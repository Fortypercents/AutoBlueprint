from typing import Dict, Tuple, Any
from entities.material import MaterialType
from entities.registry import get_transport_instance
from entities.transport import Direction, TransportComponent
from environment.grid_map import GridMap
from agents.base_agent import BaseAgent


class CascadingBusAgent(BaseAgent):
    """
    层级化瀑布流总线智能体 (Tier-Based Cascading Bus Agent)
    """

    def __init__(self, target_outputs, ext_in=(0, 2), ext_out=(33, 22)):
        super().__init__(target_outputs)
        self.ext_in = ext_in
        self.ext_out = ext_out

        # 默认使用体系A的物流组件
        self.belt_id = 102
        self.router_id = 110

    def _sort_buildings_by_dependency(self):
        """按层级 (Tier) 批量结算依赖关系，防止同级机器串联"""
        tiers = []
        pending = list(self.required_buildings)
        available_mats = set(self.raw_material_inputs.keys())

        while pending:
            tier_buildings = [b for b in pending if all(mat in available_mats for mat in b.input_materials)]

            if not tier_buildings:
                print("⚠️ 警告：检测到配方死锁或缺失前置原料！")
                tiers.append(pending)
                break

            tiers.append(tier_buildings)

            for b in tier_buildings:
                pending.remove(b)

            for b in tier_buildings:
                for out_mat in b.output_materials:
                    available_mats.add(out_mat)

        return tiers

    def optimize(self, env: GridMap):
        print("\n【Agent 思考中】开始解析多级生产链路拓扑关系...")
        self.calculate_production_chain()

        tiers = self._sort_buildings_by_dependency()

        for i, tier in enumerate(tiers):
            print(f" -> 层级 (Tier {i}): " + " | ".join([b.name for b in tier]))

        # === 开始层级化瀑布流铺设 ===
        current_bus_y = self.ext_in[1]
        last_out_x, last_out_y = self.ext_in
        current_x = self.ext_in[0] + 3

        for tier_idx, tier in enumerate(tiers):
            placed_b_info = []
            max_h = 0

            # 1. 并排摆放该层级的所有机器
            for b in tier:
                bx = current_x
                by = current_bus_y + 2

                if not env.place_building(b, bx, by):
                    print(f"❌ 警告：无法在 ({bx}, {by}) 放置 {b.name}，地图空间可能不足！")
                    continue

                bw, bh = b.size
                px = bx + bw // 2
                max_h = max(max_h, bh)

                placed_b_info.append((b, px, by, bw, bh))
                current_x += bw + 3

            if not placed_b_info:
                continue

            first_px = placed_b_info[0][1]
            last_px = placed_b_info[-1][1]
            splitter_xs = [p_info[1] for p_info in placed_b_info]

            # --- 2. 铺设该层的【输入横向总线】及分配器 (修复物理拓扑顺序) ---
            if last_out_y < current_bus_y:
                for y in range(last_out_y + 1, current_bus_y):
                    if env._get_cell(last_out_x, y) is None:
                        belt = get_transport_instance(self.belt_id)
                        env.place_transport(belt, last_out_x, y, Direction.DOWN)

            start_bus_x = min(last_out_x, first_px)
            for x in range(start_bus_x, last_px + 1):
                if x in splitter_xs:
                    b_info = next(info for info in placed_b_info if info[1] == x)
                    b, px, by, bw, bh = b_info

                    # 放置分配器
                    splitter = get_transport_instance(self.router_id)
                    env.place_transport(splitter, px, current_bus_y, Direction.RIGHT)

                    # 顺流放置进入机器的支线
                    for y in range(current_bus_y + 1, by):
                        belt = get_transport_instance(self.belt_id)
                        env.place_transport(belt, px, y, Direction.DOWN)
                else:
                    if env._get_cell(x, current_bus_y) is None:
                        belt = get_transport_instance(self.belt_id)
                        env.place_transport(belt, x, current_bus_y, Direction.RIGHT)

            # --- 3. 铺设该层的【输出横向总线】及汇流器 (修复物理拓扑顺序) ---
            out_bus_y = current_bus_y + 2 + max_h + 1

            for x in range(first_px, last_px + 1):
                if x in splitter_xs:
                    b_info = next(info for info in placed_b_info if info[1] == x)
                    b, px, by, bw, bh = b_info

                    # 从机器出来的支线 (上游)
                    for y in range(by + bh, out_bus_y):
                        belt = get_transport_instance(self.belt_id)
                        env.place_transport(belt, px, y, Direction.DOWN)

                    # 汇流器
                    merger = get_transport_instance(self.router_id)
                    env.place_transport(merger, px, out_bus_y, Direction.RIGHT)
                else:
                    if env._get_cell(x, out_bus_y) is None:
                        belt = get_transport_instance(self.belt_id)
                        env.place_transport(belt, x, out_bus_y, Direction.RIGHT)

            # 4. 在当前层输出总线的最末端，放置一个向下的皮带
            final_out_x = last_px + 1
            belt = get_transport_instance(self.belt_id)
            env.place_transport(belt, final_out_x, out_bus_y, Direction.DOWN)

            # 更新游标
            last_out_x = final_out_x
            last_out_y = out_bus_y
            current_bus_y = out_bus_y + 2

        # === 终点连接 ===
        out_x, out_y = self.ext_out
        for y in range(last_out_y + 1, out_y):
            belt = get_transport_instance(self.belt_id)
            env.place_transport(belt, last_out_x, y, Direction.DOWN)

        belt = get_transport_instance(self.belt_id)
        env.place_transport(belt, last_out_x, out_y, Direction.RIGHT)

        for x in range(last_out_x + 1, out_x + 1):
            belt = get_transport_instance(self.belt_id)
            env.place_transport(belt, x, out_y, Direction.RIGHT)

    def render_blueprint(self, env: GridMap, tick: int = 0, current_yield: Dict = None):
        yield_str = ", ".join([f"[{getattr(m, 'name', str(m))}]: {v}" for m, v in (current_yield or {}).items()])

        b_legend = {}
        letter_char = 'A'
        for b in env.buildings:
            if b.name not in b_legend:
                b_legend[b.name] = letter_char
                letter_char = chr(ord(letter_char) + 1)

        legend_str = " | ".join([f"[{v}] {k}" for k, v in b_legend.items()])

        print("\n" * 3)
        print(f"=== 🏭 层级瀑布流水线自动打样 [Tick {tick:03d}] ===")
        print(f"终端收集: {yield_str}")
        print(f"建筑图例: {legend_str}")
        print("=" * 64)

        dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}
        for y in range(env.height):
            row_str = ""
            for x in range(env.width):
                cell = env._get_cell(x, y)
                if cell is None:
                    row_str += " . "
                elif hasattr(cell, 'size'):
                    letter = b_legend.get(cell.name, '?')
                    row_str += f"[{letter}]"
                elif isinstance(cell, TransportComponent):
                    c_name = type(cell).__name__
                    is_router = "Router" in c_name or "Splitter" in c_name or "Merger" in c_name
                    direction = getattr(cell, 'direction', Direction.RIGHT)
                    dir_char = dir_symbols.get(direction, "*")

                    item = getattr(cell, 'current_item', None)
                    if item is not None:
                        amt = int(item[1]) if isinstance(item, tuple) else 1
                        base_char = "S" if is_router else dir_char
                        row_str += f"{amt:02d}{base_char}"
                    else:
                        row_str += f"[S]" if is_router else f" {dir_char} "
                else:
                    row_str += "[?]"
            print(f"{y:02d} {row_str}")
        print("=========================================================================")