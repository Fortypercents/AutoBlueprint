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
        if self._is_blocked(cell):
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

    def _push_building_outputs(self, building: Building):
        """阶段 1.3: 将建筑产物推上管网 (支持自动打包合并)"""
        if not hasattr(building, 'output_buffer'):
            building.output_buffer = {}

        for mat, amount in list(building.output_buffer.items()):
            if amount >= 1.0:
                for out_pos in building.active_output_ports:
                    target_cell = self._get_cell(out_pos[0], out_pos[1])
                    if isinstance(target_cell, TransportComponent):
                        # 强行将所有传送带默认吞吐量提速到至少 12.0
                        capacity = max(12.0, getattr(target_cell, 'max_capacity', 12.0))
                        target_item = getattr(target_cell, 'current_item', None)

                        if target_item is None:
                            push_amt = min(amount, capacity)
                            target_cell.current_item = (mat, push_amt)
                            building.output_buffer[mat] -= push_amt
                            amount -= push_amt
                        elif isinstance(target_item, tuple):
                            t_mat, t_amt = target_item
                            if t_mat == mat:
                                space_left = capacity - t_amt
                                if space_left > 0:
                                    push_amt = min(amount, space_left)
                                    target_cell.current_item = (mat, t_amt + push_amt)
                                    building.output_buffer[mat] -= push_amt
                                    amount -= push_amt
                    if amount < 1.0:
                        break

    def _try_move_or_merge(self, transport: TransportComponent, target_cell) -> bool:
        """核心物流算法：尝试移动或合并物品，实现满载压缩"""
        if not isinstance(target_cell, TransportComponent): return False

        my_item = transport.current_item
        if my_item is None: return False

        # 1. 目标空闲，直接移动
        if getattr(target_cell, 'next_tick_item', None) is None and getattr(target_cell, 'current_item', None) is None:
            target_cell.next_tick_item = my_item
            transport.current_item = None
            return True

        # 2. 目标已占用，尝试将物品挤进去 (合并 Stacking)
        target_item = getattr(target_cell, 'next_tick_item', None) or getattr(target_cell, 'current_item', None)
        if isinstance(my_item, tuple) and isinstance(target_item, tuple):
            m_mat, m_amt = my_item
            t_mat, t_amt = target_item
            if m_mat == t_mat:
                capacity = max(12.0, getattr(target_cell, 'max_capacity', 12.0))
                space_left = capacity - t_amt
                if space_left > 0:
                    transfer = min(m_amt, space_left)
                    target_cell.next_tick_item = (t_mat, t_amt + transfer)

                    if m_amt - transfer > 0:
                        transport.current_item = (m_mat, m_amt - transfer)
                    else:
                        transport.current_item = None
                    return True  # 发生过有效移动
        return False

    def tick(self):
        # ==========================================
        # 阶段 1: 建筑生产 (Production Phase)
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

            self._push_building_outputs(building)

        # ==========================================
        # 阶段 2: 运输网络流转 (支持智能分流与合并)
        # 逆序遍历极其重要！这保证了下游优先移动，释放出上游空间
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

                # 依次尝试分流。如果一个口子塞满了，它会自动把剩下的物品塞进其他口子！
                if self._is_valid_router_output(right_cell, current_x, current_y):
                    self._try_move_or_merge(transport, right_cell)
                if transport.current_item is not None and self._is_valid_router_output(left_cell, current_x, current_y):
                    self._try_move_or_merge(transport, left_cell)
                if transport.current_item is not None and self._is_valid_router_output(front_cell, current_x,
                                                                                       current_y):
                    self._try_move_or_merge(transport, front_cell)

            # --- 分支 C: 溢流门 (Overflow Gate) ---
            elif isinstance(transport, OverflowGate):
                front_cell = self._get_cell(current_x + transport.direction.value[0],
                                            current_y + transport.direction.value[1])
                if self._is_valid_router_output(front_cell, current_x, current_y):
                    self._try_move_or_merge(transport, front_cell)
                if transport.current_item is not None:
                    left_cell, right_cell = self._get_sides(current_x, current_y, transport.direction)
                    if self._is_valid_router_output(left_cell, current_x, current_y):
                        self._try_move_or_merge(transport, left_cell)
                    if transport.current_item is not None and self._is_valid_router_output(right_cell, current_x,
                                                                                           current_y):
                        self._try_move_or_merge(transport, right_cell)

            # --- 分支 D: 传输桥 (Bridge) ---
            elif transport.__class__.__name__ == "Bridge":
                if (current_x, current_y) == transport.pos:
                    dx, dy = transport.direction.value
                    self._try_move_or_merge(transport,
                                            self._get_cell(transport.end_pos[0] + dx, transport.end_pos[1] + dy))

        self._apply_next_tick_states()