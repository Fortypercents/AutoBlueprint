from typing import List, Tuple, Optional, Any
from entities.building import Building
from entities.transport import TransportComponent, Direction, Belt, OverflowGate


class GridMap:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        # 核心数据结构：存的是实体对象，None 代表空地
        self.grid: List[List[Optional[Any]]] = [[None for _ in range(width)] for _ in range(height)]

        # 方便我们快速遍历地图上的所有设施，而不需要双重 for 循环扫整个地图
        self.buildings: List[Building] = []
        self.transports: List[TransportComponent] = []

    def is_in_bounds(self, x: int, y: int) -> bool:
        """检查坐标是否越界"""
        return 0 <= x < self.width and 0 <= y < self.height

    def can_place_building(self, building: Building, start_x: int, start_y: int) -> bool:
        """检查从 (start_x, start_y) 开始的 w*h 区域是否都是空地"""
        w, h = building.size
        for y in range(start_y, start_y + h):
            for x in range(start_x, start_x + w):
                if not self.is_in_bounds(x, y) or self.grid[y][x] is not None:
                    return False
        return True

    def place_building(self, building: Building, start_x: int, start_y: int) -> bool:
        """在地图上放置建筑（多占地）"""
        if not self.can_place_building(building, start_x, start_y):
            return False

        w, h = building.size
        # 将这片区域的所有网格都指向这个建筑对象
        for y in range(start_y, start_y + h):
            for x in range(start_x, start_x + w):
                self.grid[y][x] = building

        # 记录其左上角锚点坐标，方便后续扫描
        building.anchor_pos = (start_x, start_y)
        self.buildings.append(building)
        return True

    def get_perimeter_coords(self, building: Building) -> List[Tuple[int, int]]:
        """获取建筑外延一圈的所有相邻坐标"""
        start_x, start_y = building.anchor_pos
        w, h = building.size
        perimeter = []

        # 扫描上下两边缘的上方一排和下方一排
        for x in range(start_x, start_x + w):
            perimeter.append((x, start_y - 1))  # 上边缘
            perimeter.append((x, start_y + h))  # 下边缘

        # 扫描左右两边缘的左侧一排和右侧一排
        for y in range(start_y, start_y + h):
            perimeter.append((start_x - 1, y))  # 左边缘
            perimeter.append((start_x + w, y))  # 右边缘

        # 过滤掉越界的坐标
        return [pos for pos in perimeter if self.is_in_bounds(*pos)]

    def update_connections(self, building: Building):
        """扫描并绑定直连和传送带 (体现我们之前的早测逻辑)"""
        building.reset_ports()  # 清空旧连接
        perimeter = self.get_perimeter_coords(building)

        for px, py in perimeter:
            neighbor = self.grid[py][px]
            if neighbor is None:
                continue

            # 情况 1: 旁边是传送带
            if isinstance(neighbor, TransportComponent):
                # 如果传送带的方向指向当前建筑，则是输入源
                # 这里的逻辑需要根据 neighbor 的 direction 和建筑的相对位置进行向量计算
                pass  # 留给详细实现

            # 情况 2: 旁边是另一个建筑 (Direct Insertion)
            elif isinstance(neighbor, Building):
                # 检查两者的输出和输入是否匹配
                shared_materials = set(building.output_materials.keys()) & set(neighbor.input_materials.keys())
                if shared_materials:
                    building.active_output_ports.append((px, py))
                    neighbor.active_input_ports.append(building.anchor_pos)

    def tick(self):
        """
        模拟工厂的一个时间步 (例如: 1 Tick = 1 秒)。
        分为两个子阶段：1. 机器生产与卸货； 2. 传送带与逻辑门挪动物品。
        """

        # ==========================================
        # 阶段 1: 建筑生产 (Production Phase)
        # ==========================================
        for building in self.buildings:
            # 1. 检查输入库存是否满足生产配方
            can_produce = True
            for mat, required_amount in building.input_materials.items():
                if building.inventory.get(mat, 0) < required_amount:
                    can_produce = False
                    break

            # 2. 执行生产消耗与产出
            if can_produce:
                for mat, amount in building.input_materials.items():
                    building.inventory[mat] -= amount  # 扣除原料

                for mat, amount in building.output_materials.items():
                    # 将产物放入机器的输出缓存区
                    building.output_buffer[mat] = building.output_buffer.get(mat, 0) + amount

            # 3. 将输出缓存区的物品推入管网 (直连建筑 或 传送带)
            self._push_building_outputs(building)

        # ==========================================
        # 阶段 2: 运输网络流转 (Transport Routing Phase)
        # ==========================================
        # 注意：在真实的 2D 网格游戏中，传送带的更新必须“从下游到上游”倒序遍历，
        # 或者使用“双缓冲 (Double Buffering)”，以防止物品在一帧内瞬间移动到底。
        # 这里展示核心的状态转移逻辑：

        for transport in self.transports:
            if transport.current_item is None:
                continue  # 空的传送带直接跳过

            current_x, current_y = transport.pos

            # --- 分支 A: 基础传送带逻辑 ---
            if isinstance(transport, Belt):
                next_x = current_x + transport.direction.value[0]
                next_y = current_y + transport.direction.value[1]

                next_cell = self._get_cell(next_x, next_y)

                # 如果前方是空的传送带，移动物品
                if isinstance(next_cell, Belt) and next_cell.current_item is None:
                    next_cell.next_tick_item = transport.current_item
                    transport.current_item = None

            # --- 分支 B: 溢流门逻辑 (Overflow Gate) ---
            elif isinstance(transport, OverflowGate):
                # 检查前方
                front_x = current_x + transport.direction.value[0]
                front_y = current_y + transport.direction.value[1]
                front_cell = self._get_cell(front_x, front_y)

                # 逻辑：如果前方堵塞 (满了) 或者不是合法的接收端
                if self._is_blocked(front_cell):
                    # 尝试向左右两侧输出
                    left_cell, right_cell = self._get_sides(current_x, current_y, transport.direction)
                    if not self._is_blocked(left_cell):
                        left_cell.next_tick_item = transport.current_item
                        transport.current_item = None
                    elif not self._is_blocked(right_cell):
                        right_cell.next_tick_item = transport.current_item
                        transport.current_item = None
                else:
                    # 前方畅通，正常向前输出
                    front_cell.next_tick_item = transport.current_item
                    transport.current_item = None

        # 统一应用下一帧的状态 (模拟并发更新)
        self._apply_next_tick_states()