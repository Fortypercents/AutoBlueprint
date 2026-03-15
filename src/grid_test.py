import time
from entities.material import MaterialType
from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction, TransportComponent
from entities.building import Building
from environment.grid_map import GridMap


# ==========================================
# 补丁区：临时为 GridMap 补全缺失的辅助方法
# (建议你测试完后，将这些方法正式写入 grid_map.py 中)
# ==========================================
# def patch_grid_map():
#     def place_transport(self, transport: TransportComponent, x: int, y: int, direction: Direction) -> bool:
#         if not self.is_in_bounds(x, y) or self.grid[y][x] is not None:
#             return False
#         transport.pos = (x, y)
#         transport.direction = direction
#         transport.current_item = None
#         transport.next_tick_item = None
#         self.grid[y][x] = transport
#         self.transports.append(transport)
#         return True
#
#     def _get_cell(self, x: int, y: int):
#         return self.grid[y][x] if self.is_in_bounds(x, y) else None
#
#     def _is_blocked(self, cell) -> bool:
#         if cell is None: return True
#         if isinstance(cell, Building): return False
#         if isinstance(cell, TransportComponent):
#             return getattr(cell, 'next_tick_item', None) is not None or getattr(cell, 'current_item', None) is not None
#         return True
#
#     def _apply_next_tick_states(self):
#         for t in self.transports:
#             if hasattr(t, 'next_tick_item') and t.next_tick_item is not None:
#                 t.current_item = t.next_tick_item
#                 t.next_tick_item = None
#
#     def _push_building_outputs(self, building: Building):
#         if not hasattr(building, 'output_buffer'):
#             building.output_buffer = {}
#         for mat, amount in list(building.output_buffer.items()):
#             if amount >= 1.0:
#                 for out_pos in building.active_output_ports:
#                     target_cell = self._get_cell(out_pos[0], out_pos[1])
#                     if isinstance(target_cell, TransportComponent) and not self._is_blocked(target_cell):
#                         target_cell.next_tick_item = mat
#                         building.output_buffer[mat] -= 1.0
#                         break
#
#     # 动态绑定方法到 GridMap
#     GridMap.place_transport = place_transport
#     GridMap._get_cell = _get_cell
#     GridMap._is_blocked = _is_blocked
#     GridMap._apply_next_tick_states = _apply_next_tick_states
#     GridMap._push_building_outputs = _push_building_outputs
#

# ==========================================
# 测试核心区
# ==========================================
def run_test():
    print("=== 1. 初始化测试环境 ===")
    env = GridMap(10, 5)

    # 获取实体：1个熔炉，2条传送带
    furnace = get_building_instance(201)
    # 为建筑初始化库存字典（在实际项目中应在 Building.__init__ 中声明）
    furnace.inventory = {}
    furnace.output_buffer = {}

    belt_in = get_transport_instance(101)
    belt_out = get_transport_instance(101)

    # 放置熔炉 (占地 3x3，左上角在 (3, 1))
    env.place_building(furnace, 3, 1)

    # 放置输入传送带 (位于 (2, 2)，指向右侧熔炉)
    env.place_transport(belt_in, 2, 2, Direction.RIGHT)

    # 放置输出传送带 (位于 (6, 2)，背离右侧熔炉向右)
    env.place_transport(belt_out, 6, 2, Direction.RIGHT)

    print("=== 2. 扫描环境拓扑连结 ===")
    env.update_connections(furnace)

    # 【删除或注释掉下面这两行！】
    # furnace.active_input_ports.append((2, 2))
    # furnace.active_output_ports.append((6, 2))

    print(f" -> 熔炉输入端口: {furnace.active_input_ports}")
    print(f" -> 熔炉输出端口: {furnace.active_output_ports}")

    print("\n=== 3. 运行物流 Tick 引擎 (模拟 5 帧) ===")

    for frame in range(1, 6):
        print(f"\n[Tick {frame}] ---------------------------")

        # 模拟源头每帧往输入传送带上放置一个铁矿石
        if belt_in.current_item is None:
            belt_in.current_item = MaterialType.IRON_ORE
            print("   * 矿机将 [IRON_ORE] 放入输入带 (2,2)")

        # 模拟机器从输入带抓取物品（简易版抓取逻辑）
        if belt_in.current_item == MaterialType.IRON_ORE:
            furnace.inventory[MaterialType.IRON_ORE] = furnace.inventory.get(MaterialType.IRON_ORE, 0) + 1
            belt_in.current_item = None
            print("   * 熔炉从传送带吃掉了一个 [IRON_ORE]")

        # 环境运转一帧
        env.tick()

        # 状态展示
        inv_ore = furnace.inventory.get(MaterialType.IRON_ORE, 0)
        buf_plate = furnace.output_buffer.get(MaterialType.IRON_PLATE, 0)
        print(f"   * 熔炉内部 -> 铁矿石库存: {inv_ore}, 待输出铁板: {buf_plate}")

        if belt_out.current_item:
            print(f"   * 输出带 (6,2) 出现产物: [{belt_out.current_item.name}]！")
            # 消费掉产物，避免堵塞
            belt_out.current_item = None


if __name__ == "__main__":
    run_test()