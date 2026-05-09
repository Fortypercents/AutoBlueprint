from typing import List, Tuple, Optional, Any
from entities.building import Building
from entities.transport import TransportComponent, Direction

class GridMap:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.grid: List[List[Optional[Any]]] = [[None for _ in range(width)] for _ in range(height)]
        self.buildings: List[Building] = []
        self.transports: List[TransportComponent] = []

    def is_in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def can_place_building(self, building: Building, start_x: int, start_y: int,
                           direction: Direction = Direction.UP) -> bool:
        w, h = building.size
        # 模拟建筑横向摆放时长宽互换
        if direction in (Direction.LEFT, Direction.RIGHT):
            w, h = h, w

        for y in range(start_y, start_y + h):
            for x in range(start_x, start_x + w):
                if not self.is_in_bounds(x, y) or self.grid[y][x] is not None:
                    return False
        return True

    def place_building(self, building: Building, start_x: int, start_y: int,
                       direction: Direction = Direction.UP) -> bool:
        if not self.can_place_building(building, start_x, start_y, direction):
            return False

        # 根据方向翻转尺寸并设定对立面
        if direction in (Direction.LEFT, Direction.RIGHT):
            building.size = (building.size[1], building.size[0])
        building.set_direction(direction)

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

            # ==========================================
            # 【体系物理隔离】：检查建筑与相邻元件的体系兼容性
            # ==========================================
            b_sys = getattr(building, 'system_type', None)
            n_sys = getattr(neighbor, 'system_type', None)

            if str(b_sys).split('.')[-1] != str(n_sys).split('.')[-1]:
                continue

            start_x, start_y = building.anchor_pos
            w, h = building.size

            if py == start_y - 1:
                side = Direction.UP
            elif py == start_y + h:
                side = Direction.DOWN
            elif px == start_x - 1:
                side = Direction.LEFT
            elif px == start_x + w:
                side = Direction.RIGHT
            else:
                continue

            if isinstance(neighbor, TransportComponent):
                nx, ny = px, py
                dx, dy = neighbor.direction.value
                target_x = nx + dx
                target_y = ny + dy
                is_pointing_inside = (start_x <= target_x < start_x + w) and (start_y <= target_y < start_y + h)

                if is_pointing_inside:
                    if building.allows_omni_ports or side == getattr(building, 'input_side', Direction.UP):
                        building.active_input_ports.append((nx, ny))
                else:
                    if building.allows_omni_ports or side == getattr(building, 'output_side', Direction.DOWN):
                        building.active_output_ports.append((nx, ny))

            elif isinstance(neighbor, Building):
                if not building.allows_direct_insertion or not neighbor.allows_direct_insertion:
                    continue
                shared_materials = set(building.output_materials.keys()) & set(neighbor.input_materials.keys())
                if shared_materials:
                    valid_out = building.allows_omni_ports or side == getattr(building, 'output_side', Direction.DOWN)
                    if side == Direction.UP:
                        n_side = Direction.DOWN
                    elif side == Direction.DOWN:
                        n_side = Direction.UP
                    elif side == Direction.LEFT:
                        n_side = Direction.RIGHT
                    else:
                        n_side = Direction.LEFT
                    valid_in = neighbor.allows_omni_ports or n_side == getattr(neighbor, 'input_side', Direction.UP)
                    if valid_out and valid_in:
                        building.active_output_ports.append((px, py))
                        if building.anchor_pos not in neighbor.active_input_ports:
                            neighbor.active_input_ports.append(building.anchor_pos)

    def _get_cell(self, x: int, y: int):
        if self.is_in_bounds(x, y):
            return self.grid[y][x]
        return None

    def _is_valid_router_output(self, cell, from_x, from_y) -> bool:
        """结构校验：检查目标格子是否为合法的输出方向"""
        if not isinstance(cell, TransportComponent):
            return False

        # 兼容全部新体系物流元件：拒绝把物品塞给“正向着自己开过来”的传送带/管道
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
        """阶段 4: 应用下一帧状态"""
        for transport in self.transports:
            # 【核心新增】：结算交叉器的双通道
            if "Crosser" in type(transport).__name__:
                if hasattr(transport, 'next_cross_buffers'):
                    if not hasattr(transport, 'cross_buffers'): transport.cross_buffers = {}
                    for axis, next_item in transport.next_cross_buffers.items():
                        n_mat, n_amt = next_item
                        curr_item = transport.cross_buffers.get(axis)
                        if curr_item:
                            transport.cross_buffers[axis] = (n_mat, curr_item[1] + n_amt)
                        else:
                            transport.cross_buffers[axis] = (n_mat, n_amt)
                    transport.next_cross_buffers.clear()

                    # 仅作 UI 渲染用途：挑一个通道的物品显示
                    if transport.cross_buffers:
                        transport.current_item = list(transport.cross_buffers.values())[0]
                    else:
                        transport.current_item = None
                continue

            # --- 原始状态应用逻辑 ---
            next_item = getattr(transport, 'next_tick_item', None)
            if next_item is not None:
                n_mat = next_item[0] if isinstance(next_item, tuple) else next_item
                n_amt = next_item[1] if isinstance(next_item, tuple) else 1.0

                curr_item = getattr(transport, 'current_item', None)
                if curr_item is not None:
                    c_mat = curr_item[0] if isinstance(curr_item, tuple) else curr_item
                    c_amt = curr_item[1] if isinstance(curr_item, tuple) else 1.0
                    if c_mat == n_mat:
                        transport.current_item = (n_mat, c_amt + n_amt)
                    else:
                        transport.current_item = (n_mat, n_amt)
                else:
                    transport.current_item = (n_mat, n_amt)

                transport.next_tick_item = None

    # ==========================================
    # 核心流体力学引擎 (智能合并与分配)
    # ==========================================
    def _push_to_cell(self, target_cell, mat, amt, travel_dir=None) -> float:
        """底层物流接口：尝试将最多 amt 数量的 mat 挤进 target_cell 中"""
        if not isinstance(target_cell, TransportComponent):
            return 0.0

        supported_state = getattr(target_cell, 'supported_state', None)
        if supported_state is not None:
            mat_state = getattr(mat, 'state', None)
            if mat_state is not None and mat_state != supported_state:
                return 0.0

                # ==========================================
        # 1. 严格化传送带之间的传输规则 (防误伤逻辑)
        # ==========================================
        is_multi_port = any(name in type(target_cell).__name__ for name in
                            ["Crosser", "Merger", "Splitter", "Router", "Gate", "Access"])

        if not is_multi_port and travel_dir is not None:
            expected_in_dir = None
            if travel_dir == Direction.RIGHT:
                expected_in_dir = Direction.LEFT
            elif travel_dir == Direction.LEFT:
                expected_in_dir = Direction.RIGHT
            elif travel_dir == Direction.UP:
                expected_in_dir = Direction.DOWN
            elif travel_dir == Direction.DOWN:
                expected_in_dir = Direction.UP

            target_in_dir = getattr(target_cell, 'in_dir', None)
            if target_in_dir is None:
                td = getattr(target_cell, 'direction', Direction.RIGHT)
                target_in_dir = Direction.LEFT if td == Direction.RIGHT else Direction.RIGHT if td == Direction.LEFT else Direction.DOWN if td == Direction.UP else Direction.UP

            if target_in_dir != expected_in_dir:
                return 0.0

        # ==========================================
        # 2. 【核心修复】：交叉器双通道独立容量逻辑 (无限容积)
        # ==========================================
        is_crosser = "Crosser" in type(target_cell).__name__
        if is_crosser:
            if not hasattr(target_cell, 'cross_buffers'): target_cell.cross_buffers = {}
            if not hasattr(target_cell, 'next_cross_buffers'): target_cell.next_cross_buffers = {}
            if not hasattr(target_cell, 'exit_dirs'): target_cell.exit_dirs = {}

            t_dir = travel_dir if travel_dir else getattr(target_cell, 'direction', Direction.DOWN)
            axis = 'V' if t_dir in (Direction.UP, Direction.DOWN) else 'H'

            curr_item = target_cell.cross_buffers.get(axis)
            next_item = target_cell.next_cross_buffers.get(axis)

            curr_mat = curr_item[0] if curr_item else None
            next_mat = next_item[0] if next_item else None

            if curr_mat is not None and curr_mat != mat: return 0.0
            if next_mat is not None and next_mat != mat: return 0.0

            curr_amt = curr_item[1] if curr_item else 0.0
            next_amt = next_item[1] if next_item else 0.0

            # 【关键修改】：将交叉器的容量视为无限大 (float('inf'))
            # 这样交叉器可以作为完美的弹性缓冲区，吸收物理引擎 Tick 顺序错位带来的拥堵
            capacity = float('inf')
            space_left = capacity - (curr_amt + next_amt)

            if space_left <= 0: return 0.0

            push_amt = min(amt, space_left)
            target_cell.next_cross_buffers[axis] = (mat, next_amt + push_amt)
            target_cell.exit_dirs[axis] = t_dir
            return push_amt

        # ==========================================
        # 3. 原始皮带推入逻辑
        # ==========================================
        curr_item = getattr(target_cell, 'current_item', None)
        next_item = getattr(target_cell, 'next_tick_item', None)

        curr_mat = curr_item[0] if isinstance(curr_item, tuple) else curr_item if curr_item else None
        next_mat = next_item[0] if isinstance(next_item, tuple) else next_item if next_item else None

        if curr_mat is not None and curr_mat != mat: return 0.0
        if next_mat is not None and next_mat != mat: return 0.0

        curr_amt = curr_item[1] if isinstance(curr_item, tuple) else 1.0 if curr_item else 0.0
        next_amt = next_item[1] if isinstance(next_item, tuple) else 1.0 if next_item else 0.0

        capacity = getattr(target_cell, 'max_capacity', 1.0)
        space_left = capacity - (curr_amt + next_amt)

        if space_left <= 0: return 0.0

        push_amt = min(amt, space_left)
        target_cell.next_tick_item = (mat, next_amt + push_amt)
        return push_amt

    def _push_building_outputs(self, building: Building):
        """阶段 3: 将建筑产物推上管网"""
        if not hasattr(building, 'output_buffer'): building.output_buffer = {}
        if not hasattr(building, 'rr_index'): building.rr_index = 0

        ax, ay = building.anchor_pos
        w, h = building.size

        for mat, amount in list(building.output_buffer.items()):
            if amount >= 1.0 and building.active_output_ports:
                consecutive_failures = 0
                num_ports = len(building.active_output_ports)

                while amount >= 1.0 and consecutive_failures < num_ports:
                    out_pos = building.active_output_ports[building.rr_index]
                    px, py = out_pos
                    target_cell = self._get_cell(px, py)

                    if isinstance(target_cell, TransportComponent):
                        # 基于传送带相对于建筑边框的绝对位置，计算期望的 in_dir
                        expected_in_dir = None
                        if py == ay - 1:
                            expected_in_dir = Direction.DOWN
                        elif py == ay + h:
                            expected_in_dir = Direction.UP
                        elif px == ax - 1:
                            expected_in_dir = Direction.RIGHT
                        elif px == ax + w:
                            expected_in_dir = Direction.LEFT

                        belt_in_dir = getattr(target_cell, 'in_dir', getattr(target_cell, 'direction', Direction.RIGHT))

                        # 【核心修复】：识别交叉器，解除单向朝向限制
                        is_crosser = "Crosser" in type(target_cell).__name__

                        # 如果不是交叉器，且当前这根皮带的 in_dir 和建筑要求的朝向不符，果断拦截防偷窃
                        if not is_crosser and expected_in_dir is not None and belt_in_dir != expected_in_dir:
                            consecutive_failures += 1
                            building.rr_index = (building.rr_index + 1) % num_ports
                            continue

                        # 既然对齐了（或是交叉器），推算出货物被挤入皮带时的物理行驶方向
                        t_dir_map = {Direction.UP: Direction.DOWN, Direction.DOWN: Direction.UP,
                                     Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT}
                        travel_dir = t_dir_map.get(expected_in_dir, Direction.DOWN)
                    else:
                        travel_dir = Direction.DOWN

                    push_val = min(amount, 1.0)
                    pushed = self._push_to_cell(target_cell, mat, push_val, travel_dir=travel_dir)

                    if pushed > 0:
                        building.output_buffer[mat] -= pushed
                        amount -= pushed
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1

                    building.rr_index = (building.rr_index + 1) % num_ports

    def _try_move_or_merge(self, transport: TransportComponent, target_cell) -> bool:
        if transport.current_item is None: return False

        mat = transport.current_item[0] if isinstance(transport.current_item, tuple) else transport.current_item
        amt = transport.current_item[1] if isinstance(transport.current_item, tuple) else 1.0

        # 获取运输元件当前的物理行驶方向并传递
        travel_dir = getattr(transport, 'direction', Direction.RIGHT)
        pushed = self._push_to_cell(target_cell, mat, amt, travel_dir=travel_dir)

        if pushed > 0:
            if amt - pushed > 0:
                transport.current_item = (mat, amt - pushed)
            else:
                transport.current_item = None
            return True
        return False

    def _distribute_evenly(self, transport: TransportComponent, target_cells: List) -> bool:
        if getattr(transport, 'current_item', None) is None or not target_cells:
            return False

        mat = transport.current_item[0] if isinstance(transport.current_item, tuple) else transport.current_item
        amt = transport.current_item[1] if isinstance(transport.current_item, tuple) else 1.0

        if not hasattr(transport, 'rr_index'): transport.rr_index = 0

        consecutive_failures = 0
        moved_any = False

        while amt > 0 and consecutive_failures < len(target_cells):
            cell = target_cells[transport.rr_index]

            # 动态计算分配至该接口时的旅行方向
            dx = cell.pos[0] - transport.pos[0]
            dy = cell.pos[1] - transport.pos[1]
            try:
                t_dir = Direction((dx, dy))
            except ValueError:
                t_dir = transport.direction

            push_val = min(amt, 1.0)
            pushed = self._push_to_cell(cell, mat, push_val, travel_dir=t_dir)

            if pushed > 0:
                amt -= pushed
                consecutive_failures = 0
                moved_any = True
            else:
                consecutive_failures += 1

            transport.rr_index = (transport.rr_index + 1) % len(target_cells)

        if amt > 0:
            transport.current_item = (mat, amt)
        else:
            transport.current_item = None

        return moved_any

    def tick(self):
        # ==========================================
        # 阶段 1: 建筑生产 (内部消化与产出缓冲)
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

        # ==========================================
        # 阶段 2: 运输网络流转 (核心重构：多趟扫荡机制 Sweep System)
        # ==========================================
        for t in self.transports:
            t.moved_this_tick = False

        moved_any = True
        sweeps = 0
        while moved_any and sweeps < 10:  # 最大允许 10 次扫荡，完美解决任意深度的局部依赖
            moved_any = False
            sweeps += 1

            for transport in self.transports:
                if transport.moved_this_tick:
                    continue

                c_name = type(transport).__name__
                current_x, current_y = transport.pos
                success = False

                # 【独立执行单元】：交叉器主动向外排货
                if "Crosser" in c_name:
                    if not hasattr(transport, 'cross_buffers') or not transport.cross_buffers:
                        transport.moved_this_tick = True
                        continue

                    pushed_all = True
                    pushed_any = False
                    for axis, item in list(transport.cross_buffers.items()):
                        mat, amt = item
                        exit_dir = transport.exit_dirs.get(axis)
                        if exit_dir:
                            next_x = current_x + exit_dir.value[0]
                            next_y = current_y + exit_dir.value[1]
                            pushed = self._push_to_cell(self._get_cell(next_x, next_y), mat, amt,
                                                        travel_dir=exit_dir)
                            if pushed > 0:
                                pushed_any = True
                                if amt - pushed > 0:
                                    transport.cross_buffers[axis] = (mat, amt - pushed)
                                    pushed_all = False
                                else:
                                    del transport.cross_buffers[axis]
                            else:
                                pushed_all = False

                    if transport.cross_buffers:
                        transport.current_item = list(transport.cross_buffers.values())[0]
                    else:
                        transport.current_item = None

                    if pushed_all:
                        transport.moved_this_tick = True
                    if pushed_any:
                        moved_any = True
                    continue

                # 【基础元件与分流/汇流器】
                if getattr(transport, 'current_item', None) is None:
                    transport.moved_this_tick = True
                    continue

                if c_name in ("SystemABelt", "SystemAPipe", "SystemBBelt", "SystemBPipe", "SystemBBeltAccess",
                              "SystemBPipeAccess", "SystemBMerger", "SystemBPipeMerger"):
                    next_x = current_x + transport.direction.value[0]
                    next_y = current_y + transport.direction.value[1]
                    success = self._try_move_or_merge(transport, self._get_cell(next_x, next_y))

                elif "Splitter" in c_name or "Router" in c_name:
                    front_cell = self._get_cell(current_x + transport.direction.value[0],
                                                current_y + transport.direction.value[1])
                    left_cell, right_cell = self._get_sides(current_x, current_y, transport.direction)

                    if self._is_valid_router_output(front_cell, current_x, current_y):
                        success = self._try_move_or_merge(transport, front_cell)

                    if not success and transport.current_item is not None:
                        valid_side_targets = []
                        if self._is_valid_router_output(left_cell, current_x,
                                                        current_y): valid_side_targets.append(left_cell)
                        if self._is_valid_router_output(right_cell, current_x,
                                                        current_y): valid_side_targets.append(right_cell)
                        success = self._distribute_evenly(transport, valid_side_targets)

                elif c_name in ("SystemABridge", "SystemAPipeBridge"):
                    if (current_x, current_y) == transport.pos:
                        dx, dy = transport.direction.value
                        success = self._try_move_or_merge(transport, self._get_cell(transport.end_pos[0] + dx,
                                                                                    transport.end_pos[1] + dy))

                if success:
                    moved_any = True
                    # 如果当前货物全部清空，则本帧无需再处理它
                    if getattr(transport, 'current_item', None) is None:
                        transport.moved_this_tick = True

        # ==========================================
        # 阶段 3: 将新产物推上管网 (解决克隆 Bug)
        # ==========================================
        for building in self.buildings:
            self._push_building_outputs(building)

        # ==========================================
        # 阶段 4: 应用下一帧状态
        # ==========================================
        self._apply_next_tick_states()