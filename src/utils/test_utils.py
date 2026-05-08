# 文件路径: src/test/test_utils.py
from entities.transport import Direction, TransportComponent
from environment.grid_map import GridMap


def render_system_b_blueprint(env: GridMap, tick: int = 0, status_text: str = ""):
    """
    通用渲染函数：带横纵坐标、适配 System B 体系的控制台渲染器
    """
    print("\n" * 5)
    print(f"=== 🏭 自动化泛用蓝图测试 [Tick {tick:03d}] | {status_text} ===")

    dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}

    for y in range(env.height):
        row_str = f"{y:02d} |"
        for x in range(env.width):
            cell = env._get_cell(x, y)
            if cell is None:
                row_str += " . "
            elif hasattr(cell, 'size'):
                # 兼容显示：种植机为P，其余处理设备默认显示首字母
                if cell.component_id == 401:
                    row_str += "[P]"
                elif cell.component_id == 402:
                    row_str += "[E]"
                else:
                    row_str += f"[{getattr(cell, 'name', '?')[0]}]"
            elif isinstance(cell, TransportComponent):
                c_name = type(cell).__name__
                is_crosser = "Crosser" in c_name
                is_router = "Router" in c_name or "Splitter" in c_name
                is_merger = "Merger" in c_name

                dir_char = dir_symbols.get(getattr(cell, 'direction', Direction.RIGHT), "*")
                item = getattr(cell, 'current_item', None)

                if item is not None:
                    amt = int(item[1]) if isinstance(item, tuple) else 1
                    base_char = "X" if is_crosser else "M" if is_merger else "S" if is_router else dir_char
                    row_str += f"{base_char}{amt:02d}"
                else:
                    base_char = "[X]" if is_crosser else "[M]" if is_merger else "[S]" if is_router else f" {dir_char} "
                    row_str += base_char
            else:
                row_str += "[?]"
        print(row_str)

    print("   " + "-" * (env.width * 3 + 2))
    header_x = "    "
    for x in range(env.width):
        header_x += f"{x:02d} " if x % 2 == 0 else "   "
    print(header_x)
    print("=====================================================================")