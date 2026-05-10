import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.fdp_sa_agent import FdpSaAgent
from utils.test_utils import render_system_b_blueprint

def run_test():
    env = GridMap(45, 45)

    # 1. 设立目标：利用蓝铁，生产 2 瓶蓝铁瓶
    # agent = FdpSaAgent(
    #     target_outputs={MaterialType.BLUE_IRON_BOTTLE: 3.0},
    #     available_inputs=[MaterialType.BLUE_IRON]
    # )

    agent = FdpSaAgent(
        target_outputs={MaterialType.MID_CAP_BATTERY: 1.0},
        available_inputs=[MaterialType.BLUE_IRON, MaterialType.ORIGINIUM]
    )

    # 2. 一键交由 Agent 托管执行全局布局、旋转微调和寻路连线
    agent.optimize(env)

    # 3. 初始化物理连接
    for b in env.buildings:
        env.update_connections(b)

    total_yield = 0
    ticks_to_simulate = 200

    print("=== ⚙️ FDP+SA Agent Autonomous Blueprint Generated ===")
    for tick in range(1, ticks_to_simulate + 1):

        # A. 灌注原料：测试脚本负责向 Agent 自动分配的进货口进行喂料
        if tick <= 60:
            for mat, in_ports in agent.generated_inputs.items():
                for ix, iy in in_ports:
                    cell = env._get_cell(ix, iy)
                    if cell and type(cell).__name__ == "SystemBBelt":
                        if getattr(cell, 'current_item', None) is None:
                            cell.current_item = (mat, 1.0)

        # B. 机器吃料模拟
        for b in env.buildings:
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if port_cell and getattr(port_cell, 'current_item', None):
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

        # 步进物理引擎
        env.tick()

        # C. 收集产物：从 Agent 规划到屏幕最下方的出货口取货
        for mat, out_ports in agent.generated_outputs.items():
            for ox, oy in out_ports:
                cell = env._get_cell(ox, oy)
                if cell and type(cell).__name__ == "SystemBBelt":
                    item = getattr(cell, 'current_item', None)
                    if item:
                        item_mat = item[0] if isinstance(item, tuple) else item
                        item_amt = item[1] if isinstance(item, tuple) else 1.0
                        if item_mat == MaterialType.MID_CAP_BATTERY:
                            total_yield += item_amt
                            cell.current_item = None

        # 每几帧渲染一次动画
        if tick % 2 == 0:
            status = f"Yield {total_yield:.1f} / 2.0 BOTTLES | Tick {tick}"
            render_system_b_blueprint(env, tick=tick, status_text=status)
            time.sleep(0.05)

    print(f"\n✅ 模拟测试结束！共收集目标产物: {total_yield:.1f} 个")

if __name__ == "__main__":
    run_test()