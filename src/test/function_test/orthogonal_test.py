import time
import sys
import os

# Implementation note.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.material import MaterialType
from entities.transport import TransportComponent
from environment.grid_map import GridMap

# Implementation note.
from src.agents.old_agents.cascading_bus_agent import CascadingBusAgent


def run_test():
    target_outputs = {MaterialType.IRON_INGOT: 2.0}

    # Implementation note.
    agent = CascadingBusAgent(target_outputs, ext_in=(0, 2), ext_out=(35, 22))
    env = GridMap(36, 26)

    # Building placement logic.
    agent.optimize(env)

    # Building placement logic.
    for b in env.buildings:
        env.update_connections(b)

    required_inputs = agent.raw_material_inputs
    main_input_mat = list(required_inputs.keys())[0] if required_inputs else MaterialType.IRON_ORE

    print('AutoBlueprint status message.')
    collected_yields = {MaterialType.IRON_INGOT: 0.0}
    ticks_to_simulate = 100

    for tick in range(1, ticks_to_simulate + 1):
        # Implementation note.
        in_cell = env._get_cell(*agent.ext_in)
        if isinstance(in_cell, TransportComponent):
            target_item = getattr(in_cell, 'current_item', None)
            if target_item is None:
                in_cell.current_item = (main_input_mat, 12.0)
            elif isinstance(target_item, tuple):
                mat, amt = target_item
                if mat == main_input_mat and amt < 12.0:
                    in_cell.current_item = (main_input_mat, min(12.0, amt + 12.0))

        # Implementation note.
        for b in env.buildings:
            if not hasattr(b, 'inventory'):
                b.inventory = {}

            # Implementation note.
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if port_cell and getattr(port_cell, 'current_item', None):
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0

                    if mat in b.input_materials:
                        current_inv = b.inventory.get(mat, 0)
                        max_inv = b.max_inventory
                        if current_inv < max_inv:
                            take_amt = min(amt, max_inv - current_inv)
                            b.inventory[mat] = current_inv + take_amt
                            port_cell.current_item = (mat, amt - take_amt) if amt - take_amt > 0 else None

        # Implementation note.
        env.tick()

        # Implementation note.
        out_cell = env._get_cell(*agent.ext_out)
        out_item = getattr(out_cell, 'current_item', None)
        if out_item is not None:
            mat, amt = out_item if isinstance(out_item, tuple) else (out_item, 1.0)
            if mat in collected_yields:
                collected_yields[mat] += amt
            out_cell.current_item = None

        # Implementation note.
        agent.render_blueprint(env, tick, collected_yields)
        time.sleep(0.08)

    print("Simulation finished with collected output.")


if __name__ == "__main__":
    run_test()