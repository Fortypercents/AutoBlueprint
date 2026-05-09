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
    """
    结合了 generic_baseline 体系的模拟退火布局智能体。
    使用退火算法进行全局 Block/Node 的坐标优化，随后使用多源多目标 A* 完成浮动引脚连线。
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        self.target_outputs_dict = target_outputs
        self.available_inputs = available_inputs
        self.nodes = {}
        self.edges = []
        self.required_buildings = []
        self.node_positions = {}

        self.used_ports: Set[Tuple[int, int]] = set()
        self.generated_inputs = defaultdict(list)
        self.generated_outputs = defaultdict(list)

        # 模拟退火参数
        self.initial_temp = 1000.0
        self.cooling_rate = 0.96
        self.min_temp = 1.0
        self.iters_per_temp = 100

    def optimize(self, env: GridMap):
        print("\n[SABaselineAgent] 开始执行基于模拟退火的全局布局优化...")

        # 1. 计算所需建筑与依赖图 (继承自 baseline)
        self._calculate_ratios_and_instances()
        self._build_instance_graph()

        # 2. 模拟退火布局 (替代原有的 _partition_blocks 和 _layout_blocks)
        best_state = self._run_simulated_annealing(env)

        # 3. 将最优解写入地图与状态
        self.node_positions = best_state
        for nid, pos in self.node_positions.items():
            building = self.nodes[nid]
            env.place_building(building, pos[0], pos[1], Direction.UP)

        # 4. 浮动引脚分配与最短距离连线 (继承自 baseline)
        self._route_connections(env)

    # ==========================================
    # 核心：模拟退火算法引擎
    # ==========================================
    def _run_simulated_annealing(self, env: GridMap) -> Dict[int, Tuple[int, int]]:
        # 生成初始状态：将所有节点随机撒在地图中央区域
        current_state = {}
        cx, cy = env.width // 2, env.height // 2
        for nid, b in self.nodes.items():
            w, h = b.size
            rx = max(2, min(env.width - w - 2, cx + random.randint(-10, 10)))
            ry = max(5, min(env.height - h - 5, cy + random.randint(-10, 10)))
            current_state[nid] = (rx, ry)

        current_cost = self._evaluate_state(current_state, env)
        best_state = current_state.copy()
        best_cost = current_cost

        current_temp = self.initial_temp
        while current_temp > self.min_temp:
            for _ in range(self.iters_per_temp):
                new_state = self._get_neighbor_state(current_state, env)
                new_cost = self._evaluate_state(new_state, env)

                # Metropolis
                if new_cost < current_cost:
                    accept = True
                else:
                    prob = math.exp(-(new_cost - current_cost) / current_temp)
                    accept = random.random() < prob

                if accept:
                    current_state = new_state
                    current_cost = new_cost
                    if current_cost < best_cost:
                        best_state = current_state.copy()
                        best_cost = current_cost

            current_temp *= self.cooling_rate

        print(f"[SABaselineAgent] 退火完成！最优布局代价值: {best_cost:.2f}")
        return best_state

    def _evaluate_state(self, state: Dict[int, Tuple[int, int]], env: GridMap) -> float:
        cost = 0.0
        min_x = min_y = float('inf')
        max_x = max_y = 0
        nids = list(state.keys())

        # 1. 边界与面积计算
        for nid, (x, y) in state.items():
            w, h = self.nodes[nid].size
            min_x, min_y = min(min_x, x), min(min_y, y)
            max_x, max_y = max(max_x, x + w), max(max_y, y + h)

            # 越界惩罚
            if x < 2 or y < 3 or x + w >= env.width - 2 or y + h >= env.height - 3:
                cost += 10000.0

        area = max(0, max_x - min_x) * max(0, max_y - min_y)
        cost += area * 1.5

        # 2. AABB 重叠惩罚 (绝对不允许建筑重叠)
        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                nid1, nid2 = nids[i], nids[j]
                x1, y1 = state[nid1]
                x2, y2 = state[nid2]
                w1, h1 = self.nodes[nid1].size
                w2, h2 = self.nodes[nid2].size

                # 增加 1 格的呼吸空间 (padding)，防止靠得太紧堵死端口
                if not (x1 + w1 + 1 <= x2 or x2 + w2 + 1 <= x1 or y1 + h1 + 1 <= y2 or y2 + h2 + 1 <= y1):
                    cost += 5000.0

        # 3. 曼哈顿线长预估 (针对内部边)
        for edge in self.edges:
            sx, sy = state[edge['src']]
            dx, dy = state[edge['dst']]
            cost += (abs(sx - dx) + abs(sy - dy)) * 2.0

        # 4. 外部端口线长预估 (y=0 和 y=height-1)
        for nid, b in self.nodes.items():
            for mat in b.input_materials:
                if mat in self.available_inputs:
                    # 原料需要从顶部下来，Y坐标越小越好
                    cost += state[nid][1] * 1.0
            for mat in b.output_materials:
                if mat in self.target_outputs_dict:
                    # 产物需要送往底部，距离底部越近越好
                    cost += (env.height - state[nid][1]) * 1.0

        return cost

    def _get_neighbor_state(self, state: Dict[int, Tuple[int, int]], env: GridMap):
        new_state = state.copy()
        nid = random.choice(list(new_state.keys()))
        x, y = new_state[nid]

        if random.random() < 0.7:
            # 随机平移 1-3 格
            dx, dy = random.randint(-3, 3), random.randint(-3, 3)
            new_state[nid] = (max(2, min(env.width - 2, x + dx)), max(3, min(env.height - 3, y + dy)))
        else:
            # 随机互换位置
            nid2 = random.choice(list(new_state.keys()))
            new_state[nid] = state[nid2]
            new_state[nid2] = (x, y)

        return new_state

    # ==========================================
    # 以下为完全沿用 generic_baseline 的网络与路由逻辑
    # ==========================================
    def _calculate_ratios_and_instances(self):
        demand_queue = {k: v for k, v in self.target_outputs_dict.items()}
        recipes = get_recipe_catalog()

        while demand_queue:
            mat, amount = demand_queue.popitem()
            if mat in self.available_inputs: continue

            producer_cid = next((cid for cid, recipe in recipes.items() if mat in recipe['out']), None)
            if not producer_cid: continue

            recipe = recipes[producer_cid]
            prod_rate = recipe['out'][mat] * recipe['speed']
            num_buildings = math.ceil(amount / prod_rate)

            for _ in range(num_buildings):
                self.required_buildings.append(get_building_instance(producer_cid))

            for in_mat, in_amount in recipe['in'].items():
                demand_queue[in_mat] = demand_queue.get(in_mat, 0) + (in_amount * recipe['speed']) * (
                            amount / prod_rate)

    def _build_instance_graph(self):
        self.nodes = {i: b for i, b in enumerate(self.required_buildings)}
        providers = defaultdict(list)
        consumers = defaultdict(list)

        for nid, b in self.nodes.items():
            for mat in b.output_materials: providers[mat].append(nid)
            for mat in b.input_materials: consumers[mat].append(nid)

        for mat, c_list in consumers.items():
            if mat in self.available_inputs: continue
            if mat in providers:
                p_list = providers[mat]
                edges_for_mat = set()
                for c_idx, c_nid in enumerate(c_list):
                    edges_for_mat.add((p_list[c_idx % len(p_list)], c_nid, mat))
                for p_idx, p_nid in enumerate(p_list):
                    edges_for_mat.add((p_nid, c_list[p_idx % len(c_list)], mat))

                for src, dst, m in edges_for_mat:
                    self.edges.append({'src': src, 'dst': dst, 'mat': m})

    def _get_available_ports(self, nid: int, is_input: bool) -> List[Tuple[int, int]]:
        ax, ay = self.node_positions[nid]
        w, h = self.nodes[nid].size
        y = ay - 1 if is_input else ay + h
        ports = []
        for dx in range(w):
            port = (ax + dx, y)
            if port not in self.used_ports:
                ports.append(port)
        return ports

    def _a_star_route_multi(self, env: GridMap, starts: List[Tuple[int, int]], goals: List[Tuple[int, int]]) -> \
    Optional[List[Tuple[int, int]]]:
        def heuristic(curr):
            return min(abs(curr[0] - g[0]) + abs(curr[1] - g[1]) for g in goals)

        frontier = []
        came_from = {}
        g_score = {}

        for start in starts:
            heapq.heappush(frontier, (heuristic(start), start))
            came_from[start] = None
            g_score[start] = 0

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
                        continue

                new_cost = g_score[current] + 1
                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    priority = new_cost + heuristic((nx, ny))
                    heapq.heappush(frontier, (priority, (nx, ny)))
                    came_from[(nx, ny)] = current

        if best_goal:
            path = []
            curr = best_goal
            while curr is not None:
                path.append(curr)
                curr = came_from[curr]
            path.reverse()
            return path
        return None

    def _route_connections(self, env: GridMap):
        routing_tasks = []
        for edge in self.edges:
            routing_tasks.append(
                {'src_type': 'node', 'src': edge['src'], 'dst_type': 'node', 'dst': edge['dst'], 'mat': edge['mat']})

        for nid, b in self.nodes.items():
            for mat in b.input_materials:
                if mat in self.available_inputs:
                    routing_tasks.append(
                        {'src_type': 'ext_in', 'src': None, 'dst_type': 'node', 'dst': nid, 'mat': mat})
            for mat in b.output_materials:
                if mat in self.target_outputs_dict:
                    routing_tasks.append(
                        {'src_type': 'node', 'src': nid, 'dst_type': 'ext_out', 'dst': None, 'mat': mat})

        for t in routing_tasks:
            starts, goals = [], []

            if t['src_type'] == 'node':
                starts = self._get_available_ports(t['src'], is_input=False)
            else:
                dst_x = self.node_positions[t['dst']][0]
                starts = [(x, 0) for x in range(max(0, dst_x - 5), min(env.width, dst_x + 8))]

            if t['dst_type'] == 'node':
                goals = self._get_available_ports(t['dst'], is_input=True)
            else:
                src_x = self.node_positions[t['src']][0]
                goals = [(x, env.height - 1) for x in range(max(0, src_x - 5), min(env.width, src_x + 8))]

            if not starts or not goals: continue

            path = self._a_star_route_multi(env, starts, goals)

            if path:
                start_port, end_port = path[0], path[-1]
                if t['src_type'] == 'node': self.used_ports.add(start_port)
                if t['dst_type'] == 'node': self.used_ports.add(end_port)

                if t['src_type'] == 'ext_in': self.generated_inputs[t['mat']].append(start_port)
                if t['dst_type'] == 'ext_out': self.generated_outputs[t['mat']].append(end_port)

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
                            cell.in_dir = in_dir
                        elif type(cell).__name__ == "SystemBBelt":
                            if cell in env.transports: env.transports.remove(cell)
                            env.grid[py][px] = None
                            comp = get_transport_instance(314)
                            comp.in_dir = in_dir
                            env.place_transport(comp, px, py, Direction.DOWN)
            else:
                print(f"[Warning] Congestion: Unable to route optimally for {t}")