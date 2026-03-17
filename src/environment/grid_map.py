from typing import List, Tuple, Optional, Any
from entities.building import Building
from entities.transport import TransportComponent, Direction, Belt, OverflowGate, LogicRouter


class GridMap:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.grid: List[List[Optional[Any]]] = [[None for _ in range(width)] for _ in range(height)]
        self.buildings: List[Building] = []
        self.transports: List[TransportComponent] = []

    def is_in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def can_place_building(self, building: Building, start_x: int, start_y: int) -> bool:
        w, h = building.size
        for y in range(start_y, start_y + h):
            for x in range(start_x, start_x + w):
                if not self.is_in_bounds(x, y) or self.grid[y][x] is not None:
                    return False
        return True

    def place_building(self, building: Building, start_x: int, start_y: int) -> bool:
        if not self.can_place_building(building, start_x, start_y):
            return False
        w, h = building.size
        for y in range(start_y, start_y + h):
            for x in range(start_x, start_x + w):
                self.grid[y][x] = building
        building.anchor_pos = (start_x, start_y)
        self.buildings.append(building)
        return True

    def place_transport(self, transport: TransportComponent, x: int, y: int, direction: Direction) -> bool:
        if not self.is_in_bounds(x, y) or self.grid[y][x] is not None:
            return False
        transport.pos = (x, y)
        transport.direction = direction
        transport.current_item = None
        transport.next_tick_item = None
        self.grid[y][x] = transport
        self.transports.append(transport)
        return True

    def place_bridge(self, bridge, start_x: int, start_y: int, direction: Direction, span_length: int) -> bool:
        if not (bridge.min_length <= span_length <= bridge.max_length):
            return False
        dx, dy = direction.value
        end_x = start_x + dx * (span_length + 1)
        end_y = start_y + dy * (span_length + 1)
        if not self.is_in_bounds(start_x, start_y) or not self.is_in_bounds(end_x, end_y):
            return False
        if self.grid[start_y][start_x] is not None or self.grid[end_y][end_x] is not None:
            return False
        bridge.pos = (start_x, start_y)
        bridge.end_pos = (end_x, end_y)
        bridge.direction = direction
        bridge.current_item = None
        bridge.next_tick_item = None
        self.grid[start_y][start_x] = bridge
        self.grid[end_y][end_x] = bridge
        self.transports.append(bridge)
        return True

    def get_perimeter_coords(self, building: Building) -> List[Tuple[int, int]]:
        start_x, start_y = building.anchor_pos
        w, h = building.size
        perimeter = []
        for x in range(start_x, start_x + w):
            perimeter.append((x, start_y - 1))
            perimeter.append((x, start_y + h))
        for y in range(start_y, start_y + h):
            perimeter.append((start_x - 1, y))
            perimeter.append((start_x + w, y))
        return [pos for pos in perimeter if self.is_in_bounds(*pos)]

    def update_connections(self, building: Building):
        building.reset_ports()
        perimeter = self.get_perimeter_coords(building)
        for px, py in perimeter:
            neighbor = self.grid[py][px]
            if neighbor is None:
                continue
            if isinstance(neighbor, TransportComponent):
                nx, ny = px, py
                dx, dy = neighbor.direction.value
                target_x = nx + dx
                target_y = ny + dy
                start_x, start_y = building.anchor_pos
                w, h = building.size
                is_pointing_inside = (start_x <= target_x < start_x + w) and (start_y <= target_y < start_y + h)
                if is_pointing_inside:
                    building.active_input_ports.append((nx, ny))
                else:
                    building.active_output_ports.append((nx, ny))
            elif isinstance(neighbor, Building):
                shared_materials = set(building.output_materials.keys()) & set(neighbor.input_materials.keys())
                if shared_materials:
                    building.active_output_ports.append((px, py))
                    neighbor.active_input_ports.append(building.anchor_pos)

    def _get_cell(self, x: int, y: int):
        if self.is_in_bounds(x, y):
            return self.grid[y][x]
        return None

    def _is_blocked(self, cell) -> bool:
        if cell is None:
            return True
        if isinstance(cell, Building):
            return False
        if isinstance(cell, TransportComponent):
            return getattr(cell, 'next_tick_item', None) is not None or getattr(cell, 'current_item', None) is not None
        return True

    def _is_valid_router_output(self, cell, from_x, from_y) -> bool:
        """结构校验：检查目标格子是否为合法的输出方向（仅校验连接关系，不再校验是否满载）"""
        if not isinstance(cell, TransportComponent):
            return False
        if isinstance(cell, Belt):
            dx = cell.pos[0] - from_x
            dy = cell.pos[1] - from_y
            if cell.direction.value == (-dx, -dy):
                return False
        return True

    def _get_sides(self, x: int, y: int, direction: Direction):
        if direction in (Direction.UP, Direction.DOWN):
            return self._get_cell(x - 1, y), self._get_cell(x + 1, y)
        else:
            return self._get_cell(x, y - 1), self._get_cell(x, y + 1)

    def _apply_next_tick_states(self):
        for transport in self.transports:
            if hasattr(transport, 'next_tick_item') and transport.next_tick_item is not None:
                transport.current_item = transport.next_tick_item
                transport.next_tick_item = None

    # ==========================================
    # 核心流体力学引擎 (智能合并与分配)
    # ==========================================
    def _push_to_cell(self, target_cell, mat, amt) -> float:
        """底层物流接口：尝试将最多 amt 数量的 mat 挤进 target_cell 中，返回实际挤入的数量"""
        if not isinstance(target_cell, TransportComponent):
            return 0.0

        target_item = getattr(target_cell, 'next_tick_item', None) or getattr(target_cell, 'current_item', None)
        capacity = max(12.0, getattr(target_cell, 'max_capacity', 12.0))

        # 目标为空，直接放入
        if target_item is None:
            push_amt = min(amt, capacity)
            target_cell.next_tick_item = (mat, push_amt)
            return push_amt

        # 解析目标的物资和数量 (向下兼容单体枚举)
        t_mat = target_item[0] if isinstance(target_item, tuple) else target_item
        t_amt = target_item[1] if isinstance(target_item, tuple) else 1.0

        # 种类相同，进行空间堆叠合并
        if t_mat == mat:
            space_left = capacity - t_amt
            if space_left > 0:
                push_amt = min(amt, space_left)
                target_cell.next_tick_item = (mat, t_amt + push_amt)
                return push_amt

        return 0.0

    def _push_building_outputs(self, building: Building):
        """阶段 1.3: 将建筑产物推上管网"""
        if not hasattr(building, 'output_buffer'):
            building.output_buffer = {}

        for mat, amount in list(building.output_buffer.items()):
            if amount >= 1.0:
                for out_pos in building.active_output_ports:
                    target_cell = self._get_cell(out_pos[0], out_pos[1])
                    pushed = self._push_to_cell(target_cell, mat, amount)
                    if pushed > 0:
                        building.output_buffer[mat] -= pushed
                        amount -= pushed
                    if amount < 1.0:
                        break

    def _try_move_or_merge(self, transport: TransportComponent, target_cell) -> bool:
        """基础传送带移动逻辑：尝试将当前拥有的物资全部推向下一格"""
        if transport.current_item is None: return False

        mat = transport.current_item[0] if isinstance(transport.current_item, tuple) else transport.current_item
        amt = transport.current_item[1] if isinstance(transport.current_item, tuple) else 1.0

        pushed = self._push_to_cell(target_cell, mat, amt)
        if pushed > 0:
            if amt - pushed > 0:
                transport.current_item = (mat, amt - pushed)
            else:
                transport.current_item = None
            return True
        return False

    def _distribute_evenly(self, transport: TransportComponent, target_cells: List) -> bool:
        """分配器核心：将携带的物品打散，每次仅分配 1 个单位，均匀轮询塞给有效的输出口"""
        if getattr(transport, 'current_item', None) is None or not target_cells:
            return False

        mat = transport.current_item[0] if isinstance(transport.current_item, tuple) else transport.current_item
        amt = transport.current_item[1] if isinstance(transport.current_item, tuple) else 1.0

        # 分配器内置状态机，记忆上一次分配的出口索引，确保真正的 Round-Robin
        if not hasattr(transport, 'rr_index'):
            transport.rr_index = 0

        consecutive_failures = 0
        moved_any = False

        # 如果所有口子连 1 个物品都塞不进去了，退出死循环
        while amt > 0 and consecutive_failures < len(target_cells):
            cell = target_cells[transport.rr_index]

            # 关键：每次最多只向该出口挤入 1.0 的单位，而不是全塞进去！
            push_val = min(amt, 1.0)
            pushed = self._push_to_cell(cell, mat, push_val)

            if pushed > 0:
                amt -= pushed
                consecutive_failures = 0
                moved_any = True
            else:
                consecutive_failures += 1

            # 轮询至下一个出口
            transport.rr_index = (transport.rr_index + 1) % len(target_cells)

        # 保存尚未分配完的物资 (分配不完卡在分配器里等下一帧)
        if amt > 0:
            transport.current_item = (mat, amt)
        else:
            transport.current_item = None

        return moved_any

    def tick(self):
        # ==========================================
        # 阶段 1: 建筑内部生产 (Production Phase)
        # ==========================================
        for building in self.buildings:
            if not hasattr(building, 'inventory'): building.inventory = {}
            if not hasattr(building, 'output_buffer'): building.output_buffer = {}

            speed = getattr(building, 'production_speed', 1.0)
            can_produce = True
            for mat, required_amount in building.input_materials.items():
                if building.inventory.get(mat, 0) < (required_amount * speed):
                    can_produce = False
                    break

            if can_produce:
                for mat, amount in building.input_materials.items():
                    building.inventory[mat] -= (amount * speed)
                for mat, amount in building.output_materials.items():
                    building.output_buffer[mat] = building.output_buffer.get(mat, 0) + (amount * speed)

            # 🚨 核心修复：删除/注释掉这里的 self._push_building_outputs(building)

        # ==========================================
        # 阶段 2: 运输网络流转 (支持智能分流与合并)
        # ==========================================
        for transport in reversed(self.transports):
            if getattr(transport, 'current_item', None) is None:
                continue

            current_x, current_y = transport.pos

            # --- 分支 A: 基础传送带 ---
            if isinstance(transport, Belt):
                next_x = current_x + transport.direction.value[0]
                next_y = current_y + transport.direction.value[1]
                self._try_move_or_merge(transport, self._get_cell(next_x, next_y))

            # --- 分支 B: 分配器 (LogicRouter) ---
            elif type(transport) is LogicRouter:
                dx, dy = transport.direction.value
                front_cell = self._get_cell(current_x + dx, current_y + dy)
                left_cell, right_cell = self._get_sides(current_x, current_y, transport.direction)

                valid_targets = []
                if self._is_valid_router_output(right_cell, current_x, current_y): valid_targets.append(right_cell)
                if self._is_valid_router_output(left_cell, current_x, current_y): valid_targets.append(left_cell)
                if self._is_valid_router_output(front_cell, current_x, current_y): valid_targets.append(front_cell)

                self._distribute_evenly(transport, valid_targets)

            # --- 分支 C: 溢流门 (Overflow Gate) ---
            elif isinstance(transport, OverflowGate):
                front_cell = self._get_cell(current_x + transport.direction.value[0],
                                            current_y + transport.direction.value[1])
                left_cell, right_cell = self._get_sides(current_x, current_y, transport.direction)

                if self._is_valid_router_output(front_cell, current_x, current_y):
                    self._try_move_or_merge(transport, front_cell)

                if transport.current_item is not None:
                    valid_side_targets = []
                    if self._is_valid_router_output(left_cell, current_x, current_y): valid_side_targets.append(
                        left_cell)
                    if self._is_valid_router_output(right_cell, current_x, current_y): valid_side_targets.append(
                        right_cell)
                    self._distribute_evenly(transport, valid_side_targets)

            # --- 分支 D: 传输桥 (Bridge) ---
            elif transport.__class__.__name__ == "Bridge":
                if (current_x, current_y) == transport.pos:
                    dx, dy = transport.direction.value
                    self._try_move_or_merge(transport,
                                            self._get_cell(transport.end_pos[0] + dx, transport.end_pos[1] + dy))

        # ==========================================
        # 阶段 3: 将新产物推上管网 (修复复制Bug的关键点)
        # ==========================================
        # 必须在所有传送带旧物品移动完、腾出空位后，再把新一帧的产物放上流水线！
        for building in self.buildings:
            self._push_building_outputs(building)

        # ==========================================
        # 阶段 4: 应用下一帧状态
        # ==========================================
        self._apply_next_tick_states()