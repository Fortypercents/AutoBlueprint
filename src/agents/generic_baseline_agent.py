import math
import heapq
from collections import deque, defaultdict
from typing import List, Dict, Tuple, Optional

from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction
from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.utils import get_recipe_catalog


class GenericBaselineAgent:
    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        self.target_outputs_dict = target_outputs
        self.available_inputs = available_inputs
        self.nodes = {}
        self.edges = []
        self.required_buildings = []
        self.node_positions = {}

        self.generated_inputs = defaultdict(list)
        self.generated_outputs = defaultdict(list)

    def optimize(self, env: GridMap):
        print("\n[GenericBaselineAgent] Starting smart autonomous production line planning...")

        self._calculate_ratios_and_instances()
        self._build_instance_graph()
        tiers = self._calculate_tiers()

        # 1. 优先防止好所有建筑
        self._layout_grid(env, tiers)

        # 2 & 3. 预先部署出入口组件并执行带交叉器的自动排线
        self._route_connections(env)

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

    def _calculate_tiers(self) -> Dict[int, List[int]]:
        in_degrees = {nid: 0 for nid in self.nodes.keys()}
        for edge in self.edges: in_degrees[edge['dst']] += 1
        sources = [nid for nid, deg in in_degrees.items() if deg == 0]

        depths = {nid: 0 for nid in self.nodes.keys()}
        queue = deque(sources)
        while queue:
            curr = queue.popleft()
            for edge in self.edges:
                if edge['src'] == curr:
                    nxt = edge['dst']
                    if depths[curr] + 1 > depths[nxt]:
                        depths[nxt] = depths[curr] + 1
                        queue.append(nxt)
        tiers = defaultdict(list)
        for nid, d in depths.items(): tiers[d].append(nid)
        return dict(tiers)

    def _layout_grid(self, env: GridMap, tiers: Dict[int, List[int]]):
        start_x, start_y = 3, 5
        y_spacing = 7
        min_x_spacing = 3
        current_y = start_y
        max_depth = max(tiers.keys()) if tiers else 0

        for tier_level in range(max_depth + 1):
            nodes_in_tier = tiers.get(tier_level, [])
            current_x, max_height_in_tier = start_x, 0

            for nid in nodes_in_tier:
                building = self.nodes[nid]
                w, h = building.size

                parents = [e['src'] for e in self.edges if e['dst'] == nid and e['src'] in self.node_positions]
                if parents:
                    avg_center_x = sum(self.node_positions[p][0] + self.nodes[p].size[0] // 2 for p in parents) // len(
                        parents)
                    ideal_x = avg_center_x - w // 2
                    current_x = max(current_x, ideal_x)

                if current_x + w >= env.width:
                    current_x = start_x
                    current_y += max_height_in_tier + y_spacing
                    max_height_in_tier = 0

                env.place_building(building, current_x, current_y, Direction.UP)
                self.node_positions[nid] = (current_x, current_y)

                max_height_in_tier = max(max_height_in_tier, h)
                current_x += w + min_x_spacing

            current_y += max_height_in_tier + y_spacing

    def _a_star_route(self, env: GridMap, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[
        List[Tuple[int, int]]]:
        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        frontier = []
        heapq.heappush(frontier, (0, start))
        came_from = {start: None}
        g_score = {start: 0}

        while frontier:
            current = heapq.heappop(frontier)[1]
            if current == goal: break
            x, y = current

            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = x + dx, y + dy
                if not env.is_in_bounds(nx, ny): continue

                cell = env._get_cell(nx, ny)
                is_crossable = False

                if cell is not None and (nx, ny) != goal and (nx, ny) != start:
                    if type(cell).__name__ == "SystemBBelt":
                        move_dir = Direction.RIGHT if nx > x else Direction.LEFT if nx < x else Direction.DOWN if ny > y else Direction.UP
                        belt_out_dir = getattr(cell, 'direction', Direction.RIGHT)

                        # 安全获取该网格的接收方向
                        belt_in_dir = getattr(cell, 'in_dir', None)
                        if belt_in_dir is None:
                            belt_in_dir = Direction.LEFT if belt_out_dir == Direction.RIGHT else Direction.RIGHT if belt_out_dir == Direction.LEFT else Direction.DOWN if belt_out_dir == Direction.UP else Direction.UP

                        # 【核心防破坏逻辑】：判断这是否是一根直行皮带
                        # 如果是转弯皮带，严禁跨越！跨越会导致该弯道被直接抹除并替换为交叉器。
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
                            # 仅允许对直行的传送带进行【垂直十字交叉】
                            if move_dir in [Direction.UP, Direction.DOWN] and belt_out_dir in [Direction.LEFT,
                                                                                               Direction.RIGHT]:
                                is_crossable = True
                            elif move_dir in [Direction.LEFT, Direction.RIGHT] and belt_out_dir in [Direction.UP,
                                                                                                    Direction.DOWN]:
                                is_crossable = True

                    if not is_crossable:
                        continue

                        # 交叉惩罚(5)保证非必要不交叉；拐弯惩罚(2)保证皮带尽可能走直线
                cost_step = 5 if is_crossable else 1
                turn_penalty = 0
                if came_from[current] is not None:
                    px, py = came_from[current]
                    if (x - px, y - py) != (nx - x, ny - y): turn_penalty = 2

                new_cost = g_score[current] + cost_step + turn_penalty

                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    priority = new_cost + heuristic((nx, ny), goal)
                    heapq.heappush(frontier, (priority, (nx, ny)))
                    came_from[(nx, ny)] = current

        path = []
        if goal in came_from:
            curr = goal
            while curr != start:
                path.append(curr)
                curr = came_from[curr]
            path.append(start)
            path.reverse()
            return path
        return None

    def _route_connections(self, env: GridMap):
        routing_tasks = []

        # 1. 任务构建
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

        # 2. 端口分配
        for nid, b in self.nodes.items():
            ax, ay = self.node_positions[nid]
            w, h = b.size
            incoming = [t for t in routing_tasks if t['dst_type'] == 'node' and t['dst'] == nid]
            incoming.sort(key=lambda t: self.node_positions[t['src']][0] if t['src_type'] == 'node' else ax)
            for idx, t in enumerate(incoming):
                t['end_port'] = (ax + (idx % w), ay - 1)

            outgoing = [t for t in routing_tasks if t['src_type'] == 'node' and t['src'] == nid]
            outgoing.sort(key=lambda t: self.node_positions[t['dst']][0] if t['dst_type'] == 'node' else ax)
            for idx, t in enumerate(outgoing):
                t['start_port'] = (ax + (idx % w), ay + h)

        for t in routing_tasks:
            if t['src_type'] == 'ext_in':
                t['start_port'] = (t['end_port'][0], 0)
                self.generated_inputs[t['mat']].append(t['start_port'])
            if t['dst_type'] == 'ext_out':
                t['end_port'] = (t['start_port'][0], env.height - 1)
                self.generated_outputs[t['mat']].append(t['end_port'])

        # 4. A* 智能排线 (追加物理碰撞强制覆盖逻辑)
        for t in routing_tasks:
            start, end = t['start_port'], t['end_port']
            path = self._a_star_route(env, start, end)

            if path:
                for i in range(len(path)):
                    px, py = path[i]

                    # 确定前进方向 (out_dir)
                    if i + 1 < len(path):
                        nx, ny = path[i + 1]
                        out_dir = Direction.RIGHT if nx > px else Direction.LEFT if nx < px else Direction.DOWN if ny > py else Direction.UP
                    else:
                        out_dir = Direction.DOWN

                    # 确定来车方向 (in_dir)
                    if i > 0:
                        prev_x, prev_y = path[i - 1]
                        in_dir = Direction.LEFT if px > prev_x else Direction.RIGHT if px < prev_x else Direction.UP if py > prev_y else Direction.DOWN
                    else:
                        in_dir = Direction.UP

                    cell = env._get_cell(px, py)

                    # 【核心修复 1】：无论是普通路径还是 Ext_In/Out 的起点，只要是空地，无条件铺设皮带！
                    if cell is None:
                        comp = get_transport_instance(301)
                        comp.in_dir = in_dir
                        env.place_transport(comp, px, py, out_dir)
                    else:
                        # 如果是预部署好的出入口节点，仅赋予转向属性，满足引擎拦截条件
                        if (px, py) == start or (px, py) == end:
                            cell.in_dir = in_dir
                        # 如果是被交叉穿透的普通皮带
                        elif type(cell).__name__ == "SystemBBelt":
                            # 【核心修复 2】：必须先从物理引擎中彻底超度旧皮带，否则新交叉器会被碰撞拦截
                            if cell in env.transports:
                                env.transports.remove(cell)
                            env.grid[py][px] = None  # 腾出物理网格

                            # 放置新的交叉器
                            comp = get_transport_instance(314)
                            comp.in_dir = in_dir
                            env.place_transport(comp, px, py, Direction.DOWN)
            else:
                print(f"[Warning] Congestion: Unable to route from {start} to {end}")