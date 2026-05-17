import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction, TransportComponent
from environment.grid_map import GridMap
from entities.material import MaterialType
from utils.test_utils import render_system_b_blueprint


def run_blue_iron_validation():
    env = GridMap(30, 15)

    b_refinery = get_building_instance(513)
    b_part_maker = get_building_instance(532)

    # Building placement logic.
    env.place_building(b_refinery, 8, 4, Direction.RIGHT)
    env.place_building(b_part_maker, 16, 4, Direction.LEFT)

    # Implementation note.
    def place_belt(x, y, out_d, in_d=None):
        belt = get_transport_instance(301)
        env.place_transport(belt, x, y, out_d)

        if in_d is not None:
            belt.in_dir = in_d
        else:
            # Input/output port handling.
            opposite = {
                Direction.UP: Direction.DOWN,
                Direction.DOWN: Direction.UP,
                Direction.LEFT: Direction.RIGHT,
                Direction.RIGHT: Direction.LEFT
            }
            belt.in_dir = opposite[out_d]

    # Input/output port handling.
    place_belt(14, 4, Direction.LEFT)
    place_belt(13, 4, Direction.LEFT)
    place_belt(12, 4, Direction.LEFT)
    place_belt(11, 4, Direction.LEFT)

    # Implementation note.
    place_belt(7, 6, Direction.LEFT)  # Implementation note.
    place_belt(6, 6, Direction.DOWN, Direction.RIGHT)  # Implementation note.
    place_belt(6, 7, Direction.DOWN)  # Implementation note.
    place_belt(6, 8, Direction.RIGHT, Direction.UP)  # Implementation note.
    for x in range(7, 14):
        place_belt(x, 8, Direction.RIGHT)  # Implementation note.
    place_belt(14, 8, Direction.UP, Direction.LEFT)  # Implementation note.
    place_belt(14, 7, Direction.UP)  # Implementation note.
    place_belt(14, 6, Direction.RIGHT, Direction.DOWN)  # Implementation note.
    place_belt(15, 6, Direction.RIGHT)  # Implementation note.

    # Implementation note.
    place_belt(19, 5, Direction.RIGHT)
    place_belt(20, 5, Direction.RIGHT)
    place_belt(21, 5, Direction.RIGHT)
    place_belt(22, 5, Direction.RIGHT)

    for b in env.buildings:
        env.update_connections(b)
        if not hasattr(b, 'inventory'): b.inventory = {}
        if not hasattr(b, 'output_buffer'): b.output_buffer = {}

    total_parts_collected = 0

    # Implementation note.
    for tick in range(1, 80):
        # Implementation note.
        start_belt = env._get_cell(14, 4)
        if isinstance(start_belt, TransportComponent) and start_belt.current_item is None:
            start_belt.current_item = (MaterialType.BLUE_IRON, 1.0)

        for b in env.buildings:
            for px, py in b.active_input_ports:
                cell = env._get_cell(px, py)
                if isinstance(cell, TransportComponent) and getattr(cell, 'current_item', None):
                    item = cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0
                    if mat in b.allowed_input_materials:
                        b.inventory[mat] = b.inventory.get(mat, 0) + amt
                        cell.current_item = None

        env.tick()

        # Implementation note.
        end_belt = env._get_cell(22, 5)
        if isinstance(end_belt, TransportComponent) and end_belt.current_item is not None:
            item = end_belt.current_item
            mat = item[0] if isinstance(item, tuple) else item
            if mat == MaterialType.BLUE_IRON_PART:
                total_parts_collected += 1
            end_belt.current_item = None

        render_system_b_blueprint(env, tick=tick, status_text="System B routing test")
        time.sleep(0.1)

    print(f"Final collected blue iron parts: {total_parts_collected}")


if __name__ == "__main__":
    run_blue_iron_validation()