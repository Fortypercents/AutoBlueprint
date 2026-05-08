import sys
import os

# 确保可以导入项目模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.generic_baseline_agent import GenericBaselineAgent
from utils.test_utils import render_system_b_blueprint


def run_test():
    # 1. 准备足够大的画布。由于三级生产链建筑较多，建议开大地图。
    env = GridMap(50, 45)

    # 2. 定义外部接口坐标
    # 蓝铁输入点 (多个点以应对高产量需求)
    iron_inputs = [(5, 0), (7, 0)]
    # 源石输入点
    ori_inputs = [(20, 0), (22, 0), (24, 0)]
    # 最终电池产出点
    battery_outputs = [(25, 44)]

    # 3. 初始化 Agent
    # 目标：产量为 1.0 的中容谷地电池
    # 原料：蓝铁 和 源石
    agent = GenericBaselineAgent(
        target_outputs={MaterialType.BLUE_IRON_BOTTLE: 3.0},
        available_inputs=[MaterialType.BLUE_IRON, MaterialType.ORIGINIUM]
    )

    # 4. 执行规划与排线
    # Agent 会自动将蓝铁输入连至精炼炉，源石输入连至粉碎机
    agent.optimize(
        env,
        external_in={
            MaterialType.BLUE_IRON: iron_inputs,
            MaterialType.ORIGINIUM: ori_inputs
        },
        external_out={
            MaterialType.BLUE_IRON_BOTTLE: battery_outputs
        }
    )

    # 唤醒引擎拓扑检测
    for b in env.buildings:
        env.update_connections(b)

    # 5. 物理模拟与动态点火测试
    total_yield = 0
    ticks_to_simulate = 70  # 三级产线较长，增加模拟时长以观察产出

    print("=== ⚙️ ENDFIELD 电池产线规划完毕，开始点火测试 ===")
    for tick in range(1, ticks_to_simulate + 1):

        # A. 外部原料投放 (点火)
        if tick <= 50:  # 持续投放原料
            # 投放蓝铁
            for fx, fy in iron_inputs:
                cell = env._get_cell(fx, fy)
                if cell and getattr(cell, 'current_item', None) is None:
                    cell.current_item = (MaterialType.BLUE_IRON, 1.0)
            # 投放源石
            for fx, fy in ori_inputs:
                cell = env._get_cell(fx, fy)
                if cell and getattr(cell, 'current_item', None) is None:
                    cell.current_item = (MaterialType.ORIGINIUM, 1.0)

        # B. 机器消化逻辑 (System B 标准逻辑)
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

        # C. 引擎 Tick
        env.tick()

        # D. 终端产物收集
        for ox, oy in battery_outputs:
            cell = env._get_cell(ox, oy)
            if cell and type(cell).__name__ == "SystemBBelt":
                item = getattr(cell, 'current_item', None)
                if item:
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0
                    # 检查是否为中容电池
                    if mat == MaterialType.MID_CAP_BATTERY:
                        total_yield += amt
                        cell.current_item = None

        # 每 2 Tick 渲染一次，防止屏幕闪烁过快
        if tick % 2 == 0:
            status = f"已产出中容电池: {total_yield:.1f} 个"
            render_system_b_blueprint(env, tick, status)
            time.sleep(0.02)


if __name__ == "__main__":
    run_test()