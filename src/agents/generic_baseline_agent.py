import math
import heapq
from collections import deque, defaultdict
from typing import List, Dict, Tuple, Optional, Set

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

        # [新增] 区域块划分
        self.blocks: List[List[int]] = []
        # [新增] 全局已占用端口记录，用于浮动引脚分配
        self.used_ports: Set[Tuple[int, int]] = set()

        self.generated_inputs = defaultdict(list)
        self.generated_outputs = defaultdict(list)

    def optimize(self, env: GridMap):
        print("\n[GenericBaselineAgent] Starting Wirelength-Driven Block-Level P&R...")

        self._calculate_ratios_and_instances()
        self._build_instance_graph()

        # 1. 以最高级建筑为核心，划分 Block
        self._partition_blocks()

        # 2. 按 Block 逐级底向上放置
        self._layout_blocks(env)

        # 3. 浮动引脚分配与最短距离连线
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

    def _partition_blocks(self):
        """【算法 1】：基于最高级节点辐射划分 Block"""
        # 寻找终端建筑 (最高级)
        root_nids = [nid for nid, b in self.nodes.items() if
                     any(mat in self.target_outputs_dict for mat in b.output_materials)]

        assigned_nodes = set()
        self.blocks = []

        # 从最高级建筑开始 BFS，寻找为其服务的所有上游建筑
        for root in root_nids:
            if root in assigned_nodes: continue
            current_block = []
            queue = deque([root])

            while queue:
                curr = queue.popleft()
                if curr not in assigned_nodes:
                    assigned_nodes.add(curr)
                    current_block.append(curr)
                    # 寻找为当前建筑供货的提供者
                    providers = [e['src'] for e in self.edges if e['dst'] == curr]
                    queue.extend(providers)

            self.blocks.append(current_block)

        # 兜底：处理可能的未连通孤岛
        leftovers = [n for n in self.nodes if n not in assigned_nodes]
        if leftovers: self.blocks.append(leftovers)

    def _layout_blocks(self, env: GridMap):
        """【算法 2】：Block 独立规划，最低级优先 (Bottom-Up)"""
        start_x, start_y = 3, 5
        y_spacing = 7
        min_x_spacing = 3
        block_spacing = 6

        current_block_x = start_x

        # 计算全局深度 (0 为最低级的原材料加工厂)
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

        for block_nodes in self.blocks:
            # 将 Block 内的节点按深度分层
            tiers = defaultdict(list)
            for nid in block_nodes:
                tiers[depths[nid]].append(nid)

            max_depth = max(tiers.keys()) if tiers else 0
            current_y = start_y
            max_width_in_block = 0

            # 从最低级 (Tier 0) 开始放置，逐级向上
            for tier_level in range(max_depth + 1):
                nodes_in_tier = tiers.get(tier_level, [])
                tier_x = current_block_x
                max_height_in_tier = 0

                for nid in nodes_in_tier:
                    building = self.nodes[nid]
                    w, h = building.size

                    # 尝试根据上游建筑(如果有)对齐重心
                    parents = [e['src'] for e in self.edges if e['dst'] == nid and e['src'] in self.node_positions]
                    if parents:
                        avg_center_x = sum(
                            self.node_positions[p][0] + self.nodes[p].size[0] // 2 for p in parents) // len(parents)
                        ideal_x = avg_center_x - w // 2
                        tier_x = max(tier_x, ideal_x)

                    # 换行保护
                    if tier_x + w >= env.width:
                        tier_x = current_block_x
                        current_y += max_height_in_tier + y_spacing
                        max_height_in_tier = 0

                    env.place_building(building, tier_x, current_y, Direction.UP)
                    self.node_positions[nid] = (tier_x, current_y)

                    max_height_in_tier = max(max_height_in_tier, h)
                    max_width_in_block = max(max_width_in_block, tier_x + w - current_block_x)
                    tier_x += w + min_x_spacing

                current_y += max_height_in_tier + y_spacing

            # 下一个 Block 的起始 X 坐标
            current_block_x += max_width_in_block + block_spacing

    def _get_available_ports(self, nid: int, is_input: bool) -> List[Tuple[int, int]]:
        """获取建筑尚未被占用的合法端口"""
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
        """【算法 3】：多源多目标 A* 最短路径 (无附加扣分)"""

        # 启发函数：到任意目标的最短距离
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

                        # 仅允许跨越直行皮带
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

                        # 【目标变更】：纯粹的线长驱动，不添加任何惩罚。每走一格代价恒为 1。
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

        # 收集任务
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
            # 【浮动引脚获取】：取目标建筑所有未被占用的合法端口交由 A* 抉择
            starts, goals = [], []

            if t['src_type'] == 'node':
                starts = self._get_available_ports(t['src'], is_input=False)
            else:
                # 外部输入：允许从地图顶部任何合理的 X 坐标下放
                dst_x = self.node_positions[t['dst']][0]
                starts = [(x, 0) for x in range(max(0, dst_x - 5), min(env.width, dst_x + 8))]

            if t['dst_type'] == 'node':
                goals = self._get_available_ports(t['dst'], is_input=True)
            else:
                # 外部输出：允许拉到地图底部合理的 X 坐标
                src_x = self.node_positions[t['src']][0]
                goals = [(x, env.height - 1) for x in range(max(0, src_x - 5), min(env.width, src_x + 8))]

            if not starts or not goals:
                print(f"[Error] No available ports for task: {t}")
                continue

            # 多源多目标寻路，算法自动取最短解
            path = self._a_star_route_multi(env, starts, goals)

            if path:
                start_port = path[0]
                end_port = path[-1]

                # 标记被选中的实体端口为已占用 (外部全局端口不占用)
                if t['src_type'] == 'node': self.used_ports.add(start_port)
                if t['dst_type'] == 'node': self.used_ports.add(end_port)

                if t['src_type'] == 'ext_in': self.generated_inputs[t['mat']].append(start_port)
                if t['dst_type'] == 'ext_out': self.generated_outputs[t['mat']].append(end_port)

                # 执行物理铺设
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
                            if cell in env.transports:
                                env.transports.remove(cell)
                            env.grid[py][px] = None

                            comp = get_transport_instance(314)
                            comp.in_dir = in_dir
                            env.place_transport(comp, px, py, Direction.DOWN)
            else:
                print(f"[Warning] Congestion: Unable to route optimally for {t}")