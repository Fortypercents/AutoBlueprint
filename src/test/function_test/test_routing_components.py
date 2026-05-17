import sys
import os
import time

# Implementation note.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from environment.grid_map import GridMap
from entities.material import MaterialType
from entities.registry import get_transport_instance
from entities.transport import Direction
from utils.test_utils import render_system_b_blueprint


def place_belt(env, x, y, out_dir, in_dir=None):
    'AutoBlueprint status message.'
    belt = get_transport_instance(301)
    if in_dir is None:
        opp_map = {Direction.UP: Direction.DOWN, Direction.DOWN: Direction.UP,
                   Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT}
        belt.in_dir = opp_map[out_dir]
    else:
        belt.in_dir = in_dir
    env.place_transport(belt, x, y, out_dir)


def place_comp(env, comp_id, x, y, out_dir):
    'AutoBlueprint status message.'
    comp = get_transport_instance(comp_id)
    opp_map = {Direction.UP: Direction.DOWN, Direction.DOWN: Direction.UP,
               Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT}
    comp.in_dir = opp_map[out_dir]
    env.place_transport(comp, x, y, out_dir)


def run_test():
    # Implementation note.
    env = GridMap(38, 17)

    # ==========================================
    # Test and validation logic.
    # ==========================================
    for y in range(2, 8): place_belt(env, 7, y, Direction.DOWN)
    for y in range(9, 15): place_belt(env, 7, y, Direction.DOWN)
    for x in range(2, 7): place_belt(env, x, 8, Direction.RIGHT)
    for x in range(8, 13): place_belt(env, x, 8, Direction.RIGHT)
    place_comp(env, 314, 7, 8, Direction.DOWN)

    # ==========================================
    # Test and validation logic.
    # ==========================================
    for y in range(2, 8): place_belt(env, 21, y, Direction.DOWN)
    for x in range(15, 21): place_belt(env, x, 8, Direction.RIGHT)
    place_comp(env, 312, 21, 8, Direction.DOWN)
    for y in range(9, 15): place_belt(env, 21, y, Direction.DOWN)

    # ==========================================
    # Test and validation logic.
    # ==========================================
    for y in range(2, 8): place_belt(env, 30, y, Direction.DOWN)
    place_comp(env, 311, 30, 8, Direction.DOWN)
    for x in range(24, 30): place_belt(env, x, 8, Direction.LEFT)
    for x in range(31, 37): place_belt(env, x, 8, Direction.RIGHT)

    total_crosser_v = 0.0
    total_crosser_h = 0.0
    total_merger = 0.0
    total_splitter_l = 0.0
    total_splitter_r = 0.0

    ticks_to_simulate = 60

    print("=== ⚙️ Extended Routing Components Diagnostic Test ===")
    for tick in range(1, ticks_to_simulate + 1):

        # Implementation note.
        if tick <= 30:
            # Implementation note.
            c_v = env._get_cell(7, 2)
            if not getattr(c_v, 'current_item', None): c_v.current_item = (MaterialType.IRON_ORE, 1.0)
            c_h = env._get_cell(2, 8)
            if not getattr(c_h, 'current_item', None): c_h.current_item = (MaterialType.COPPER, 1.0)

            # Implementation note.
            # Implementation note.
            # Implementation note.
            if tick % 2 != 0:  # Implementation note.
                m_top = env._get_cell(21, 2)
                if not getattr(m_top, 'current_item', None): m_top.current_item = (MaterialType.COAL, 1.0)
            else:  # Implementation note.
                m_left = env._get_cell(15, 8)
                if not getattr(m_left, 'current_item', None): m_left.current_item = (MaterialType.COAL, 1.0)

            # Implementation note.
            s_top = env._get_cell(30, 2)
            if not getattr(s_top, 'current_item', None): s_top.current_item = (MaterialType.WATER, 1.0)

        # Implementation note.
        env.tick()

        # Implementation note.
        out_cv = env._get_cell(7, 14)
        if out_cv and getattr(out_cv, 'current_item', None):
            total_crosser_v += out_cv.current_item[1]
            out_cv.current_item = None

        out_ch = env._get_cell(12, 8)
        if out_ch and getattr(out_ch, 'current_item', None):
            total_crosser_h += out_ch.current_item[1]
            out_ch.current_item = None

        out_m = env._get_cell(21, 14)
        if out_m and getattr(out_m, 'current_item', None):
            total_merger += out_m.current_item[1]
            out_m.current_item = None

        out_sl = env._get_cell(24, 8)
        if out_sl and getattr(out_sl, 'current_item', None):
            total_splitter_l += out_sl.current_item[1]
            out_sl.current_item = None

        out_sr = env._get_cell(36, 8)
        if out_sr and getattr(out_sr, 'current_item', None):
            total_splitter_r += out_sr.current_item[1]
            out_sr.current_item = None

        # Input/output port handling.
        if tick % 2 == 0:
            status = (f"Crosser(V:{total_crosser_v:.0f} H:{total_crosser_h:.0f}) | "
                      f"Merger({total_merger:.0f}) | "
                      f"Splitter(L:{total_splitter_l:.0f} R:{total_splitter_r:.0f})")
            render_system_b_blueprint(env, tick, status)
            time.sleep(0.08)


if __name__ == "__main__":
    run_test()