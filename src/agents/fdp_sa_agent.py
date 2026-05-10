import math
import random
import heapq
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Set

from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction
from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.utils import get_recipe_catalog


class FdpSaAgent:
    """
    两阶段混合布局智能体 (极致紧凑 & 严谨正交布线版):
    1. FDP 寻找全局紧凑拓扑 (带向心力压缩)。
    2. SA 最小化占地面积 (Bounding Box 惩罚)。
    3. M:N 动态多目标 A* 寻路，带【绝对引脚保护】与【强制直行穿越锁】。
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

        # 保持 padding 为 3：为机器前方的交叉与转弯预留缓冲空间，防止死胡同
        self.padding = 3

    def optimize(self, env: GridMap):
        print("\n[FdpSaAgent] 启动紧凑型混合布局引擎...")

        self._calculate_ratios_and_instances()
        self._build_instance_graph()

        print(f"[FdpSaAgent] 计算 FDP 力导向初始拓扑 (聚拢收敛)...")
        fdp_state = self._run_force_directed_placement(env)

        print(f"[FdpSaAgent] 执行 SA 模拟退火 (最小化占地面积)...")
        best_state = self._run_simulated_annealing(env, fdp_state)
        self.node_positions = best_state

        for nid, state in self.node_positions.items():
            building = self.nodes[nid]
            env.place_building(building, state['x'], state['y'], state['dir'])

        print(f"[FdpSaAgent] 执行多源多目标 A* 自动布线 (启用引脚保护区与交叉锁)...")
        self._route_connections(env)
        print(f"[FdpSaAgent] 蓝图构建完毕！")

    # ==========================================
    # 核心修复 1: 完美的多对多 (M:N) 映射逻辑
    # ==========================================
    def _build_instance_graph(self):
        self.nodes = {i: b for i, b in enumerate(self.required_buildings)}
        providers, consumers = defaultdict(list), defaultdict(list)

        for nid, b in self.nodes.items():
            for mat in b.output_materials: providers[mat].append(nid)
            for mat in b.input_materials: consumers[mat].append(nid)

        for mat in set(providers.keys()).intersection(consumers.keys()):
            if mat in self.available_inputs: continue

            p_list = providers[mat]
            c_list = consumers[mat]

            # 1. 确保每一个供应者都有一个消费者
            for i, p_nid in enumerate(p_list):
                c_nid = c_list[i % len(c_list)]
                self.edges.append({'src': p_nid, 'dst': c_nid, 'mat': mat})

            # 2. 确保每一个消费者都获得了至少一个供应者
            for i, c_nid in enumerate(c_list):
                if not any(e['dst'] == c_nid and e['mat'] == mat for e in self.edges):
                    p_nid = p_list[i % len(p_list)]
                    self.edges.append({'src': p_nid, 'dst': c_nid, 'mat': mat})

    # ==========================================
    # 核心修复 2: 寻路引脚保护与直行穿越锁 (Crosser BUG Fix)
    # ==========================================
    def _a_star_route_multi(self, env: GridMap, starts: List[Tuple[int, int]], goals: List[Tuple[int, int]],
                            forbidden: Set[Tuple[int, int]]) -> Optional[List[Tuple[int, int]]]:
        frontier = []
        came_from = {}
        g_score = {}
        for start in starts:
            heapq.heappush(frontier, (0, start))
            came_from[start] = None
            g_score[start] = 0

        best_goal = None
        while frontier:
            current = heapq.heappop(frontier)[1]
            if current in goals:
                best_goal = current
                break

            x, y = current
            cell_current = env._get_cell(x, y)

            # 判断当前脚下是否踩在别人的传送带上
            is_on_crossable = (cell_current is not None and type(
                cell_current).__name__ == "SystemBBelt" and current not in starts and current not in goals)

            allowed_moves = [(0, -1), (0, 1), (-1, 0), (1, 0)]

            # 【核心穿越锁】：踩在皮带上时，绝不允许转弯！必须直挺挺地跨过去！
            if is_on_crossable and came_from[current] is not None:
                px, py = came_from[current]
                allowed_moves = [(x - px, y - py)]

            for dx, dy in allowed_moves:
                nx, ny = x + dx, y + dy
                if not env.is_in_bounds(nx, ny): continue

                # 【核心引脚保护】：严禁任何人借道或横穿他人的输入输出端口
                if (nx, ny) in forbidden: continue

                cell_next = env._get_cell(nx, ny)
                is_crossable = False

                if cell_next is not None and (nx, ny) not in goals and (nx, ny) not in starts:
                    # 注意：如果前方已经是 Crosser，严禁二次重叠穿越！只允许穿越普通的 SystemBBelt
                    if type(cell_next).__name__ == "SystemBBelt":
                        move_dir = Direction.RIGHT if nx > x else Direction.LEFT if nx < x else Direction.DOWN if ny > y else Direction.UP
                        belt_out_dir = getattr(cell_next, 'direction', Direction.RIGHT)
                        belt_in_dir = getattr(cell_next, 'in_dir', self._get_opposite_dir(belt_out_dir))

                        is_straight = (belt_out_dir, belt_in_dir) in [
                            (Direction.RIGHT, Direction.LEFT), (Direction.LEFT, Direction.RIGHT),
                            (Direction.UP, Direction.DOWN), (Direction.DOWN, Direction.UP)
                        ]

                        # 只允许在对方是直道，且我们垂直撞向它时，才判定为合法交叉
                        if is_straight:
                            if move_dir in [Direction.UP, Direction.DOWN] and belt_out_dir in [Direction.LEFT,
                                                                                               Direction.RIGHT]:
                                is_crossable = True
                            elif move_dir in [Direction.LEFT, Direction.RIGHT] and belt_out_dir in [Direction.UP,
                                                                                                    Direction.DOWN]:
                                is_crossable = True

                    if not is_crossable: continue

                # A* 惩罚参数
                turn_penalty = 0
                if came_from[current] is not None:
                    px, py = came_from[current]
                    if (x - px) != dx or (y - py) != dy:
                        turn_penalty = 2  # 惩罚无意义转弯，鼓励走拉直的线

                cross_penalty = 15 if is_crossable else 0  # 交叉有风险，轻微惩罚优先绕路

                new_cost = g_score[current] + 1 + turn_penalty + cross_penalty

                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    h = min(abs(nx - g[0]) + abs(ny - g[1]) for g in goals)
                    heapq.heappush(frontier, (new_cost + h, (nx, ny)))
                    came_from[(nx, ny)] = current

        if best_goal:
            path = []
            curr = best_goal
            while curr is not None:
                path.append(curr)
                curr = came_from[curr]
            return path[::-1]
        return None

    def _route_connections(self, env: GridMap):
        # 1. 搜集全图机器的所有可用端口，设为禁区
        self.all_building_ports = set()
        for nid in self.nodes:
            self.all_building_ports.update(self._get_all_ports_of_node(nid, True))
            self.all_building_ports.update(self._get_all_ports_of_node(nid, False))

        tasks = [{'src_type': 'node', 'src': e['src'], 'dst_type': 'node', 'dst': e['dst'], 'mat': e['mat']} for e in
                 self.edges]

        for nid, b in self.nodes.items():
            for mat in b.input_materials:
                if mat in self.available_inputs:
                    tasks.append({'src_type': 'ext_in', 'src': None, 'dst_type': 'node', 'dst': nid, 'mat': mat})
            for mat in b.output_materials:
                if mat in self.target_outputs_dict:
                    tasks.append({'src_type': 'node', 'src': nid, 'dst_type': 'ext_out', 'dst': None, 'mat': mat})

        # 优先链接机器内部节点，把外部输入/输出放最后（留出外部操作空间）
        tasks.sort(key=lambda t: 1 if t['src_type'] == 'ext_in' or t['dst_type'] == 'ext_out' else 0)

        for t in tasks:
            starts, goals = [], []
            if t['src_type'] == 'node':
                starts = self._get_available_ports(t['src'], False)
            else:
                starts = [(x, 0) for x in range(env.width)]
            if t['dst_type'] == 'node':
                goals = self._get_available_ports(t['dst'], True)
            else:
                goals = [(x, env.height - 1) for x in range(env.width)]

            if not starts or not goals: continue

            # 构建对当前线路生效的安全禁区（扣除当前起点与终点）
            forbidden_cells = self.all_building_ports - set(starts) - set(goals)

            path = self._a_star_route_multi(env, starts, goals, forbidden_cells)
            if path:
                start_p, end_p = path[0], path[-1]
                if t['src_type'] == 'node': self.used_ports.add(start_p)
                if t['dst_type'] == 'node': self.used_ports.add(end_p)
                if t['src_type'] == 'ext_in': self.generated_inputs[t['mat']].append(start_p)
                if t['dst_type'] == 'ext_out': self.generated_outputs[t['mat']].append(end_p)

                for i in range(len(path)):
                    px, py = path[i]
                    if i + 1 < len(path):
                        out_dir = self._dir_between(path[i], path[i + 1])
                    else:
                        if t['dst_type'] == 'node':
                            out_dir = self._get_opposite_dir(self.node_positions[t['dst']]['dir'])
                        else:
                            out_dir = Direction.DOWN

                    if i > 0:
                        in_dir = self._dir_between(path[i], path[i - 1])
                    else:
                        if t['src_type'] == 'node':
                            in_dir = self.node_positions[t['src']]['dir']
                        else:
                            in_dir = Direction.UP

                    cell = env._get_cell(px, py)
                    if cell is None:
                        comp = get_transport_instance(301)
                        comp.in_dir = in_dir
                        env.place_transport(comp, px, py, out_dir)
                    else:
                        # 对于合法的端点重叠，赋予最终受力面
                        if (px, py) == start_p or (px, py) == end_p:
                            cell.in_dir = in_dir
                        elif type(cell).__name__ == "SystemBBelt":
                            # 发生物理交叉！正确挂载 Crosser (314)
                            original_dir = getattr(cell, 'direction', Direction.RIGHT)
                            original_in = getattr(cell, 'in_dir', self._get_opposite_dir(original_dir))

                            if cell in env.transports: env.transports.remove(cell)
                            env.grid[py][px] = None

                            comp = get_transport_instance(314)
                            comp.in_dir = original_in
                            env.place_transport(comp, px, py, original_dir)
            else:
                print(f"[Warning] 路径拥堵: 无法为 {t['mat'].name} 规划无损连线。")

    # ==========================================
    # 获取任意建筑所有端口辅助函数
    # ==========================================
    def _get_all_ports_of_node(self, nid: int, is_input: bool) -> List[Tuple[int, int]]:
        if nid not in self.node_positions: return []
        x, y = self.node_positions[nid]['x'], self.node_positions[nid]['y']
        d = self.node_positions[nid]['dir']
        w, h = self.nodes[nid].size
        target_side = d if is_input else self._get_opposite_dir(d)

        if target_side == Direction.UP:
            return [(x + dx, y - 1) for dx in range(w)]
        elif target_side == Direction.DOWN:
            return [(x + dx, y + h) for dx in range(w)]
        elif target_side == Direction.LEFT:
            return [(x - 1, y + dy) for dy in range(h)]
        elif target_side == Direction.RIGHT:
            return [(x + w, y + dy) for dy in range(h)]
        return []

    def _get_available_ports(self, nid: int, is_input: bool) -> List[Tuple[int, int]]:
        ports = self._get_all_ports_of_node(nid, is_input)
        return [p for p in ports if p not in self.used_ports]

    # ==========================================
    # 其他核心 FDP / SA 算法保留原有设计
    # ==========================================
    def _run_force_directed_placement(self, env: GridMap) -> Dict[int, Dict]:
        pos = {}
        cx, cy = env.width / 2.0, env.height / 2.0
        for nid in self.nodes:
            pos[nid] = [cx + random.uniform(-3, 3), cy + random.uniform(-3, 3)]

        velocities = {nid: [0.0, 0.0] for nid in self.nodes}
        for _ in range(60):
            forces = {nid: [0.0, 0.0] for nid in self.nodes}
            nids = list(self.nodes.keys())

            for i in range(len(nids)):
                for j in range(i + 1, len(nids)):
                    n1, n2 = nids[i], nids[j]
                    dx, dy = pos[n1][0] - pos[n2][0], pos[n1][1] - pos[n2][1]
                    dist = max(0.1, math.hypot(dx, dy))
                    f = 120.0 / (dist * dist)
                    forces[n1][0] += (dx / dist) * f;
                    forces[n1][1] += (dy / dist) * f
                    forces[n2][0] -= (dx / dist) * f;
                    forces[n2][1] -= (dy / dist) * f

            for edge in self.edges:
                n1, n2 = edge['src'], edge['dst']
                dx, dy = pos[n2][0] - pos[n1][0], pos[n2][1] - pos[n1][1]
                dist = max(0.1, math.hypot(dx, dy))
                f = 2.5 * dist
                forces[n1][0] += (dx / dist) * f;
                forces[n1][1] += (dy / dist) * f
                forces[n2][0] -= (dx / dist) * f;
                forces[n2][1] -= (dy / dist) * f

            # 向心力压缩
            for nid in self.nodes:
                dx, dy = cx - pos[nid][0], cy - pos[nid][1]
                forces[nid][0] += dx * 0.8
                forces[nid][1] += dy * 0.8

            for nid in self.nodes:
                velocities[nid][0] = (velocities[nid][0] + forces[nid][0]) * 0.80
                velocities[nid][1] = (velocities[nid][1] + forces[nid][1]) * 0.80
                pos[nid][0] += velocities[nid][0]
                pos[nid][1] += velocities[nid][1]

        state = {}
        for nid in self.nodes:
            x = max(self.padding, min(env.width - 5, int(pos[nid][0])))
            y = max(self.padding, min(env.height - 5, int(pos[nid][1])))
            state[nid] = {'x': x, 'y': y, 'dir': random.choice(list(Direction)), 'size': self.nodes[nid].size}
        return state

    def _run_simulated_annealing(self, env: GridMap, initial_state: Dict) -> Dict:
        curr_state = initial_state
        curr_cost = self._evaluate_state(curr_state, env)
        best_state, best_cost = {k: v.copy() for k, v in curr_state.items()}, curr_cost

        temp = 800.0
        while temp > 1.0:
            for _ in range(60):
                new_state = self._mutate_state(curr_state, env)
                new_cost = self._evaluate_state(new_state, env)
                if new_cost < curr_cost or math.exp(-(new_cost - curr_cost) / temp) > random.random():
                    curr_state, curr_cost = new_state, new_cost
                    if curr_cost < best_cost:
                        best_state, best_cost = {k: v.copy() for k, v in curr_state.items()}, curr_cost
            temp *= 0.95
        return best_state

    def _mutate_state(self, state: Dict, env: GridMap) -> Dict:
        new_s = {k: v.copy() for k, v in state.items()}
        nid = random.choice(list(new_s.keys()))
        r = random.random()
        if r < 0.5:
            new_s[nid]['x'] = max(self.padding, min(env.width - 5, new_s[nid]['x'] + random.choice([-1, 1, -2, 2])))
            new_s[nid]['y'] = max(self.padding, min(env.height - 5, new_s[nid]['y'] + random.choice([-1, 1, -2, 2])))
        elif r < 0.85:
            new_s[nid]['dir'] = random.choice([d for d in Direction if d != new_s[nid]['dir']])
        else:
            nid2 = random.choice(list(new_s.keys()))
            new_s[nid]['x'], new_s[nid]['y'], new_s[nid2]['x'], new_s[nid2]['y'] = new_s[nid2]['x'], new_s[nid2]['y'], \
                                                                                   new_s[nid]['x'], new_s[nid]['y']
        return new_s

    def _evaluate_state(self, state: Dict, env: GridMap) -> float:
        cost = 0.0
        nids = list(state.keys())
        min_gx, min_gy, max_gx, max_gy = float('inf'), float('inf'), -float('inf'), -float('inf')

        for i in range(len(nids)):
            s1 = state[nids[i]]
            w1, h1 = s1['size']
            if s1['dir'] in (Direction.LEFT, Direction.RIGHT): w1, h1 = h1, w1

            min_gx = min(min_gx, s1['x'])
            min_gy = min(min_gy, s1['y'])
            max_gx = max(max_gx, s1['x'] + w1)
            max_gy = max(max_gy, s1['y'] + h1)

            for j in range(i + 1, len(nids)):
                s2 = state[nids[j]]
                w2, h2 = s2['size']
                if s2['dir'] in (Direction.LEFT, Direction.RIGHT): w2, h2 = h2, w2

                if not (s1['x'] + w1 + self.padding <= s2['x'] or s2['x'] + w2 + self.padding <= s1['x'] or
                        s1['y'] + h1 + self.padding <= s2['y'] or s2['y'] + h2 + self.padding <= s1['y']):
                    cost += 50000.0

        # Bounding Box 面积惩罚
        area = max(0, max_gx - min_gx) * max(0, max_gy - min_gy)
        cost += area * 15.0

        for edge in self.edges:
            s_src, s_dst = state[edge['src']], state[edge['dst']]
            w1, h1 = s_src['size']
            if s_src['dir'] in (Direction.LEFT, Direction.RIGHT): w1, h1 = h1, w1
            w2, h2 = s_dst['size']
            if s_dst['dir'] in (Direction.LEFT, Direction.RIGHT): w2, h2 = h2, w2

            out_side = self._get_opposite_dir(s_src['dir'])
            out_x = s_src['x'] + w1 / 2 if out_side in (Direction.UP, Direction.DOWN) else (
                s_src['x'] - 1 if out_side == Direction.LEFT else s_src['x'] + w1)
            out_y = s_src['y'] + h1 / 2 if out_side in (Direction.LEFT, Direction.RIGHT) else (
                s_src['y'] - 1 if out_side == Direction.UP else s_src['y'] + h1)

            in_side = s_dst['dir']
            in_x = s_dst['x'] + w2 / 2 if in_side in (Direction.UP, Direction.DOWN) else (
                s_dst['x'] - 1 if in_side == Direction.LEFT else s_dst['x'] + w2)
            in_y = s_dst['y'] + h2 / 2 if in_side in (Direction.LEFT, Direction.RIGHT) else (
                s_dst['y'] - 1 if in_side == Direction.UP else s_dst['y'] + h2)

            dist = abs(out_x - in_x) + abs(out_y - in_y)
            cost += dist * 12.0

            dx, dy = in_x - out_x, in_y - out_y
            for side, vdx, vdy in [(Direction.RIGHT, 1, 0), (Direction.LEFT, -1, 0), (Direction.DOWN, 0, 1),
                                   (Direction.UP, 0, -1)]:
                if out_side == side and dx * vdx > 0 and dy * vdy == 0: cost -= 40
                if in_side == side and dx * vdx > 0 and dy * vdy == 0: cost -= 40
        return cost

    def _get_opposite_dir(self, d: Direction) -> Direction:
        return {Direction.UP: Direction.DOWN, Direction.DOWN: Direction.UP,
                Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT}[d]

    def _dir_between(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> Direction:
        if p2[0] > p1[0]: return Direction.RIGHT
        if p2[0] < p1[0]: return Direction.LEFT
        if p2[1] > p1[1]: return Direction.DOWN
        return Direction.UP

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
            for _ in range(math.ceil(amount / prod_rate)):
                self.required_buildings.append(get_building_instance(producer_cid))
            for in_mat, in_amount in recipe['in'].items():
                demand_queue[in_mat] = demand_queue.get(in_mat, 0) + (in_amount * recipe['speed']) * (
                            amount / prod_rate)