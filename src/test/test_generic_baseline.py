# 文件路径: src/test/test_generic_baseline.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from environment.grid_map import GridMap
from entities.material import MaterialType
from agents.generic_baseline_agent import GenericBaselineAgent
from test.test_utils import render_system_b_blueprint  # 导入复用的渲染函数


def run_test():
    # 1. 初始化大网格环境
    env = GridMap(40, 25)

    # 2. 定义需求：只要告诉 Agent 你要什么，你有什么
    # 场景：提供苹果种子，要求全自动推导并生成能产出苹果的整条流水线
    agent = GenericBaselineAgent(
        target_outputs=[MaterialType.APPLE],
        available_inputs=[MaterialType.APPLE_SEED]
    )

    # 3. 自动规划与寻路排线
    agent.optimize(env)

    # 确保所有连接都已更新
    for b in env.buildings:
        env.update_connections(b)

    # 4. 物理模拟与动态点火测试
    total_yield = 0
    ticks_to_simulate = 100

    # 找到所有的种植机 (作为动态点火的目标)
    source_buildings = [b for b in env.buildings if MaterialType.APPLE_SEED in b.allowed_input_materials]

    for tick in range(1, ticks_to_simulate + 1):
        # 自动点火：只在最初几个 Tick 给源头机器喂入种子
        if tick <= 5:
            for b in source_buildings:
                if not hasattr(b, 'inventory'): b.inventory = {}
                current_seed = b.inventory.get(MaterialType.APPLE_SEED, 0)
                if current_seed < b.max_inventory:
                    b.inventory[MaterialType.APPLE_SEED] = current_seed + 1

        # 机器消化逻辑
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

        # 物理 Tick 推进
        env.tick()

        # 自动终端收集：扫描所有传送带最末端的格子，收集目标产物
        for x in range(env.width):
            for y in range(env.height):
                cell = env._get_cell(x, y)
                if cell and type(cell).__name__ == "SystemBBelt":
                    # 简化判定：如果传送带上有我们要的苹果，且它位于传送带网络末端或已被推出
                    item = getattr(cell, 'current_item', None)
                    if item:
                        mat = item[0] if isinstance(item, tuple) else item
                        amt = item[1] if isinstance(item, tuple) else 1.0
                        if mat == MaterialType.APPLE:
                            # 提取并销毁物品
                            total_yield += amt
                            cell.current_item = None

        # 调用公共复用函数渲染画面
        render_system_b_blueprint(env, tick, f"动态产出苹果: {total_yield} 个")
        time.sleep(0.05)


if __name__ == "__main__":
    run_test()