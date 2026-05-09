import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.sa_baseline_agent import SABaselineAgent
from utils.test_utils import render_system_b_blueprint


def run_advanced_sa_test():
    # 缩小地图看它的极限压缩能力
    env = GridMap(35, 35)

    # 设立目标：2蓝铁锭 -> 1蓝铁瓶。由于我们加入了“产能感知”，Agent 会自动计算需要几台机器。
    agent = SABaselineAgent(
        target_outputs={MaterialType.BLUE_IRON_BOTTLE: 1.0},
        available_inputs=[MaterialType.BLUE_IRON]
    )

    # 启动一键托管：DAG -> Wire-Inclusive SA -> Rip-up Routing
    agent.optimize(env)

    # 初始化物理引脚状态
    for b in env.buildings:
        env.update_connections(b)

    total_yield = 0
    ticks_to_simulate = 200

    print("\n" + "=" * 60)
    print("🚀 ADVANCED SA Blueprint Generated (Rotation + Rip-Up enabled)")
    print("=" * 60)

    for tick in range(1, ticks_to_simulate + 1):

        # A. 灌注外部原料
        if tick <= 50:
            for mat, in_ports in agent.generated_inputs.items():
                for fx, fy in in_ports:
                    cell = env._get_cell(fx, fy)
                    if cell and getattr(cell, 'current_item', None) is None:
                        cell.current_item = (mat, 1.0)

        # B. 内部机器消耗逻辑
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

        # 核心物理引擎流转
        env.tick()

        # C. 收集并统计底部产物
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

        # 控制台 UI 渲染
        if tick % 2 == 0:
            status = f"Tick: {tick:03d} | Yield (BOTTLE): {total_yield:.1f}"
            render_system_b_blueprint(env, tick, status)
            time.sleep(0.04)


if __name__ == "__main__":
    run_advanced_sa_test()