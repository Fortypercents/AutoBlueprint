from entities.transport import Direction, TransportComponent


def _get_building_cell_str(building, cx, cy):
    # ... (保持原有的渲染框逻辑不变) ...
    ax, ay = getattr(building, 'anchor_pos', (cx, cy))
    w, h = getattr(building, 'size', (1, 1))
    rx, ry = cx - ax, cy - ay

    if not (0 <= rx < w and 0 <= ry < h): return "[?]"

    if ry == 0 or ry == h - 1:
        if w == 1: return "+-+"
        if rx == 0:
            return "+--"
        elif rx == w - 1:
            return "--+"
        else:
            return "---"
    else:
        if rx == w // 2 and ry == h // 2:
            cid = getattr(building, 'component_id', 0)
            if cid in [511, 512, 513]:
                abbr = "REF"
            elif cid in [521, 522, 523, 524]:
                abbr = "CRU"
            elif cid in [531, 532]:
                abbr = "PRT"
            elif cid in [541, 542]:
                abbr = "PRS"
            elif cid in [551, 552]:
                abbr = "PAK"
            elif cid == 401:
                abbr = "PLT"
            elif cid == 402:
                abbr = "EXT"
            else:
                abbr = str(cid)[:3].center(3)
            return abbr
        else:
            if rx == 0:
                return "|  "
            elif rx == w - 1:
                return "  |"
            else:
                return "   "


def render_system_b_blueprint(env, tick=0, status_text=""):
    print("\n" * 3)
    print(f"=== 🏭 AutoBlueprint Simulation [Tick {tick:03d}] | {status_text} ===")

    dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}

    for y in range(env.height):
        row_str = f"{y:02d} |"
        for x in range(env.width):
            cell = env._get_cell(x, y)
            if cell is None:
                row_str += " . "
            elif hasattr(cell, 'size'):
                row_str += _get_building_cell_str(cell, x, y)
            elif isinstance(cell, TransportComponent):
                c_name = type(cell).__name__
                is_crosser = "Crosser" in c_name
                is_router = "Router" in c_name or "Splitter" in c_name
                is_merger = "Merger" in c_name

                out_dir = getattr(cell, 'direction', Direction.RIGHT)
                in_dir = getattr(cell, 'in_dir', out_dir)

                dir_char = dir_symbols.get(out_dir, "*")

                # 【视觉核心】：当输入和输出方向不同时，渲染精美的转向字符
                if in_dir != out_dir and not (is_crosser or is_router or is_merger):
                    turn_map = {
                        (Direction.UP, Direction.RIGHT): '└',
                        (Direction.LEFT, Direction.UP): '┘',
                        (Direction.UP, Direction.LEFT): '┘',
                        (Direction.RIGHT, Direction.UP): '└',
                        (Direction.DOWN, Direction.RIGHT): '┌',
                        (Direction.LEFT, Direction.DOWN): '┐',
                        (Direction.DOWN, Direction.LEFT): '┐',
                        (Direction.RIGHT, Direction.DOWN): '┌'
                    }
                    dir_char = turn_map.get((in_dir, out_dir), dir_char)

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