import math
import random
import heapq
from collections import deque, defaultdict
from typing import List, Dict, Tuple, Optional, Set

from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction
from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.utils import get_recipe_catalog


class SABaselineAgent:
    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        self.target_outputs_dict = target_outputs
        self.available_inputs = available_inputs
        self.nodes = {}
        self.edges = []
        self.node_positions = {}

        self.used_ports: Set[Tuple[int, int]] = set()
        self.generated_inputs = defaultdict(list)
        self.generated_outputs = defaultdict(list)
        self.route_paths = {}  # 记录每条线缆的具体路径坐标集

        # SA 参数 - 调整为更利于收敛的参数
        self.initial_temp = 2000.0
        self.cooling_rate = 0.96
        self.min_temp = 1.0
        self.iters_per_temp = 150

    def optimize(self, env: GridMap):
        print("\n[SABaselineAgent] Phase 1: 构建产能感知有向无环图 (DAG)...")
        self._build_capacity_aware_dag()

        print("\n[SABaselineAgent] Phase 2: 保障连通率的全局布局 (Padding-Aware SA)...")
        best_state = self._run_simulated_annealing(env)

        self.node_positions = best_state
        for nid, (x, y, d) in self.node_positions.items():
            building = self.nodes[nid]
            env.place_building(building, x, y, d)

        print("\n[SABaselineAgent] Phase 3: 严格受理约束的精准布线 (Strict Routing)...")
        self._route_connections_with_rip_up(env)

    # ==========================================
    # Phase 1: DAG 生成 (保持不变)
    # ==========================================
    def _build_capacity_aware_dag(self):
        demand_queue = {k: v for k, v in self.target_outputs_dict.items()}
        recipes = get_recipe_catalog()
        remaining_capacity = defaultdict(float)
        remaining_demand = defaultdict(lambda: defaultdict(float))
        nid_counter = 0

        while demand_queue:
            mat, amount = demand_queue.popitem()
            if mat in self.available_inputs: continue

            producer_cid = next((cid for cid, recipe in recipes.items() if mat in recipe['out']), None)
            if not producer_cid: continue

            recipe = recipes[producer_cid]
            prod_rate = recipe['out'][mat] * recipe['speed']
            num_buildings = math.ceil(amount / prod_rate)

            for _ in range(num_buildings):
                self.nodes[nid_counter] = get_building_instance(producer_cid)
                remaining_capacity[nid_counter] = prod_rate
                for in_mat, in_amount in recipe['in'].items():
                    remaining_demand[nid_counter][in_mat] = in_amount * recipe['speed']
                nid_counter += 1

            for in_mat, in_amount in recipe['in'].items():
                demand_queue[in_mat] = demand_queue.get(in_mat, 0) + (in_amount * recipe['speed']) * (
                            amount / prod_rate)

        providers = defaultdict(list)
        consumers = defaultdict(list)
        for nid, b in self.nodes.items():
            for mat in b.output_materials: providers[mat].append(nid)
            for mat in b.input_materials: consumers[mat].append(nid)

        for mat, c_list in consumers.items():
            if mat in self.available_inputs: continue
            if mat in providers:
                p_list = providers[mat]
                for c_nid in c_list:
                    demand = remaining_demand[c_nid][mat]
                    for p_nid in p_list:
                        if demand <= 0: break
                        supply = remaining_capacity[p_nid]
                        if supply > 0:
                            transfer = min(demand, supply)
                            self.edges.append({'src': p_nid, 'dst': c_nid, 'mat': mat, 'quota': transfer})
                            remaining_capacity[p_nid] -= transfer
                            demand -= transfer

    # ==========================================
    # Phase 2: 优先保证走线空间的 SA (1-Grid Padding)
    # ==========================================
    def _get_side_ports(self, nid: int, state: Dict, is_input: bool) -> List[Tuple[int, int]]:
        x, y, d = state[nid]
        w_orig, h_orig = self.nodes[nid].size
        w, h = (h_orig, w_orig) if d in (Direction.LEFT, Direction.RIGHT) else (w_orig, h_orig)

        if d == Direction.UP:
            return [(x + dx, y - 1) for dx in range(w)] if is_input else [(x + dx, y + h) for dx in range(w)]
        elif d == Direction.RIGHT:
            return [(x + w, y + dy) for dy in range(h)] if is_input else [(x - 1, y + dy) for dy in range(h)]
        elif d == Direction.DOWN:
            return [(x + dx, y + h) for dx in range(w)] if is_input else [(x + dx, y - 1) for dx in range(w)]
        elif d == Direction.LEFT:
            return [(x - 1, y + dy) for dy in range(h)] if is_input else [(x + w, y + dy) for dy in range(h)]
        return []

    def _run_simulated_annealing(self, env: GridMap) -> Dict:
        current_state = {}
        cx, cy = env.width // 2, env.height // 2
        for nid, b in self.nodes.items():
            rx = max(2, min(env.width - b.size[0] - 2, cx + random.randint(-8, 8)))
            ry = max(5, min(env.height - b.size[1] - 5, cy + random.randint(-8, 8)))
            current_state[nid] = (rx, ry, Direction.UP)

        current_cost = self._evaluate_state(current_state, env)
        best_state, best_cost = current_state.copy(), current_cost

        current_temp = self.initial_temp
        while current_temp > self.min_temp:
            for _ in range(self.iters_per_temp):
                new_state = self._get_neighbor_state(current_state, env)
                new_cost = self._evaluate_state(new_state, env)

                if new_cost < current_cost or random.random() < math.exp(-(new_cost - current_cost) / current_temp):
                    current_state = new_state
                    current_cost = new_cost
                    if current_cost < best_cost:
                        best_state, best_cost = current_state.copy(), current_cost

            current_temp *= self.cooling_rate

        return best_state

    def _evaluate_state(self, state: Dict, env: GridMap) -> float:
        cost = 0.0
        nids = list(state.keys())
        global_min_x, global_min_y, global_max_x, global_max_y = float('inf'), float('inf'), 0, 0

        def get_real_size(nid, d):
            w, h = self.nodes[nid].size
            return (h, w) if d in (Direction.LEFT, Direction.RIGHT) else (w, h)

        for nid, (x, y, d) in state.items():
            w, h = get_real_size(nid, d)
            if x < 1 or y < 2 or x + w >= env.width - 1 or y + h >= env.height - 2:
                cost += 10000.0
            global_min_x, global_min_y = min(global_min_x, x), min(global_min_y, y)
            global_max_x, global_max_y = max(global_max_x, x + w), max(global_max_y, y + h)

        # 【核心修正1】：强制要求建筑之间保留 1 格的缓冲空间 (Padding)，提供物理走廊
        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                x1, y1, d1 = state[nids[i]]
                x2, y2, d2 = state[nids[j]]
                w1, h1 = get_real_size(nids[i], d1)
                w2, h2 = get_real_size(nids[j], d2)
                # +1 保证周围留空，防止引脚和走线被挤死
                if not (x1 + w1 + 1 <= x2 or x2 + w2 + 1 <= x1 or y1 + h1 + 1 <= y2 or y2 + h2 + 1 <= y1):
                    cost += 8000.0

        active_ports = []
        for edge in self.edges:
            src_nid, dst_nid = edge['src'], edge['dst']
            out_ports = self._get_side_ports(src_nid, state, is_input=False)
            in_ports = self._get_side_ports(dst_nid, state, is_input=True)
            active_ports.extend(out_ports + in_ports)

            # 逼迫引脚相互靠近并对齐
            min_port_dist = min(abs(px - qx) + abs(py - qy) for px, py in out_ports for qx, qy in in_ports)
            cost += min_port_dist * 4.0

        # 致命排线检查：引脚绝对不能被实体压住
        for px, py in active_ports:
            for nid, (x, y, d) in state.items():
                w, h = get_real_size(nid, d)
                if x <= px < x + w and y <= py < y + h:
                    cost += 10000.0

        # 外部连线引导
        for nid, (x, y, d) in state.items():
            b = self.nodes[nid]
            if any(m in self.available_inputs for m in b.input_materials): cost += y * 2.0
            if any(m in self.target_outputs_dict for m in b.output_materials): cost += (env.height - y) * 2.0

        area = max(0, global_max_x - global_min_x) * max(0, global_max_y - global_min_y)
        cost += area * 1.2  # 降低面积在总成本中的权重，优先保连通
        return cost

    def _get_neighbor_state(self, state: Dict, env: GridMap):
        new_state = state.copy()
        nid = random.choice(list(new_state.keys()))
        x, y, d = new_state[nid]

        action = random.random()
        if action < 0.6:
            dx, dy = random.randint(-2, 2), random.randint(-2, 2)
            new_state[nid] = (max(1, min(env.width - 2, x + dx)), max(2, min(env.height - 3, y + dy)), d)
        elif action < 0.9:
            dirs = [Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT]
            new_state[nid] = (x, y, dirs[(dirs.index(d) + 1) % 4])
        else:
            nid2 = random.choice(list(new_state.keys()))
            new_state[nid] = state[nid2]
            new_state[nid2] = (x, y, d)

        return new_state

    # ==========================================
    # Phase 3: 严格物理法则 A* 与 定向拆解 (Targeted Rip-up)
    # ==========================================
    def _get_available_ports(self, nid: int, is_input: bool) -> List[Tuple[int, int]]:
        ports = self._get_side_ports(nid, self.node_positions, is_input)
        return [p for p in ports if p not in self.used_ports]

    def _route_connections_with_rip_up(self, env: GridMap):
        routing_tasks = []
        # 将任务排序：先连内部核心边，再连外部边
        for i, edge in enumerate(self.edges):
            routing_tasks.append(
                {'id': f"edge_{i}", 'src_type': 'node', 'src': edge['src'], 'dst_type': 'node', 'dst': edge['dst'],
                 'mat': edge['mat']})

        for nid, b in self.nodes.items():
            for mat in b.input_materials:
                if mat in self.available_inputs:
                    routing_tasks.append(
                        {'id': f"in_{nid}_{mat}", 'src_type': 'ext_in', 'src': None, 'dst_type': 'node', 'dst': nid,
                         'mat': mat})
            for mat in b.output_materials:
                if mat in self.target_outputs_dict:
                    routing_tasks.append(
                        {'id': f"out_{nid}_{mat}", 'src_type': 'node', 'src': nid, 'dst_type': 'ext_out', 'dst': None,
                         'mat': mat})

        failed_queue = deque(routing_tasks)
        routed_history = {}
        max_attempts = len(routing_tasks) * 5
        attempts = 0

        while failed_queue and attempts < max_attempts:
            attempts += 1
            t = failed_queue.popleft()

            starts, goals = [], []
            if t['src_type'] == 'node':
                starts = self._get_available_ports(t['src'], is_input=False)
            else:
                dst_x = self.node_positions[t['dst']][0]
                starts = [(x, 0) for x in range(max(0, dst_x - 6), min(env.width, dst_x + 7))]

            if t['dst_type'] == 'node':
                goals = self._get_available_ports(t['dst'], is_input=True)
            else:
                src_x = self.node_positions[t['src']][0]
                goals = [(x, env.height - 1) for x in range(max(0, src_x - 6), min(env.width, src_x + 7))]

            if not starts or not goals:
                failed_queue.append(t)
                continue

            path = self._a_star_route_multi(env, starts, goals)

            if path:
                routed_history[t['id']] = path
                self.route_paths[t['id']] = set(path)
                self._lay_physical_belts(env, path, t)
            else:
                print(f"[Rip-up] 任务 {t['id']} 走线死锁。执行定向拆解 (Targeted Rip-up)...")
                if routed_history:
                    # 【核心修正2】：定向拆解！优先拆除最后铺设的 2 条线，因为它们最有可能堵住了当前的任务
                    recent_keys = list(routed_history.keys())[-2:]
                    for r_key in recent_keys:
                        old_path = routed_history.pop(r_key)
                        self.route_paths.pop(r_key, None)
                        self._remove_physical_belts(env, old_path)
                        # 将被拆除的任务重新插回队首（稍后执行），把当前失败任务优先执行
                        failed_queue.appendleft(next(task for task in routing_tasks if task['id'] == r_key))
                failed_queue.appendleft(t)  # 保证清空阻挡后立即重试自身

    def _a_star_route_multi(self, env: GridMap, starts: List[Tuple[int, int]], goals: List[Tuple[int, int]]):
        def heuristic(curr):
            return min(abs(curr[0] - g[0]) + abs(curr[1] - g[1]) for g in goals)

        frontier, came_from, g_score = [], {}, {}
        for start in starts:
            heapq.heappush(frontier, (heuristic(start), start))
            came_from[start], g_score[start] = None, 0

        best_goal = None
        while frontier:
            current = heapq.heappop(frontier)[1]
            if current in goals:
                best_goal = current
                break
            x, y = current
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = x + dx, y + dy
                if not env.is_in_bounds(nx, ny): continue

                cell = env._get_cell(nx, ny)
                is_crossable = False

                if cell is not None and (nx, ny) not in goals and (nx, ny) not in starts:
                    # 【核心修正3】：恢复严格的垂直交叉器物理判定，禁止非直角的随意穿模
                    if type(cell).__name__ == "SystemBBelt":
                        move_dir = Direction.RIGHT if nx > x else Direction.LEFT if nx < x else Direction.DOWN if ny > y else Direction.UP
                        belt_out_dir = getattr(cell, 'direction', Direction.RIGHT)
                        belt_in_dir = getattr(cell, 'in_dir', None)
                        if belt_in_dir is None:
                            belt_in_dir = Direction.LEFT if belt_out_dir == Direction.RIGHT else Direction.RIGHT if belt_out_dir == Direction.LEFT else Direction.DOWN if belt_out_dir == Direction.UP else Direction.UP

                        is_straight = False
                        if belt_out_dir == Direction.RIGHT and belt_in_dir == Direction.LEFT:
                            is_straight = True
                        elif belt_out_dir == Direction.LEFT and belt_in_dir == Direction.RIGHT:
                            is_straight = True
                        elif belt_out_dir == Direction.UP and belt_in_dir == Direction.DOWN:
                            is_straight = True
                        elif belt_out_dir == Direction.DOWN and belt_in_dir == Direction.UP:
                            is_straight = True

                        if is_straight:
                            if move_dir in [Direction.UP, Direction.DOWN] and belt_out_dir in [Direction.LEFT,
                                                                                               Direction.RIGHT]:
                                is_crossable = True
                            elif move_dir in [Direction.LEFT, Direction.RIGHT] and belt_out_dir in [Direction.UP,
                                                                                                    Direction.DOWN]:
                                is_crossable = True

                    if not is_crossable:
                        continue  # 遇到建筑或非垂直传送带，绝对不可跨越

                # 如果跨越已有的线，稍微增加惩罚值，促使优先走空地
                cross_penalty = 2 if is_crossable else 1
                new_cost = g_score[current] + cross_penalty

                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    heapq.heappush(frontier, (new_cost + heuristic((nx, ny)), (nx, ny)))
                    came_from[(nx, ny)] = current

        if best_goal:
            path, curr = [], best_goal
            while curr is not None:
                path.append(curr)
                curr = came_from[curr]
            return path[::-1]
        return None

    def _lay_physical_belts(self, env: GridMap, path: List[Tuple[int, int]], task: Dict):
        start_port, end_port = path[0], path[-1]
        if task['src_type'] == 'node': self.used_ports.add(start_port)
        if task['dst_type'] == 'node': self.used_ports.add(end_port)
        if task['src_type'] == 'ext_in': self.generated_inputs[task['mat']].append(start_port)
        if task['dst_type'] == 'ext_out': self.generated_outputs[task['mat']].append(end_port)

        for i in range(len(path)):
            px, py = path[i]
            if i + 1 < len(path):
                nx, ny = path[i + 1]
                out_dir = Direction.RIGHT if nx > px else Direction.LEFT if nx < px else Direction.DOWN if ny > py else Direction.UP
            else:
                out_dir = Direction.DOWN

            if i > 0:
                prev_x, prev_y = path[i - 1]
                in_dir = Direction.LEFT if px > prev_x else Direction.RIGHT if px < prev_x else Direction.UP if py > prev_y else Direction.DOWN
            else:
                in_dir = Direction.UP

            cell = env._get_cell(px, py)
            if cell is None:
                comp = get_transport_instance(301)
                comp.in_dir = in_dir
                env.place_transport(comp, px, py, out_dir)
            else:
                if (px, py) == start_port or (px, py) == end_port:
                    if hasattr(cell, 'in_dir'): cell.in_dir = in_dir
                elif type(cell).__name__ == "SystemBBelt" and (px, py) != start_port and (px, py) != end_port:
                    if cell in env.transports: env.transports.remove(cell)
                    env.grid[py][px] = None
                    comp = get_transport_instance(314)  # 严格替换为交叉器
                    comp.in_dir = in_dir
                    env.place_transport(comp, px, py, out_dir)

    def _remove_physical_belts(self, env: GridMap, path: List[Tuple[int, int]]):
        if not path: return
        self.used_ports.discard(path[0])
        self.used_ports.discard(path[-1])

        for i, (px, py) in enumerate(path):
            cell = env._get_cell(px, py)
            if cell is None: continue

            # 如果是交叉器 (314)，拆除时需要降级回普通传送带 (301)，而不是直接挖空
            if type(cell).__name__ == "SystemCrosser" or type(cell).__name__ == "SystemBBelt" and getattr(cell, 'id',
                                                                                                          0) == 314:
                # 寻找哪条别的线的历史路径经过这里，恢复它的方向
                restored = False
                for other_path in self.route_paths.values():
                    if (px, py) in other_path:
                        env.transports.remove(cell)
                        env.grid[py][px] = None
                        comp = get_transport_instance(301)
                        # 这里简化处理：假定原线路的方向不受影响
                        env.place_transport(comp, px, py, cell.direction)
                        restored = True
                        break
                if not restored and cell in env.transports:
                    env.transports.remove(cell)
                    env.grid[py][px] = None
            elif cell in env.transports:
                env.transports.remove(cell)
                env.grid[py][px] = None