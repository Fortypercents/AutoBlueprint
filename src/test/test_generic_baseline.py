import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.generic_baseline_agent import GenericBaselineAgent
from utils.test_utils import render_system_b_blueprint


def run_test():
    env = GridMap(45, 45)

    # 1. 设立目标：2蓝铁锭 -> 1蓝铁瓶，需要 2台精炼炉对准1台压制机
    agent = GenericBaselineAgent(
        target_outputs={MaterialType.BLUE_IRON_BOTTLE: 3.0},
        available_inputs=[MaterialType.BLUE_IRON]
    )

    # Agent全自动托管，无需再传递 external_in 和 external_out
    agent.optimize(env)

    for b in env.buildings:
        env.update_connections(b)

    total_yield = 0
    ticks_to_simulate = 200

    print("=== ⚙️ ENDFIELD Autonomous Blueprint Generated (2:1 Smart Routing) ===")
    for tick in range(1, ticks_to_simulate + 1):

        # A. 测试脚本向 Agent 自动分配的进货口灌注原料
        if tick <= 40:
            for mat, in_ports in agent.generated_inputs.items():
                for fx, fy in in_ports:
                    cell = env._get_cell(fx, fy)
                    if cell and getattr(cell, 'current_item', None) is None:
                        cell.current_item = (mat, 1.0)

        # B. 内部物流推进与消耗
        for b in env.buildings:
            if not hasattr(b, 'inventory'): b.inventory = {}
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if port_cell and getattr(port_cell, 'current_item', None) is not None:
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0
                    if mat in b.allowed_input_materials:
                        current_inv = b.inventory.get(mat, 0)
                        if current_inv < b.max_inventory:
                            take_amt = min(amt, b.max_inventory - current_inv)
                            b.inventory[mat] = current_inv + take_amt
                            port_cell.current_item = (mat, amt - take_amt) if amt - take_amt > 0 else None

        env.tick()

        # C. 从 Agent 自动拉到屏幕最下方的出货口收集产物
        for mat, out_ports in agent.generated_outputs.items():
            for ox, oy in out_ports:
                cell = env._get_cell(ox, oy)
                if cell and type(cell).__name__ == "SystemBBelt":
                    item = getattr(cell, 'current_item', None)
                    if item:
                        item_mat = item[0] if isinstance(item, tuple) else item
                        item_amt = item[1] if isinstance(item, tuple) else 1.0
                        if item_mat == MaterialType.BLUE_IRON_BOTTLE:
                            total_yield += item_amt
                            cell.current_item = None

        if tick % 2 == 0:
            status = f"Yield (BLUE_IRON_BOTTLE): {total_yield:.1f}"
            render_system_b_blueprint(env, tick, status)
            time.sleep(0.04)


if __name__ == "__main__":
    run_test()