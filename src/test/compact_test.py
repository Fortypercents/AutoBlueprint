import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.material import MaterialType
from entities.transport import TransportComponent
from environment.grid_map import GridMap
from agents.compact_layout_agent import CompactLayoutAgent


def run_test():
    target_outputs = {MaterialType.IRON_INGOT: 2.0}

    # 实例化 Agent 和环境地图
    agent = CompactLayoutAgent(target_outputs, ext_in=(0, 2), ext_out=(31, 20))
    env = GridMap(32, 22)

    print("=== 🚀 开始生成紧凑型工厂布局 ===")
    agent.optimize(env)

    # 更新建筑接口连接
    for b in env.buildings:
        env.update_connections(b)

    required_inputs = agent.raw_material_inputs
    main_input_mat = list(required_inputs.keys())[0] if required_inputs else MaterialType.IRON_ORE

    print("\n=== ⚙️ 开始动态物流流转模拟 ===")
    collected_yields = {MaterialType.IRON_INGOT: 0.0}
    ticks_to_simulate = 100

    for tick in range(1, ticks_to_simulate + 1):
        # A. 从源头持续注入矿石 (保持满载 12 单位/格，确保持续输入)
        in_cell = env._get_cell(*agent.ext_in)
        if isinstance(in_cell, TransportComponent):
            target_item = getattr(in_cell, 'current_item', None)
            if target_item is None:
                in_cell.current_item = (main_input_mat, 12.0)
            elif isinstance(target_item, tuple):
                mat, amt = target_item
                if mat == main_input_mat and amt < 12.0:
                    # 将不足 12 的量强行拉满
                    in_cell.current_item = (main_input_mat, min(12.0, amt + 12.0))

        # B. 机器吃料 (严格限制特定输入)
        for b in env.buildings:
            if not hasattr(b, 'inventory'):
                b.inventory = {}

            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if port_cell and getattr(port_cell, 'current_item', None):
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0

                    # 修复：从检查 input_materials 改为检查 allowed_input_materials
                    if mat in getattr(b, 'allowed_input_materials', []):
                        current_inv = b.inventory.get(mat, 0)
                        max_inv = b.max_inventory
                        if current_inv < max_inv:
                            take_amt = min(amt, max_inv - current_inv)
                            b.inventory[mat] = current_inv + take_amt
                            port_cell.current_item = (mat, amt - take_amt) if amt - take_amt > 0 else None

        # C. 物理引擎 Tick
        env.tick()

        # D. 终点收集
        out_cell = env._get_cell(*agent.ext_out)
        out_item = getattr(out_cell, 'current_item', None)
        if out_item is not None:
            mat, amt = out_item if isinstance(out_item, tuple) else (out_item, 1.0)
            if mat in collected_yields:
                collected_yields[mat] += amt
            out_cell.current_item = None

        # E. 渲染包含字母图例的画面
        agent.render_blueprint(env, tick, collected_yields)
        time.sleep(0.08)

    print(f"\n✅ 模拟结束！Agent 成功完成了紧凑布局，共产出 {collected_yields[MaterialType.IRON_INGOT]} 个铁块！")


if __name__ == "__main__":
    run_test()