import math
import random
import heapq
from collections import deque, defaultdict
from typing import List, Dict, Tuple, Optional, Set, Any

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

        # SA 参数
        self.initial_temp = 2500.0
        self.cooling_rate = 0.97
        self.min_temp = 1.0
        self.iters_per_temp = 200

    def optimize(self, env: GridMap):
        print("\n[SABaselineAgent] Phase 1: 构建产能感知有向无环图 (DAG)...")
        self._build_capacity_aware_dag()

        print("\n[SABaselineAgent] Phase 2: 端口级旋转与排布寻优 (Port-Aware SA Placement)...")
        best_state = self._run_simulated_annealing(env)

        self.node_positions = best_state
        for nid, (x, y, d) in self.node_positions.items():
            building = self.nodes[nid]
            env.place_building(building, x, y, d)

        print("\n[SABaselineAgent] Phase 3: 精准微观布线 (Rip-up & Reroute)...")
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
    # Phase 2: 全新的、具备端口与旋转感知的 SA
    # ==========================================
    def _get_side_ports(self, nid: int, state: Dict, is_input: bool) -> List[Tuple[int, int]]:
        """【核心修复】：根据建筑当前的旋转方向，精准返回对应的进出口坐标"""
        x, y, d = state[nid]
        w_orig, h_orig = self.nodes[nid].size
        w, h = (h_orig, w_orig) if d in (Direction.LEFT, Direction.RIGHT) else (w_orig, h_orig)

        # 假定默认朝上时：顶部进货，底部出货
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
            rx = max(2, min(env.width - b.size[0] - 2, cx + random.randint(-6, 6)))
            ry = max(5, min(env.height - b.size[1] - 5, cy + random.randint(-6, 6)))
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

        # 获取实际尺寸
        def get_real_size(nid, d):
            w, h = self.nodes[nid].size
            return (h, w) if d in (Direction.LEFT, Direction.RIGHT) else (w, h)

        # 1. 越界与基础面积
        for nid, (x, y, d) in state.items():
            w, h = get_real_size(nid, d)
            if x < 1 or y < 2 or x + w >= env.width - 1 or y + h >= env.height - 2:
                cost += 10000.0
            global_min_x, global_min_y = min(global_min_x, x), min(global_min_y, y)
            global_max_x, global_max_y = max(global_max_x, x + w), max(global_max_y, y + h)

        # 2. 绝对刚体碰撞 (不允许实体间有任何重叠)
        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                x1, y1, d1 = state[nids[i]]
                x2, y2, d2 = state[nids[j]]
                w1, h1 = get_real_size(nids[i], d1)
                w2, h2 = get_real_size(nids[j], d2)
                if not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1):
                    cost += 10000.0

        # 3. 核心：引脚级连接预判 (逼迫算法进行正确的旋转与预留排线空间)
        active_ports = []
        for edge in self.edges:
            src_nid, dst_nid = edge['src'], edge['dst']

            # 拿到供应方实际的输出口，和需求方实际的输入口
            out_ports = self._get_side_ports(src_nid, state, is_input=False)
            in_ports = self._get_side_ports(dst_nid, state, is_input=True)
            active_ports.extend(out_ports + in_ports)

            # 计算最佳对接引脚之间的曼哈顿距离
            min_port_dist = min(abs(px - qx) + abs(py - qy) for px, py in out_ports for qx, qy in in_ports)

            # 【关键】：距离越小得分越高！这会迫使建筑互相旋转，将进出口“面对面”对准！
            cost += min_port_dist * 3.0

            # 扩展含线全局包围盒
            for px, py in out_ports:
                global_min_x, global_max_x = min(global_min_x, px), max(global_max_x, px)
                global_min_y, global_max_y = min(global_min_y, py), max(global_max_y, py)
            for qx, qy in in_ports:
                global_min_x, global_max_x = min(global_min_x, qx), max(global_max_x, qx)
                global_min_y, global_max_y = min(global_min_y, qy), max(global_max_y, qy)

        # 4. 【致命排线检查】：绝杀那些封死传送带的“假优解”
        # 如果排线必经的引脚，被别的（甚至自己的）建筑压在身下，直接给毁灭惩罚！
        for px, py in active_ports:
            for nid, (x, y, d) in state.items():
                w, h = get_real_size(nid, d)
                if x <= px < x + w and y <= py < y + h:
                    cost += 5000.0  # 传送带端口被实体建筑压死，完全无法排线！

        # 外部连线引导
        for nid, (x, y, d) in state.items():
            b = self.nodes[nid]
            if any(m in self.available_inputs for m in b.input_materials): cost += y * 1.5
            if any(m in self.target_outputs_dict for m in b.output_materials): cost += (env.height - y) * 1.5

        area = max(0, global_max_x - global_min_x) * max(0, global_max_y - global_min_y)
        cost += area * 1.5
        return cost

    def _get_neighbor_state(self, state: Dict, env: GridMap):
        new_state = state.copy()
        nid = random.choice(list(new_state.keys()))
        x, y, d = new_state[nid]

        action = random.random()
        if action < 0.5:
            # 频繁平移
            dx, dy = random.randint(-3, 3), random.randint(-3, 3)
            new_state[nid] = (max(1, min(env.width - 2, x + dx)), max(2, min(env.height - 3, y + dy)), d)
        elif action < 0.85:
            # 高频旋转 (0, 90, 180, 270)
            dirs = [Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT]
            new_state[nid] = (x, y, dirs[(dirs.index(d) + 1) % 4])
        else:
            nid2 = random.choice(list(new_state.keys()))
            new_state[nid] = state[nid2]
            new_state[nid2] = (x, y, d)

        return new_state

    # ==========================================
    # Phase 3: 严格受方向约束的 A* 寻路
    # ==========================================
    def _get_available_ports(self, nid: int, is_input: bool) -> List[Tuple[int, int]]:
        """仅返回对应当前旋转方向的物理引脚"""
        ports = self._get_side_ports(nid, self.node_positions, is_input)
        return [p for p in ports if p not in self.used_ports]

    def _route_connections_with_rip_up(self, env: GridMap):
        routing_tasks = []
        for i, edge in enumerate(self.edges):
            routing_tasks.append(
                {'id': i, 'src_type': 'node', 'src': edge['src'], 'dst_type': 'node', 'dst': edge['dst'],
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
        max_attempts = len(routing_tasks) * 3
        attempts = 0

        while failed_queue and attempts < max_attempts:
            attempts += 1
            t = failed_queue.popleft()

            starts, goals = [], []
            if t['src_type'] == 'node':
                starts = self._get_available_ports(t['src'], is_input=False)
            else:
                dst_x = self.node_positions[t['dst']][0]
                starts = [(x, 0) for x in range(max(0, dst_x - 4), min(env.width, dst_x + 5))]

            if t['dst_type'] == 'node':
                goals = self._get_available_ports(t['dst'], is_input=True)
            else:
                src_x = self.node_positions[t['src']][0]
                goals = [(x, env.height - 1) for x in range(max(0, src_x - 4), min(env.width, src_x + 5))]

            path = self._a_star_route_multi(env, starts, goals)

            if path:
                routed_history[t['id']] = path
                self._lay_physical_belts(env, path, t)
            else:
                print(f"[Rip-up] 任务 {t['id']} 寻路失败。强行拆毁挡路旧线重试...")
                if routed_history:
                    rip_keys = random.sample(list(routed_history.keys()), min(2, len(routed_history)))
                    for r_key in rip_keys:
                        old_path = routed_history.pop(r_key)
                        self._remove_physical_belts(env, old_path)
                        failed_queue.append(next(task for task in routing_tasks if task['id'] == r_key))
                failed_queue.append(t)

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

                # 如果这个格子不是目标，不是起点，且已经被建筑占了，绝对不可跨越！
                if cell is not None and (nx, ny) not in goals and (nx, ny) not in starts:
                    if type(cell).__name__ != "SystemBBelt":
                        continue  # 撞到建筑了，死路一条

                new_cost = g_score[current] + 1
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
            out_dir = Direction.DOWN if i + 1 == len(path) else Direction((path[i + 1][0] - px, path[i + 1][1] - py))
            in_dir = Direction.UP if i == 0 else Direction((px - path[i - 1][0], py - path[i - 1][1]))
            cell = env._get_cell(px, py)
            if cell is None:
                comp = get_transport_instance(301)
                comp.in_dir = in_dir
                env.place_transport(comp, px, py, out_dir)
            elif type(cell).__name__ == "SystemBBelt" and (px, py) != start_port and (px, py) != end_port:
                env.transports.remove(cell)
                env.grid[py][px] = None
                comp = get_transport_instance(314)  # Crosser
                comp.in_dir = in_dir
                env.place_transport(comp, px, py, out_dir)

    def _remove_physical_belts(self, env: GridMap, path: List[Tuple[int, int]]):
        if not path: return
        self.used_ports.discard(path[0])
        self.used_ports.discard(path[-1])
        for px, py in path:
            cell = env._get_cell(px, py)
            if cell and cell in env.transports:
                env.transports.remove(cell)
                env.grid[py][px] = None