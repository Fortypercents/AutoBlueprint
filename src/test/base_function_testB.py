import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from typing import Dict, Tuple, Any
from entities.material import MaterialType
from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction, TransportComponent
from environment.grid_map import GridMap
from agents.base_agent import BaseAgent


class SystemBTestAgent(BaseAgent):
    def optimize(self, env: GridMap):
        print('Agent status message.')

        def route(pts, comp_id=301):
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                if x2 > x1:
                    d = Direction.RIGHT
                elif x2 < x1:
                    d = Direction.LEFT
                elif y2 > y1:
                    d = Direction.DOWN
                else:
                    d = Direction.UP

                if x1 == x2:
                    step = 1 if y2 > y1 else -1
                    for y in range(y1, y2, step):
                        env.place_transport(get_transport_instance(comp_id), x1, y, d)
                else:
                    step = 1 if x2 > x1 else -1
                    for x in range(x1, x2, step):
                        env.place_transport(get_transport_instance(comp_id), x, y1, d)

            x1, y1 = pts[-2]
            x2, y2 = pts[-1]
            d = Direction.RIGHT if x2 > x1 else Direction.LEFT if x2 < x1 else Direction.DOWN if y2 > y1 else Direction.UP
            env.place_transport(get_transport_instance(comp_id), x2, y2, d)

        # Building placement logic.
        env.place_building(get_building_instance(401), 2, 8, Direction.UP)  # P1
        env.place_building(get_building_instance(401), 8, 8, Direction.UP)  # P2
        env.place_building(get_building_instance(401), 16, 8, Direction.UP)  # P3
        env.place_building(get_building_instance(401), 24, 8, Direction.UP)  # P4

        env.place_building(get_building_instance(402), 16, 14, Direction.UP)  # E1
        env.place_building(get_building_instance(402), 24, 14, Direction.UP)  # E2

        # Implementation note.
        route([(0, 1), (25, 1), (25, 5)])
        # Input/output port handling.
        env.place_transport(get_transport_instance(312), 25, 6, Direction.DOWN)
        env.place_transport(get_transport_instance(301), 25, 7, Direction.DOWN)

        # Implementation note.
        route([(3, 12), (3, 19)])  # Implementation note.
        env.place_transport(get_transport_instance(314), 3, 20, Direction.DOWN)  # Building placement logic.
        env.place_transport(get_transport_instance(314), 9, 24, Direction.DOWN)  # Implementation note.
        env.place_transport(get_transport_instance(314), 21, 6, Direction.LEFT)  # Implementation note.
        route([(3, 21), (3, 24), (31, 24)])  # Implementation note.

        # Implementation note.
        route([(9, 12), (9, 19)])
        env.place_transport(get_transport_instance(314), 9, 20, Direction.DOWN)  # Building placement logic.
        route([(9, 21), (9, 25), (31, 25)])

        # Implementation note.
        route([(17, 12), (17, 13)])
        route([(25, 12), (25, 13)])

        # Implementation note.
        route([(25, 18), (25, 19)])
        env.place_transport(get_transport_instance(311), 25, 20, Direction.DOWN)
        # Implementation note.
        route([(26, 20), (28, 20), (28, 6), (26, 6)])
        # Input/output port handling.
        route([(24, 20), (22, 20), (22, 6), (17, 6), (17, 7)])

        # Implementation note.
        route([(17, 18), (17, 19)])
        env.place_transport(get_transport_instance(311), 17, 20, Direction.DOWN)
        # Implementation note.
        route([(18, 20), (21, 20), (21, 5), (9, 5), (9, 7)])
        # Implementation note.
        route([(16, 20), (10, 20)])  # Implementation note.
        route([(8, 20), (4, 20)])  # Implementation note.
        route([(2, 20), (1, 20), (1, 6), (3, 6), (3,7)])  # Input/output port handling.

    def render_blueprint(self, env: GridMap, tick: int = 0, total_yield: float = 0):
        print("\n" * 5)
        print(f"=== Logistics simulation [Tick {tick:03d}] | Total output: {total_yield} ===")

        dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}

        for y in range(env.height):
            row_str = f"{y:02d} |"
            for x in range(env.width):
                cell = env._get_cell(x, y)
                if cell is None:
                    row_str += " . "
                elif hasattr(cell, 'size'):
                    row_str += "[P]" if cell.component_id == 401 else "[E]"
                elif isinstance(cell, TransportComponent):
                    c_name = type(cell).__name__
                    is_crosser = "Crosser" in c_name
                    is_router = "Router" in c_name or "Splitter" in c_name
                    is_merger = "Merger" in c_name

                    dir_char = dir_symbols.get(getattr(cell, 'direction', Direction.RIGHT), "*")

                    item = getattr(cell, 'current_item', None)
                    if item is not None:
                        amt = int(item[1]) if isinstance(item, tuple) else 1
                        base_char = "X" if is_crosser else "M" if is_merger else "S" if is_router else dir_char
                        row_str += f"{base_char}{amt:02d}"
                    else:
                        base_char = "[X]" if is_crosser else "[M]" if is_merger else "[S]" if is_router else f" {dir_char} "
                        row_str += base_char
                else:
                    row_str += "[?]"
            print(row_str)

        print("   " + "-" * (env.width * 3 + 2))
        header_x = "    "
        for x in range(env.width):
            header_x += f"{x:02d} " if x % 2 == 0 else "   "
        print(header_x)
        print("=====================================================================")


def run_test():
    agent = SystemBTestAgent({})
    env = GridMap(34, 27)
    agent.optimize(env)
    for b in env.buildings: env.update_connections(b)

    print('AutoBlueprint status message.')
    total_apple_yield = 0
    ticks_to_simulate = 350
    seeds_injected = 0

    for tick in range(1, ticks_to_simulate + 1):
        # Implementation note.
        if seeds_injected < 15:
            in_cell = env._get_cell(0, 1)
            if in_cell and in_cell.current_item is None:
                in_cell.current_item = (MaterialType.APPLE_SEED, 1.0)
                seeds_injected += 1

        # Implementation note.
        for b in env.buildings:
            if not hasattr(b, 'inventory'): b.inventory = {}
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if isinstance(port_cell, TransportComponent) and getattr(port_cell, 'current_item', None) is not None:
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0
                    if mat in b.allowed_input_materials:
                        current_inv = b.inventory.get(mat, 0)
                        if current_inv < b.max_inventory:
                            take_amt = min(amt, b.max_inventory - current_inv)
                            b.inventory[mat] = current_inv + take_amt
                            port_cell.current_item = (mat, amt - take_amt) if amt - take_amt > 0 else None

        # Implementation note.
        crosser_defs = [
            # Implementation note.
            {'pos': (3, 20),  'p1': ((3, 19), (3, 21)),   'p2': ((4, 20), (2, 20))},   # Implementation note.
            {'pos': (9, 20),  'p1': ((9, 19), (9, 21)),   'p2': ((10, 20), (8, 20))},  # Implementation note.
            {'pos': (9, 24),  'p1': ((9, 23), (9, 25)),   'p2': ((8, 24), (10, 24))},  # Implementation note.
            {'pos': (21, 6),  'p1': ((21, 7), (21, 5)),   'p2': ((22, 6), (20, 6))}    # Implementation note.
        ]

        for cdef in crosser_defs:
            cx, cy = cdef['pos']
            crosser = env._get_cell(cx, cy)
            if crosser and type(crosser).__name__ == "SystemBCrosser":
                # Implementation note.
                for path in ['p1', 'p2']:
                    in_pos, out_pos = cdef[path]
                    c_in = env._get_cell(*in_pos)
                    c_out = env._get_cell(*out_pos)

                    # Implementation note.
                    if c_in and getattr(c_in, 'current_item', None):
                        if c_out and getattr(c_out, 'current_item', None) is None:
                            c_out.current_item = c_in.current_item
                            c_in.current_item = None

        # Implementation note.
        env.tick()

        # Implementation note.
        for out_y in [24, 25]:
            out_cell = env._get_cell(31, out_y)
            if out_cell and getattr(out_cell, 'current_item', None) is not None:
                out_item = out_cell.current_item
                amt = out_item[1] if isinstance(out_item, tuple) else 1.0
                if (out_item[0] if isinstance(out_item, tuple) else out_item) == MaterialType.APPLE:
                    total_apple_yield += amt
                out_cell.current_item = None

        agent.render_blueprint(env, tick, total_apple_yield)
        time.sleep(0.04)

    print(f"Test finished. Total apple output: {total_apple_yield}")
    print('Operation completed successfully.')


if __name__ == "__main__":
    run_test()