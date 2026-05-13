import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agents.sequence_pair_sa_agent_v2 import SequencePairSaAgentV2
from entities.material import MaterialType
from environment.grid_map import GridMap
from utils.test_utils import render_system_b_blueprint


def layout_area(agent: SequencePairSaAgentV2) -> int:
    if not agent.node_positions:
        return 0
    min_x = min_y = float("inf")
    max_x = max_y = -float("inf")
    for state in agent.node_positions.values():
        w, h = agent._real_size(state)
        min_x = min(min_x, state["x"])
        min_y = min(min_y, state["y"])
        max_x = max(max_x, state["x"] + w)
        max_y = max(max_y, state["y"] + h)
    return int((max_x - min_x) * (max_y - min_y))


def run_test(render: bool = True):
    random.seed(16)
    env = GridMap(45, 45)

    agent = SequencePairSaAgentV2(
        target_outputs={MaterialType.MID_CAP_BATTERY: 2.0},
        available_inputs=[MaterialType.BLUE_IRON, MaterialType.ORIGINIUM],
    )

    agent.optimize(env)
    print(f"=== Sequence Pair + SA V2 layout area: {layout_area(agent)} cells ===")
    print(f"=== Routed belts/crossers: {len(env.transports)} | failed routes: {len(agent.failed_routes)} ===")
    if agent.failed_routes:
        raise AssertionError(f"Sequence Pair + SA V2 has unresolved routes: {len(agent.failed_routes)}")

    for building in env.buildings:
        env.update_connections(building)

    total_yield = 0.0
    ticks_to_simulate = 180

    for tick in range(1, ticks_to_simulate + 1):
        if tick <= 60:
            for mat, in_ports in agent.generated_inputs.items():
                for ix, iy in in_ports:
                    cell = env._get_cell(ix, iy)
                    if cell and type(cell).__name__ == "SystemBBelt":
                        if getattr(cell, "current_item", None) is None:
                            cell.current_item = (mat, 1.0)

        for building in env.buildings:
            for px, py in building.active_input_ports:
                port_cell = env._get_cell(px, py)
                if port_cell and getattr(port_cell, "current_item", None):
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0
                    if mat in getattr(building, "allowed_input_materials", building.input_materials.keys()):
                        max_inv = getattr(building, "max_inventory", 10.0)
                        current_inv = building.inventory.get(mat, 0)
                        if current_inv < max_inv:
                            take_amt = min(amt, max_inv - current_inv)
                            building.inventory[mat] = current_inv + take_amt
                            port_cell.current_item = (mat, amt - take_amt) if amt - take_amt > 0 else None

        env.tick()

        for _mat, out_ports in agent.generated_outputs.items():
            for ox, oy in out_ports:
                cell = env._get_cell(ox, oy)
                if cell and type(cell).__name__ == "SystemBBelt":
                    item = getattr(cell, "current_item", None)
                    if item:
                        item_mat = item[0] if isinstance(item, tuple) else item
                        item_amt = item[1] if isinstance(item, tuple) else 1.0
                        if item_mat == MaterialType.MID_CAP_BATTERY:
                            total_yield += item_amt
                            cell.current_item = None

        if render and tick % 2 == 0:
            status = f"SP-SA V2 Area {layout_area(agent)} | Yield {total_yield:.1f} | Tick {tick}"
            render_system_b_blueprint(env, tick=tick, status_text=status)
            time.sleep(0.05)

    print(f"Sequence Pair + SA V2 simulation finished, collected target output: {total_yield:.1f}")
    if total_yield <= 0:
        raise AssertionError("Sequence Pair + SA V2 produced no MID_CAP_BATTERY output.")


if __name__ == "__main__":
    run_test(render="--no-render" not in sys.argv)
