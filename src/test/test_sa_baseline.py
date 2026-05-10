import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.sa_baseline_agent import SABaselineAgent
from utils.test_utils import render_system_b_blueprint

def run_test():
    env = GridMap(45, 45)

    # 1. 设立目标：产出 BLUE_IRON_BOTTLE，系统提供 BLUE_IRON
    agent = SABaselineAgent(
        target_outputs={MaterialType.BLUE_IRON_BOTTLE: 4.0},
        available_inputs=[MaterialType.BLUE_IRON]
    )

    # Agent全自动托管执行：配方反推 -> SA全局布局 -> 浮动引脚连线
    agent.optimize(env)

    # 初始化物理连接
    for b in env.buildings:
        env.update_connections(b)

    total_yield = 0
    ticks_to_simulate = 200

    print("=== ⚙️ SA-Baseline Autonomous Blueprint Generated ===")
    for tick in range(1, ticks_to_simulate + 1):

        # A. 灌注原料：测试脚本向 Agent 自动分配的进货口 (y=0 附近) 喂料
        if tick <= 40:
            for mat, in_ports in agent.generated_inputs.items():
                for fx, fy in in_ports:
                    cell = env._get_cell(fx, fy)
                    if cell and getattr(cell, 'current_item', None) is None:
                        cell.current_item = (mat, 1.0)

        # B. 内部物流推进与机器消耗
        for b in env.buildings:
            if not hasattr(b, 'inventory'): b.inventory = {}
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if port_cell and getattr(port_cell, 'current_item', None) is not None:
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0
                    if mat in getattr(b, 'allowed_input_materials', b.input_materials.keys()):
                        max_inv = getattr(b, 'max_inventory', 10.0)
                        current_inv = b.inventory.get(mat, 0)
                        if current_inv < max_inv:
                            take_amt = min(amt, max_inv - current_inv)
                            b.inventory[mat] = current_inv + take_amt
                            port_cell.current_item = (mat, amt - take_amt) if amt - take_amt > 0 else None

        env.tick()

        # C. 收集产物：从 Agent 规划到屏幕最下方的出货口 (y=height-1) 取货
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