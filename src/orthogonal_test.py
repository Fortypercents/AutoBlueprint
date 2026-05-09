import time
import sys
import os

# 确保能够导入 src 下的模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.material import MaterialType
from entities.transport import TransportComponent
from environment.grid_map import GridMap

# 导入分离出来的 Agent
from src.agents.old_agents.cascading_bus_agent import CascadingBusAgent


def run_test():
    target_outputs = {MaterialType.IRON_INGOT: 2.0}

    # 实例化 Agent 和环境地图
    agent = CascadingBusAgent(target_outputs, ext_in=(0, 2), ext_out=(35, 22))
    env = GridMap(36, 26)

    # 运行布局算法
    agent.optimize(env)

    # 更新建筑接口连接
    for b in env.buildings:
        env.update_connections(b)

    required_inputs = agent.raw_material_inputs
    main_input_mat = list(required_inputs.keys())[0] if required_inputs else MaterialType.IRON_ORE

    print("=== ⚙️ 开始物理仿真 (2 铁矿石 = 1 铁板) ===")
    collected_yields = {MaterialType.IRON_INGOT: 0.0}
    ticks_to_simulate = 100

    for tick in range(1, ticks_to_simulate + 1):
        # A. 从源头注入矿石
        in_cell = env._get_cell(*agent.ext_in)
        if isinstance(in_cell, TransportComponent):
            target_item = getattr(in_cell, 'current_item', None)
            if target_item is None:
                in_cell.current_item = (main_input_mat, 12.0)
            elif isinstance(target_item, tuple):
                mat, amt = target_item
                if mat == main_input_mat and amt < 12.0:
                    in_cell.current_item = (main_input_mat, min(12.0, amt + 12.0))

        # B. 机器消化与制造 (修复缩进：已退回与 A 并列层级)
        for b in env.buildings:
            if not hasattr(b, 'inventory'):
                b.inventory = {}

            # 吃料
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

        # C. 物理引擎 Tick (引擎会自动处理生产和产物弹出)
        env.tick()

        # D. 终点收集
        out_cell = env._get_cell(*agent.ext_out)
        out_item = getattr(out_cell, 'current_item', None)
        if out_item is not None:
            mat, amt = out_item if isinstance(out_item, tuple) else (out_item, 1.0)
            if mat in collected_yields:
                collected_yields[mat] += amt
            out_cell.current_item = None

        # 渲染画面
        agent.render_blueprint(env, tick, collected_yields)
        time.sleep(0.08)

    print(f"\n✅ 模拟结束！Agent 成功推断出并联关系，共产出 {collected_yields[MaterialType.IRON_INGOT]} 个产物！")


if __name__ == "__main__":
    run_test()