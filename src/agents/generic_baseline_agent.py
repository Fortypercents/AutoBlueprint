import math
import heapq
from collections import deque, defaultdict
from typing import List, Dict, Tuple, Optional

from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction
from environment.grid_map import GridMap
from entities.material import MaterialType

# 导入抽离的公用配方工具
from agents.utils import get_recipe_catalog


class GenericBaselineAgent:
    """
    泛用型基线自动布局代理 (完全独立版：无 BaseAgent 依赖，内置 A* 算法)
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        # 不再调用 super().__init__()
        self.target_outputs_dict = target_outputs
        self.available_inputs = available_inputs
        self.nodes = {}
        self.edges = []
        self.required_buildings = []

    def optimize(self, env: GridMap, external_in: Dict[MaterialType, List[Tuple[int, int]]] = None,
                 external_out: Dict[MaterialType, List[Tuple[int, int]]] = None):
        print("\n【GenericBaselineAgent】开始按目标产量规划产线 (独立运行模式)...")
        self.external_in = external_in or {}
        self.external_out = external_out or {}

        self._calculate_ratios_and_instances()
        self._build_instance_graph()
        tiers = self._calculate_tiers()
        self._layout_grid(env, tiers)
        self._route_connections(env)

    def _calculate_ratios_and_instances(self):
        demand_queue = {k: v for k, v in self.target_outputs_dict.items()}
        # 使用 utils.py 提供的解耦配方映射
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
                for c_idx, c_nid in enumerate(c_list):
                    self.edges.append({'src': p_list[c_idx % len(p_list)], 'dst': c_nid, 'mat': mat})

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
        y_spacing = 7  # 保持纵向有足够的布线走廊
        x_spacing = 0  # 【核心修改】：取消同行建筑的水平间隔，让建筑紧密贴合
        current_y = start_y
        max_depth = max(tiers.keys()) if tiers else 0

        for tier_level in range(max_depth + 1):
            nodes_in_tier = tiers.get(tier_level, [])
            current_x, max_height_in_tier = start_x, 0

            for nid in nodes_in_tier:
                building = self.nodes[nid]

                # 检测是否即将越界 (保留换行保护逻辑)
                if current_x + building.size[0] >= env.width:
                    current_x = start_x
                    current_y += max_height_in_tier + y_spacing
                    max_height_in_tier = 0

                env.place_building(building, current_x, current_y, Direction.UP)

                if not hasattr(building, 'anchor_pos'):
                    raise RuntimeError(f"❌ 地图尺寸严重不足！无法在 ({current_x}, {current_y}) 放置 {building.name}")

                max_height_in_tier = max(max_height_in_tier, building.size[1])
                # 紧密排列：下一个建筑紧贴着当前建筑放置
                current_x += building.size[0] + x_spacing

            # 一层全部放完后，Y轴推进到下一个 Tier 的初始位置
            current_y += max_height_in_tier + y_spacing

    def _get_absolute_ports(self, building) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        ax, ay = building.anchor_pos
        w, h = building.size
        in_port = (ax + w // 2, ay - 1)
        out_port = (ax + w // 2, ay + h)
        return in_port, out_port

    def _a_star_route(self, env: GridMap, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[
        List[Tuple[int, int]]]:
        """完整重写并内置的 A* 寻路算法（已包含起点回归修复）"""

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
                if env.grid[ny][nx] is not None and (nx, ny) != goal: continue

                new_cost = g_score[current] + 1
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
            path.append(start)  # [修复点] 包含起点
            path.reverse()
            return path
        return None

    def _route_connections(self, env: GridMap):
        def _draw_belt_path(start, end):
            # 恢复最紧凑的极限寻路，不使用外扩缓冲带
            path = self._a_star_route(env, start, end)

            if path:
                for i in range(len(path)):
                    px, py = path[i]
                    if i + 1 < len(path):
                        nx, ny = path[i + 1]
                        d = Direction.RIGHT if nx > px else Direction.LEFT if nx < px else Direction.DOWN if ny > py else Direction.UP
                    else:
                        if i > 0:
                            prev_x, prev_y = path[i - 1]
                            d = Direction.RIGHT if px > prev_x else Direction.LEFT if px < prev_x else Direction.DOWN if py > prev_y else Direction.UP
                        else:
                            d = Direction.DOWN

                    if env._get_cell(px, py) is None:
                        # 【核心优化】：利用特殊组件掩盖转向，节约占地面积
                        if (px, py) == start:
                            # 机器输出口 / 路径起点：放置分配器 (Splitter ID: 311)
                            env.place_transport(get_transport_instance(311), px, py, d)
                        elif (px, py) == end:
                            # 机器输入口 / 路径终点：放置汇流器 (Merger ID: 312)，统一朝下喂入
                            env.place_transport(get_transport_instance(312), px, py, Direction.DOWN)
                        else:
                            # 中间路径：放置普通传送带 (Belt ID: 301)
                            env.place_transport(get_transport_instance(301), px, py, d)
            else:
                print(f"⚠️ 拥堵警告: 无法为 {start} -> {end} 找到无障碍路径")

        # 1. 内网铺设 (机器 -> 机器)
        for edge in self.edges:
            src_b, dst_b = self.nodes[edge['src']], self.nodes[edge['dst']]
            _, out_port = self._get_absolute_ports(src_b)
            in_port, _ = self._get_absolute_ports(dst_b)
            _draw_belt_path(out_port, in_port)

        # 2. 外网输入口接入 (External In -> 机器输入口)
        for mat, in_ports in self.external_in.items():
            consumers = [b for b in self.required_buildings if mat in b.input_materials]
            for i, b in enumerate(consumers):
                if i < len(in_ports):
                    in_port, _ = self._get_absolute_ports(b)
                    _draw_belt_path(in_ports[i], in_port)

        # 3. 外网输出口拉出 (机器输出口 -> External Out)
        for mat, out_ports in self.external_out.items():
            producers = [b for b in self.required_buildings if mat in b.output_materials]
            for i, b in enumerate(producers):
                if i < len(out_ports):
                    _, out_port = self._get_absolute_ports(b)
                    _draw_belt_path(out_port, out_ports[i])