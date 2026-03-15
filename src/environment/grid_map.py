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

    # 因为只需要写grid[x][y] is none就可以检测所以不需要can_place辅助
    def place_transport(self, transport: TransportComponent, x: int, y: int, direction: Direction) -> bool:
        """放置普通 1x1 运输元件（传送带、分配器等）"""
        if not self.is_in_bounds(x, y) or self.grid[y][x] is not None:
            return False

        transport.pos = (x, y)
        transport.direction = direction
        transport.current_item = None
        transport.next_tick_item = None

        self.grid[y][x] = transport
        self.transports.append(transport)
        return True

    # 因为只需要写grid[x][y] is none就可以检测所以不需要can_place辅助
    def place_bridge(self, bridge, start_x: int, start_y: int, direction: Direction, span_length: int) -> bool:
        """
        放置传输桥。跨度 span_length 表示中间跨过的格子数。
        例如 span_length=2，起点(0,0)向右，则终点在(3,0)。
        """
        if not (bridge.min_length <= span_length <= bridge.max_length):
            return False

        # 计算终点坐标
        dx, dy = direction.value
        end_x = start_x + dx * (span_length + 1)
        end_y = start_y + dy * (span_length + 1)

        # 检查起点和终点是否合法且为空
        if not self.is_in_bounds(start_x, start_y) or not self.is_in_bounds(end_x, end_y):
            return False
        if self.grid[start_y][start_x] is not None or self.grid[end_y][end_x] is not None:
            return False

        # 记录起点和终点状态
        bridge.pos = (start_x, start_y)
        bridge.end_pos = (end_x, end_y)
        bridge.direction = direction
        bridge.current_item = None
        bridge.next_tick_item = None

        # 将起点和终点都注册到网格中 (指向同一个 Bridge 对象)
        self.grid[start_y][start_x] = bridge
        self.grid[end_y][end_x] = bridge
        self.transports.append(bridge)
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
                nx, ny = px, py
                dx, dy = neighbor.direction.value

                # 计算传送带的“正前方”指向哪个坐标
                target_x = nx + dx
                target_y = ny + dy

                # 获取建筑的实际占地范围
                start_x, start_y = building.anchor_pos
                w, h = building.size

                # 检查 target_x, target_y 是否在建筑内部的网格中
                is_pointing_inside = (start_x <= target_x < start_x + w) and (start_y <= target_y < start_y + h)

                if is_pointing_inside:
                    # 传送带指向建筑内部 -> 这是输入源
                    building.active_input_ports.append((nx, ny))
                else:
                    # 传送带背向或侧向建筑 -> 这是输出目标
                    building.active_output_ports.append((nx, ny))

            # 情况 2: 旁边是另一个建筑 (Direct Insertion)
            elif isinstance(neighbor, Building):
                # 检查两者的输出和输入是否匹配
                shared_materials = set(building.output_materials.keys()) & set(neighbor.input_materials.keys())
                if shared_materials:
                    building.active_output_ports.append((px, py))
                    neighbor.active_input_ports.append(building.anchor_pos)

    # ==========================================
    # Tick 引擎依赖的底层辅助方法 (【已修复缩进错误】)
    # ==========================================
    def _get_cell(self, x: int, y: int):
        if self.is_in_bounds(x, y):
            return self.grid[y][x]
        return None

    def _is_blocked(self, cell) -> bool:
        """检查目标网格是否堵塞（不可接收物品）"""
        if cell is None:
            return True  # 空地不能走
        if isinstance(cell, Building):
            return False  # 简易处理：假设建筑无限吞吐（真实情况应检查其 capacity）
        if isinstance(cell, TransportComponent):
            # 如果下一帧它已经预定了物品，说明堵塞
            return getattr(cell, 'next_tick_item', None) is not None or getattr(cell, 'current_item', None) is not None
        return True

    def _get_sides(self, x: int, y: int, direction: Direction):
        """获取元件的左右两侧坐标 (用于溢流门和分类器)"""
        if direction in (Direction.UP, Direction.DOWN):
            return self._get_cell(x - 1, y), self._get_cell(x + 1, y)
        else:
            return self._get_cell(x, y - 1), self._get_cell(x, y + 1)

    def _apply_next_tick_states(self):
        """将 next_tick_item 固化为 current_item"""
        for transport in self.transports:
            if hasattr(transport, 'next_tick_item') and transport.next_tick_item is not None:
                transport.current_item = transport.next_tick_item
                transport.next_tick_item = None

    def _push_building_outputs(self, building: Building):
        """阶段 1.3: 将建筑产物推上管网"""
        if not hasattr(building, 'output_buffer'):
            building.output_buffer = {}

        for mat, amount in list(building.output_buffer.items()):
            if amount >= 1.0:  # 假设凑齐 1 个整数才能上管网
                # 寻找一个空闲的输出端口
                for out_pos in building.active_output_ports:
                    target_cell = self._get_cell(out_pos[0], out_pos[1])
                    if isinstance(target_cell, TransportComponent) and not self._is_blocked(target_cell):
                        target_cell.next_tick_item = mat  # 物品上管网
                        building.output_buffer[mat] -= 1.0
                        break

    def tick(self):
        """
        模拟工厂的一个时间步 (例如: 1 Tick = 1 秒)。
        分为两个子阶段：1. 机器生产与卸货； 2. 传送带与逻辑门挪动物品。
        """

        # ==========================================
        # 阶段 1: 建筑生产 (Production Phase)
        # ==========================================
        for building in self.buildings:
            # 安全初始化库存字典
            if not hasattr(building, 'inventory'):
                building.inventory = {}
            if not hasattr(building, 'output_buffer'):
                building.output_buffer = {}

            # 【重点新增】：提取机器的生产倍率 (如没有设置则默认 1.0)
            speed = getattr(building, 'production_speed', 1.0)

            # 1. 检查输入库存是否满足生产配方 (计入倍率)
            can_produce = True
            for mat, required_amount in building.input_materials.items():
                if building.inventory.get(mat, 0) < (required_amount * speed):
                    can_produce = False
                    break

            # 2. 执行生产消耗与产出 (计入倍率)
            if can_produce:
                for mat, amount in building.input_materials.items():
                    building.inventory[mat] -= (amount * speed)  # 扣除原料

                for mat, amount in building.output_materials.items():
                    # 将产物放入机器的输出缓存区
                    building.output_buffer[mat] = building.output_buffer.get(mat, 0) + (amount * speed)

            # 3. 将输出缓存区的物品推入管网 (直连建筑 或 传送带)
            self._push_building_outputs(building)

        # ==========================================
        # 阶段 2: 运输网络流转 (Transport Routing Phase)
        # ==========================================
        for transport in self.transports:
            # 【修复点】：检查 hasattr 避免报错
            if getattr(transport, 'current_item', None) is None:
                continue  # 空的传送带直接跳过

            current_x, current_y = transport.pos

            # --- 分支 A: 基础传送带逻辑 ---
            if isinstance(transport, Belt):
                next_x = current_x + transport.direction.value[0]
                next_y = current_y + transport.direction.value[1]

                next_cell = self._get_cell(next_x, next_y)

                # 如果前方是空的传送带，移动物品
                if isinstance(next_cell, Belt) and getattr(next_cell, 'current_item', None) is None:
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

            # --- 分支 C: 传输桥逻辑 (Bridge) (【已修复嵌套错误！】) ---
            # 引入 Bridge 需要判断物品当前是在起点还是终点
            elif transport.__class__.__name__ == "Bridge":
                # 只有当计算坐标恰好在桥的【起点】时，才触发跨越传送
                if (current_x, current_y) == transport.pos:
                    # 物品瞬间跨越到终点的前方一格
                    dx, dy = transport.direction.value
                    end_x, end_y = transport.end_pos
                    output_x = end_x + dx
                    output_y = end_y + dy

                    output_cell = self._get_cell(output_x, output_y)
                    if not self._is_blocked(output_cell):
                        output_cell.next_tick_item = transport.current_item
                        transport.current_item = None

        # 统一应用下一帧的状态 (模拟并发更新)
        self._apply_next_tick_states()