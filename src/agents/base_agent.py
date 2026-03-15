from typing import Dict, List, Tuple, Optional
import math
import heapq
from entities.material import MaterialType
from entities.building import Building
from entities.registry import get_building_instance, BUILDING_CATALOG, get_transport_instance
from entities.transport import Direction, Belt
from environment.grid_map import GridMap


class BaseAgent:
    """
    蓝图生成智能体的基类。
    负责：
    1. 根据目标产物反推所需的建筑数量与原料配比 (配比最优化)。
    2. 提供评估蓝图好坏的适应度函数 (最小化占地面积和传送带消耗)。
    3. 提供基础的自动寻路算法 (A*) 用于连接建筑之间的物流。
    """

    def __init__(self, target_outputs: Dict[MaterialType, float]):
        """
        :param target_outputs: 期望的最终产物及每Tick的产量要求。例如 {MaterialType.IRON_PLATE: 2.0}
        """
        self.target_outputs = target_outputs
        self.required_buildings: List[Building] = []
        self.raw_material_inputs: Dict[MaterialType, float] = {}

        # 构建反向查找表：哪种产物由哪个建筑生产
        self.recipe_lookup = self._build_recipe_lookup()

    def _build_recipe_lookup(self) -> Dict[MaterialType, int]:
        """内部方法：建立 产物 -> 建筑ID 的映射关系"""
        lookup = {}
        for b_id, building in BUILDING_CATALOG.items():
            for out_mat in building.output_materials:
                lookup[out_mat] = b_id
        return lookup

    def calculate_production_chain(self):
        """
        核心功能 1：根据产物需求反推输入的原料配比，并实例化所需的最少建筑数量。
        使用广度优先搜索 (BFS) 的思路向后反推生产链。
        """
        demand_queue = self.target_outputs.copy()
        self.required_buildings = []
        self.raw_material_inputs = {}

        while demand_queue:
            mat, amount = demand_queue.popitem()

            if mat not in self.recipe_lookup:
                # 如果没有建筑能生产该物质，说明它已经是处于最底层的基础原料 (如 IRON_ORE)
                self.raw_material_inputs[mat] = self.raw_material_inputs.get(mat, 0) + amount
                continue

            # 查表得到生产该物质的建筑ID
            b_id = self.recipe_lookup[mat]
            proto_building = BUILDING_CATALOG[b_id]

            # 考虑建筑的基础生产倍率
            speed = getattr(proto_building, 'production_speed', 1.0)
            production_rate = proto_building.output_materials[mat] * speed

            # 计算需要几个这样的建筑 (向上取整)
            num_buildings = math.ceil(amount / production_rate)

            for _ in range(num_buildings):
                # 利用工厂方法获取深拷贝的独立实体
                new_building = get_building_instance(b_id)
                self.required_buildings.append(new_building)

            # 将该建筑的输入原料需求加入队列，继续向上游反推
            for in_mat, in_amount in proto_building.input_materials.items():
                # 实际需要的上游原料数量，需按要求的比例精确折算
                total_in_needed = (in_amount * speed) * (amount / production_rate)
                demand_queue[in_mat] = demand_queue.get(in_mat, 0) + total_in_needed

        print("\n【Agent 生产配比规划完成】")
        print(f" -> 目标产出: {self.target_outputs}")
        print(f" -> 最优原料输入需求: {self.raw_material_inputs}")
        print(f" -> 共需放置 {len(self.required_buildings)} 个建筑设施。\n")

    def evaluate_layout(self, env: GridMap) -> float:
        """
        核心功能 2：评估当前地图上的蓝图质量。
        返回适应度分数 (Fitness)，分数越低越好。
        优化目标：最小化占地面积(Bounding Box) + 最小化传送带数量(鼓励直连)。
        """
        if not env.buildings:
            return float('inf')

        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = 0, 0

        # 扫描所有建筑以计算包围盒 (Bounding Box)
        for b in env.buildings:
            ax, ay = b.anchor_pos
            w, h = b.size
            min_x = min(min_x, ax)
            min_y = min(min_y, ay)
            max_x = max(max_x, ax + w)
            max_y = max(max_y, ay + h)

        # 蓝图整体占地面积
        area = (max_x - min_x) * (max_y - min_y)

        # 统计地图上的传送带等物流组件数量
        belt_count = len(env.transports)

        # 分数计算公式：占地面积 + (传送带数量 * 惩罚系数)
        # 如果 Agent 聪明地将两个建筑贴在一起触发 Direct Insertion，belt_count 就会减少，得分就会更好
        fitness = area + (belt_count * 1.5)

        return fitness

    def a_star_route(self, env: GridMap, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[
        List[Tuple[int, int]]]:
        """
        核心功能 3：集成的 A* 寻路算法，用于在复杂环境中为两个端口自动连接传送带。
        """

        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        frontier = []
        heapq.heappush(frontier, (0, start))
        came_from = {start: None}
        g_score = {start: 0}

        while frontier:
            current = heapq.heappop(frontier)[1]

            if current == goal:
                break

            x, y = current
            # 上下左右四个方向
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = x + dx, y + dy

                # 1. 越界检测
                if not env.is_in_bounds(nx, ny):
                    continue

                # 2. 碰撞检测：如果是实体(建筑或其他未连通的传送带)，则为障碍物
                # 允许目标点(goal)存在建筑，因为我们要把传送带对准它
                if env.grid[ny][nx] is not None and (nx, ny) != goal:
                    continue

                new_cost = g_score[current] + 1
                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    priority = new_cost + heuristic((nx, ny), goal)
                    heapq.heappush(frontier, (priority, (nx, ny)))
                    came_from[(nx, ny)] = current

        # 回溯并生成路径
        path = []
        if goal in came_from:
            curr = goal
            while curr != start:
                path.append(curr)
                curr = came_from[curr]
            path.reverse()
            return path
        return None

    def optimize(self, env: GridMap):
        """
        执行具体的布局优化算法（随机搜索/模拟退火/遗传算法/强化学习）。
        交由继承了 BaseAgent 的具体子类 (如 RLAgent, AnnealingAgent) 来实现具体的策略。
        """
        raise NotImplementedError("智能体子类必须实现 optimize 方法以执行布局搜索和生成。")