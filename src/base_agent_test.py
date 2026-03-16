import time
import os
from typing import Dict, Tuple
from entities.material import MaterialType
from entities.registry import get_transport_instance
from entities.transport import Direction, TransportComponent, LogicRouter
from environment.grid_map import GridMap
from agents.base_agent import BaseAgent


class BlueprintTestAgent(BaseAgent):
    def optimize(self, env: GridMap):
        print("【Agent 开始构建主总线与汇流蓝图】...")
        in_belt_y, machine_y, out_belt_y = 2, 4, 8
        start_x, spacing = 2, 4
        last_mid_x = start_x

        for x in range(start_x + 1):
            belt = get_transport_instance(102)
            env.place_transport(belt, x, in_belt_y, Direction.RIGHT)

        for i, building in enumerate(self.required_buildings):
            current_x = start_x + i * spacing
            mid_x = current_x + 1
            last_mid_x = mid_x
            env.place_building(building, current_x, machine_y)

            splitter = get_transport_instance(110)
            env.place_transport(splitter, mid_x, in_belt_y, Direction.RIGHT)
            in_belt = get_transport_instance(102)
            env.place_transport(in_belt, mid_x, in_belt_y + 1, Direction.DOWN)

            out_belt = get_transport_instance(102)
            env.place_transport(out_belt, mid_x, out_belt_y - 1, Direction.DOWN)
            merger = get_transport_instance(110)
            env.place_transport(merger, mid_x, out_belt_y, Direction.RIGHT)

            if i < len(self.required_buildings) - 1:
                for gap_x in range(mid_x + 1, mid_x + spacing):
                    b_in = get_transport_instance(102)
                    env.place_transport(b_in, gap_x, in_belt_y, Direction.RIGHT)
                    b_out = get_transport_instance(102)
                    env.place_transport(b_out, gap_x, out_belt_y, Direction.RIGHT)

        for x in range(last_mid_x + 1, env.width - 1):
            b_out_final = get_transport_instance(102)
            env.place_transport(b_out_final, x, out_belt_y, Direction.RIGHT)

        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y, Direction.DOWN)
        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y + 1, Direction.DOWN)
        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y + 2, Direction.DOWN)

    def render_blueprint(self, env: GridMap, tick: int = 0, total_yield: float = 0):
        """动态渲染蓝图，显示传送带上的数量"""
        # 为了产生动画效果，在终端打印足够多的空行把旧画面顶上去
        print("\n" * 5)
        print(f"=== 🗺️ 满载 12/s 汇流管线动态模拟 [Tick {tick:03d}] | 累计产出: {total_yield} 个 ===")

        dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}
        grid_strs = []

        for y in range(env.height):
            row_str = ""
            for x in range(env.width):
                cell = env._get_cell(x, y)
                if cell is None:
                    row_str += " . "
                elif hasattr(cell, 'size') and cell.size == (3, 3):
                    row_str += "[F]"
                elif isinstance(cell, TransportComponent):
                    is_router = type(cell).__name__ == "LogicRouter"
                    direction = getattr(cell, 'direction', Direction.RIGHT)
                    dir_char = dir_symbols.get(direction, "*")

                    item = getattr(cell, 'current_item', None)
                    if item is not None:
                        # 提取数量并格式化为两位数，如 12 -> "12", 5 -> "05"
                        amt = int(item[1]) if isinstance(item, tuple) else 1
                        base_char = "S" if is_router else dir_char
                        # 带物品的显示格式：>12, v08, S12
                        row_str += f"{base_char}{amt:02d}"
                    else:
                        # 空组件显示格式：[S],  > ,  v
                        row_str += "[S]" if is_router else f" {dir_char} "
                else:
                    row_str += "[?]"
            grid_strs.append(f"{y:02d} {row_str}")

        for row in grid_strs:
            print(row)
        print("=====================================================================")


def run_test():
    target_outputs = {MaterialType.IRON_PLATE: 6.0}
    agent = BlueprintTestAgent(target_outputs)
    agent.calculate_production_chain()

    env = GridMap(32, 12)
    agent.optimize(env)

    for b in env.buildings:
        env.update_connections(b)

    # 初始空蓝图渲染
    agent.render_blueprint(env, 0, 0)
    time.sleep(1)

    print("=== ⚙️ 开始动态物流流转模拟 (12份/Tick) ===")
    total_iron_plate_yield = 0
    ticks_to_simulate = 80

    for tick in range(1, ticks_to_simulate + 1):
        # A. 左上角连续注入矿石 (保持 12.0 满载)
        in_cell = env._get_cell(0, 2)
        if isinstance(in_cell, TransportComponent):
            target_item = getattr(in_cell, 'current_item', None)
            if target_item is None:
                in_cell.current_item = (MaterialType.IRON_ORE, 12.0)
            elif isinstance(target_item, tuple):
                mat, amt = target_item
                if mat == MaterialType.IRON_ORE and amt < 12.0:
                    in_cell.current_item = (MaterialType.IRON_ORE, min(12.0, amt + 12.0))

        # B. 机器吃矿 (读取机器自身的属性进行安全过滤与容量控制)
        for b in env.buildings:
            if not hasattr(b, 'inventory'):
                b.inventory = {}
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if isinstance(port_cell, TransportComponent) and getattr(port_cell, 'current_item',
                                                                         None) is not None:

                    # 提取物品类型和数量
                    item = port_cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0

                    # 核心机制 1：输入白名单过滤 (只有在 allowed_input_materials 里的物品才吃)
                    if mat not in b.allowed_input_materials:
                        continue  # 物品不匹配，跳过，不吃

                    # 核心机制 2：动态读取这台机器的最大库存上限
                    current_inv = b.inventory.get(mat, 0)
                    max_inv = b.max_inventory

                    if current_inv < max_inv:
                        # 机器只能吃掉（最大容量 - 当前库存）和（传送带数量）中较小的那个
                        take_amt = min(amt, max_inv - current_inv)
                        b.inventory[mat] = current_inv + take_amt

                        # 结算传送带上剩余的物资
                        if amt - take_amt > 0:
                            port_cell.current_item = (mat, amt - take_amt)
                        else:
                            port_cell.current_item = None

        # C. 物理引擎 Tick
        env.tick()

        # D. 统计末端终点 (31, 10) 产量
        out_cell = env._get_cell(31, 10)
        out_item = getattr(out_cell, 'current_item', None)
        if out_item is not None:
            if isinstance(out_item, tuple):
                mat, amt = out_item
                if mat == MaterialType.IRON_PLATE:
                    total_iron_plate_yield += amt
            else:
                if out_item == MaterialType.IRON_PLATE:
                    total_iron_plate_yield += 1
            # 收集后清空末端
            out_cell.current_item = None

        # E. 打印本帧蓝图并暂停，形成动画
        agent.render_blueprint(env, tick, total_iron_plate_yield)
        time.sleep(0.15)  # 调节此数值可以改变动画播放速度 (秒)

    print(f"\n✅ 动画演示结束！蓝图内实际共收集满载产物: {total_iron_plate_yield} 个")


if __name__ == "__main__":
    run_test()