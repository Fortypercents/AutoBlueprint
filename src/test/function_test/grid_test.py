import time
from entities.material import MaterialType
from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction, TransportComponent
from entities.building import Building
from environment.grid_map import GridMap


# ==========================================
# Implementation note.
# Test and validation logic.
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
# Implementation note.
#     GridMap.place_transport = place_transport
#     GridMap._get_cell = _get_cell
#     GridMap._is_blocked = _is_blocked
#     GridMap._apply_next_tick_states = _apply_next_tick_states
#     GridMap._push_building_outputs = _push_building_outputs
#

# ==========================================
# Test and validation logic.
# ==========================================
def run_test():
    print('AutoBlueprint status message.')
    env = GridMap(10, 5)

    # Implementation note.
    furnace = get_building_instance(201)
    # Building placement logic.
    furnace.inventory = {}
    furnace.output_buffer = {}

    belt_in = get_transport_instance(101)
    belt_out = get_transport_instance(101)

    # Building placement logic.
    env.place_building(furnace, 3, 1)

    # Building placement logic.
    env.place_transport(belt_in, 2, 2, Direction.RIGHT)

    # Building placement logic.
    env.place_transport(belt_out, 6, 2, Direction.RIGHT)

    print('AutoBlueprint status message.')
    env.update_connections(furnace)

    # Implementation note.
    # furnace.active_input_ports.append((2, 2))
    # furnace.active_output_ports.append((6, 2))

    print("AutoBlueprint status message.")
    print("AutoBlueprint status message.")

    print('AutoBlueprint status message.')

    for frame in range(1, 6):
        print(f"\n[Tick {frame}] ---------------------------")

        # Building placement logic.
        if belt_in.current_item is None:
            belt_in.current_item = MaterialType.IRON_ORE
            print('AutoBlueprint status message.')

        # Input/output port handling.
        if belt_in.current_item == MaterialType.IRON_ORE:
            furnace.inventory[MaterialType.IRON_ORE] = furnace.inventory.get(MaterialType.IRON_ORE, 0) + 1
            belt_in.current_item = None
            print('AutoBlueprint status message.')

        # Implementation note.
        env.tick()

        # Implementation note.
        inv_ore = furnace.inventory.get(MaterialType.IRON_ORE, 0)
        buf_plate = furnace.output_buffer.get(MaterialType.IRON_PLATE, 0)
        print("AutoBlueprint status message.")

        if belt_out.current_item:
            print("AutoBlueprint status message.")
            # Implementation note.
            belt_out.current_item = None


if __name__ == "__main__":
    run_test()