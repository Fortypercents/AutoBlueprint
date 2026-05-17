import time
import os
from typing import Dict, Tuple, Any
from entities.material import MaterialType
from entities.registry import get_transport_instance
from entities.transport import Direction, TransportComponent, LogicRouter
from environment.grid_map import GridMap
from agents.base_agent import BaseAgent


class BlueprintTestAgent(BaseAgent):
    def optimize(self, env: GridMap):
        print('Agent status message.')
        in_belt_y, machine_y, out_belt_y = 2, 4, 8
        start_x, spacing = 2, 4
        last_mid_x = start_x

        for x in range(start_x + 1):
            belt = get_transport_instance(102)
            env.place_transport(belt, x, in_belt_y, Direction.RIGHT)

        for i, building in enumerate(self.required_buildings):
            current_x = start_x + i * spacing
            mid_x = current_x + 1
            last_mid_x = mid_x
            env.place_building(building, current_x, machine_y)

            splitter = get_transport_instance(110)
            env.place_transport(splitter, mid_x, in_belt_y, Direction.RIGHT)
            in_belt = get_transport_instance(102)
            env.place_transport(in_belt, mid_x, in_belt_y + 1, Direction.DOWN)

            out_belt = get_transport_instance(102)
            env.place_transport(out_belt, mid_x, out_belt_y - 1, Direction.DOWN)
            merger = get_transport_instance(110)
            env.place_transport(merger, mid_x, out_belt_y, Direction.RIGHT)

            if i < len(self.required_buildings) - 1:
                for gap_x in range(mid_x + 1, mid_x + spacing):
                    b_in = get_transport_instance(102)
                    env.place_transport(b_in, gap_x, in_belt_y, Direction.RIGHT)
                    b_out = get_transport_instance(102)
                    env.place_transport(b_out, gap_x, out_belt_y, Direction.RIGHT)

        for x in range(last_mid_x + 1, env.width - 1):
            b_out_final = get_transport_instance(102)
            env.place_transport(b_out_final, x, out_belt_y, Direction.RIGHT)

        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y, Direction.DOWN)
        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y + 1, Direction.DOWN)
        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y + 2, Direction.DOWN)

    def render_blueprint(self, env: GridMap, tick: int = 0, total_yield: float = 0):
        print("\n" * 5)
        print(f"=== Logistics simulation [Tick {tick:03d}] | Total output: {total_yield} ===")

        dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}
        grid_strs = []

        for y in range(env.height):
            row_str = ""
            for x in range(env.width):
                cell = env._get_cell(x, y)
                if cell is None:
                    row_str += " . "
                elif hasattr(cell, 'size') and cell.size == (3, 3):
                    row_str += "[F]"
                elif isinstance(cell, TransportComponent):
                    is_router = type(cell).__name__ == "LogicRouter"
                    direction = getattr(cell, 'direction', Direction.RIGHT)
                    dir_char = dir_symbols.get(direction, "*")

                    item = getattr(cell, 'current_item', None)
                    if item is not None:
                        amt = int(item[1]) if isinstance(item, tuple) else 1
                        base_char = "S" if is_router else dir_char
                        row_str += f"{base_char}{amt:02d}"
                    else:
                        row_str += "[S]" if is_router else f" {dir_char} "
                else:
                    row_str += "[?]"
            grid_strs.append(f"{y:02d} {row_str}")

        for row in grid_strs:
            print(row)
        print("=====================================================================")


# ==========================================
# Implementation note.
# ==========================================
def get_factory_state(env: GridMap) -> Tuple[Any, ...]:
    'AutoBlueprint status message.'
    state = []

    # Implementation note.
    for t in env.transports:
        item = getattr(t, 'current_item', None)
        if item is None:
            state.append(None)
        elif isinstance(item, tuple):
            # Implementation note.
            state.append((item[0].value, round(item[1], 2)))
        else:
            state.append((item.value, 1.0))

    # Implementation note.
    for b in env.buildings:
        inv = getattr(b, 'inventory', {})
        buf = getattr(b, 'output_buffer', {})
        # Implementation note.
        inv_tuple = tuple(sorted((k.value, round(v, 2)) for k, v in inv.items()))
        buf_tuple = tuple(sorted((k.value, round(v, 2)) for k, v in buf.items()))
        state.append(inv_tuple)
        state.append(buf_tuple)

    return tuple(state)


def run_test():
    target_outputs = {MaterialType.IRON_PLATE: 6.0}
    agent = BlueprintTestAgent(target_outputs)
    agent.calculate_production_chain()

    env = GridMap(32, 12)
    agent.optimize(env)

    for b in env.buildings:
        env.update_connections(b)

    agent.render_blueprint(env, 0, 0)
    time.sleep(1)

    print('AutoBlueprint status message.')
    total_iron_plate_yield = 0
    ticks_to_simulate = 100

    # Implementation note.
    state_history = {}  # Implementation note.
    yield_history = {}  # Implementation note.

    steady_state_entry_tick = -1
    steady_state_period = -1
    steady_yield_per_tick = 0.0

    for tick in range(1, ticks_to_simulate + 1):
        # Implementation note.
        in_cell = env._get_cell(0, 2)
        if isinstance(in_cell, TransportComponent):
            target_item = getattr(in_cell, 'current_item', None)
            if target_item is None:
                in_cell.current_item = (MaterialType.IRON_ORE, 12.0)
            elif isinstance(target_item, tuple):
                mat, amt = target_item
                if mat == MaterialType.IRON_ORE and amt < 12.0:
                    in_cell.current_item = (MaterialType.IRON_ORE, min(12.0, amt + 12.0))

        # Implementation note.
        for b in env.buildings:
            if not hasattr(b, 'inventory'):
                b.inventory = {}
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if isinstance(port_cell, TransportComponent) and getattr(port_cell, 'current_item', None) is not None:
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0

                    if mat not in b.allowed_input_materials:
                        continue

                    current_inv = b.inventory.get(mat, 0)
                    max_inv = b.max_inventory

                    if current_inv < max_inv:
                        take_amt = min(amt, max_inv - current_inv)
                        b.inventory[mat] = current_inv + take_amt

                        if amt - take_amt > 0:
                            port_cell.current_item = (mat, amt - take_amt)
                        else:
                            port_cell.current_item = None

        # Implementation note.
        env.tick()

        # Implementation note.
        out_cell = env._get_cell(31, 10)
        out_item = getattr(out_cell, 'current_item', None)
        if out_item is not None:
            if isinstance(out_item, tuple):
                mat, amt = out_item
                if mat == MaterialType.IRON_PLATE:
                    total_iron_plate_yield += amt
            else:
                if out_item == MaterialType.IRON_PLATE:
                    total_iron_plate_yield += 1
            out_cell.current_item = None

        # ==========================================
        # Implementation note.
        # ==========================================
        if steady_state_entry_tick == -1:
            current_state = get_factory_state(env)

            if current_state in state_history:
                # Implementation note.
                steady_state_entry_tick = state_history[current_state]
                steady_state_period = tick - steady_state_entry_tick

                # Implementation note.
                yield_in_period = total_iron_plate_yield - yield_history[steady_state_entry_tick]
                steady_yield_per_tick = yield_in_period / steady_state_period
            else:
                # Implementation note.
                state_history[current_state] = tick
                yield_history[tick] = total_iron_plate_yield

        # Implementation note.
        agent.render_blueprint(env, tick, total_iron_plate_yield)
        time.sleep(0.1)

    # Implementation note.
    print(f"Simulation finished. Total iron plate output: {total_iron_plate_yield}")
    print('AutoBlueprint status message.')
    if steady_state_entry_tick != -1:
        print(f"Steady-state entry tick: {steady_state_entry_tick}")
        print(f"Steady-state period: {steady_state_period} ticks")
        print(f"Average steady-state yield: {steady_yield_per_tick:.2f} per tick")
        if steady_yield_per_tick >= target_outputs[MaterialType.IRON_PLATE]:
            print('AutoBlueprint status message.')
        else:
            print('AutoBlueprint status message.')
    else:
        print(f"Factory did not reach perfect steady state within {ticks_to_simulate} ticks.")


if __name__ == "__main__":
    run_test()