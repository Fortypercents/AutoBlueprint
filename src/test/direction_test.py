import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction, TransportComponent
from environment.grid_map import GridMap
from entities.material import MaterialType
from utils.test_utils import render_system_b_blueprint


def run_blue_iron_validation():
    env = GridMap(30, 15)

    b_refinery = get_building_instance(513)
    b_part_maker = get_building_instance(532)

    # 1. 放置建筑：精炼炉向右(90度)，配件机向左(270度)
    env.place_building(b_refinery, 8, 4, Direction.RIGHT)
    env.place_building(b_part_maker, 16, 4, Direction.LEFT)

    # 2. 修正后的传送带铺设函数 (严格遵守物理接收面逻辑)
    def place_belt(x, y, out_d, in_d=None):
        belt = get_transport_instance(301)
        env.place_transport(belt, x, y, out_d)

        if in_d is not None:
            belt.in_dir = in_d
        else:
            # 如果是直道，默认接收面在输出方向的【正对面】
            opposite = {
                Direction.UP: Direction.DOWN,
                Direction.DOWN: Direction.UP,
                Direction.LEFT: Direction.RIGHT,
                Direction.RIGHT: Direction.LEFT
            }
            belt.in_dir = opposite[out_d]

    # (A) 源头输入：向左传输，接收面在右侧
    place_belt(14, 4, Direction.LEFT)
    place_belt(13, 4, Direction.LEFT)
    place_belt(12, 4, Direction.LEFT)
    place_belt(11, 4, Direction.LEFT)

    # (B) 精炼炉 -> 配件机 (绕底一圈，严谨配置受力面)
    place_belt(7, 6, Direction.LEFT)  # 直出
    place_belt(6, 6, Direction.DOWN, Direction.RIGHT)  # 从右面进，向下面出 -> 渲染为 ┌
    place_belt(6, 7, Direction.DOWN)  # 直下
    place_belt(6, 8, Direction.RIGHT, Direction.UP)  # 从上面进，向右面出 -> 渲染为 └
    for x in range(7, 14):
        place_belt(x, 8, Direction.RIGHT)  # 向右直行
    place_belt(14, 8, Direction.UP, Direction.LEFT)  # 从左面进，向上面出 -> 渲染为 ┘
    place_belt(14, 7, Direction.UP)  # 直上
    place_belt(14, 6, Direction.RIGHT, Direction.DOWN)  # 从下面进，向右面出 -> 渲染为 ┌
    place_belt(15, 6, Direction.RIGHT)  # 扎入机器

    # (C) 最终产出管道
    place_belt(19, 5, Direction.RIGHT)
    place_belt(20, 5, Direction.RIGHT)
    place_belt(21, 5, Direction.RIGHT)
    place_belt(22, 5, Direction.RIGHT)

    for b in env.buildings:
        env.update_connections(b)
        if not hasattr(b, 'inventory'): b.inventory = {}
        if not hasattr(b, 'output_buffer'): b.output_buffer = {}

    total_parts_collected = 0

    # 3. 运行 80 帧，确保物品跑完全程
    for tick in range(1, 80):
        # 持续喂入蓝铁
        start_belt = env._get_cell(14, 4)
        if isinstance(start_belt, TransportComponent) and start_belt.current_item is None:
            start_belt.current_item = (MaterialType.BLUE_IRON, 1.0)

        for b in env.buildings:
            for px, py in b.active_input_ports:
                cell = env._get_cell(px, py)
                if isinstance(cell, TransportComponent) and getattr(cell, 'current_item', None):
                    item = cell.current_item
                    mat = item[0] if isinstance(item, tuple) else item
                    amt = item[1] if isinstance(item, tuple) else 1.0
                    if mat in b.allowed_input_materials:
                        b.inventory[mat] = b.inventory.get(mat, 0) + amt
                        cell.current_item = None

        env.tick()

        # 收集末端物品
        end_belt = env._get_cell(22, 5)
        if isinstance(end_belt, TransportComponent) and end_belt.current_item is not None:
            item = end_belt.current_item
            mat = item[0] if isinstance(item, tuple) else item
            if mat == MaterialType.BLUE_IRON_PART:
                total_parts_collected += 1
            end_belt.current_item = None

        render_system_b_blueprint(env, tick=tick, status_text=f"蓝铁加工测试 | 收集零件: {total_parts_collected}")
        time.sleep(0.1)

    print(f"\n🎉 最终成功收集到: {total_parts_collected} 个蓝铁零件")


if __name__ == "__main__":
    run_blue_iron_validation()