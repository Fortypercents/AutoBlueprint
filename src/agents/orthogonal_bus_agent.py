from typing import Dict, Tuple, List, Any
from entities.material import MaterialType
from entities.registry import get_transport_instance
from entities.transport import Direction, TransportComponent
from environment.grid_map import GridMap
from agents.base_agent import BaseAgent


class OrthogonalBusAgent(BaseAgent):
    """
    多级正交总线智能体 (Tiered Orthogonal Bus Agent)
    - 能够自动识别生产链路的深度。
    - 为每一级生产工序划分 Tier，并自动连接 Tier 之间的物流。
    """

    def __init__(self, target_outputs, ext_in=(0, 2), ext_out=(31, 20)):
        super().__init__(target_outputs)
        self.ext_in = ext_in
        self.ext_out = ext_out
        self.belt_id = 102  # 体系A：装甲传送带
        self.splitter_id = 110  # 体系A：分配器/汇流器

    def optimize(self, env: GridMap):
        print("\n【Agent 思考中】正在解析生产链路并划分层级...")
        self.calculate_production_chain()

        # 1. 层级划分 (简易版：根据建筑在 required_buildings 中的顺序)
        # 假设 BaseAgent.calculate_production_chain 返回的是按工序排序的建筑列表
        # Tier 0: 矿石 -> 铁板 (石炉)
        # Tier 1: 铁板 -> 铁块 (压制机)

        # 2. 动态布局参数
        current_y = self.ext_in[1]
        last_tier_out_bus_y = self.ext_in[1]

        # 为了演示多级，我们将建筑按 Tier 分行放置
        # 这里的逻辑是：每种建筑类型占一行
        unique_building_types = []
        for b in self.required_buildings:
            if b.component_id not in unique_building_types:
                unique_building_types.append(b.component_id)

        # 3. 逐层铺设
        next_input_bus_y = self.ext_in[1]

        for tier_idx, b_id in enumerate(unique_building_types):
            buildings_in_tier = [b for b in self.required_buildings if b.component_id == b_id]

            # 当前 Tier 的位置
            tier_machine_y = next_input_bus_y + 2
            tier_output_bus_y = tier_machine_y + 4

            print(f" -> 配置 Tier {tier_idx}: 放置 {len(buildings_in_tier)} 台设备 (ID:{b_id})")

            # 铺设输入总线 (从上一级的输出或外部输入接过来)
            start_x = self.ext_in[0]

            for i, b in enumerate(buildings_in_tier):
                bx = start_x + 4 + i * 6
                env.place_building(b, bx, tier_machine_y)
                env.update_connections(b)

                bw, bh = b.size
                px = bx + bw // 2

                # 连线：总线 -> 分配器 -> 机器输入
                # 水平总线
                for x in range(start_x, px + 1):
                    env.place_transport(get_transport_instance(self.belt_id), x, next_input_bus_y, Direction.RIGHT)

                # 分配器
                env.place_transport(get_transport_instance(self.splitter_id), px, next_input_bus_y, Direction.RIGHT)

                # 垂直支线进入机器
                for y in range(next_input_bus_y + 1, tier_machine_y):
                    env.place_transport(get_transport_instance(self.belt_id), px, y, Direction.DOWN)

                # 连线：机器输出 -> 汇流器 -> 输出总线
                # 垂直支线出机器
                for y in range(tier_machine_y + bh, tier_output_bus_y):
                    env.place_transport(get_transport_instance(self.belt_id), px, y, Direction.DOWN)

                # 汇流器
                env.place_transport(get_transport_instance(self.splitter_id), px, tier_output_bus_y, Direction.RIGHT)

                # 水平输出总线
                for x in range(px + 1, self.ext_out[0] if tier_idx == len(unique_building_types) - 1 else px + 7):
                    env.place_transport(get_transport_instance(self.belt_id), x, tier_output_bus_y, Direction.RIGHT)

            # 准备下一层级：将本层的输出总线作为下一层的输入总线
            if tier_idx < len(unique_building_types) - 1:
                # 往下拐弯，连接到下一层的起始点
                conn_x = self.ext_in[0] + 1
                for y in range(tier_output_bus_y + 1, tier_output_bus_y + 6):
                    env.place_transport(get_transport_instance(self.belt_id), conn_x, y, Direction.DOWN)
                next_input_bus_y = tier_output_bus_y + 6
            else:
                # 最后一层，连接到全局输出口
                last_bus_y = tier_output_bus_y
                for y in range(last_bus_y + 1, self.ext_out[1] + 1):
                    env.place_transport(get_transport_instance(self.belt_id), self.ext_out[0], y, Direction.DOWN)

    def render_blueprint(self, env: GridMap, tick: int = 0, current_yield: Dict = None):
        if current_yield is None: current_yield = {}
        yield_str = ", ".join([f"[{m.name}]: {v}" for m, v in current_yield.items()])
        print("\n" * 2 + f"=== 🗺️ 多级自动化蓝图 [Tick {tick:03d}] | 产出: {yield_str} ===")
        dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}
        for y in range(env.height):
            row = f"{y:02d} "
            for x in range(env.width):
                cell = env._get_cell(x, y)
                if cell is None:
                    row += " . "
                elif hasattr(cell, 'size'):
                    row += "[B]"
                elif isinstance(cell, TransportComponent):
                    item = getattr(cell, 'current_item', None)
                    symbol = "S" if "Splitter" in type(cell).__name__ or "Router" in type(
                        cell).__name__ else dir_symbols.get(cell.direction, "*")
                    row += f"{symbol}{int(item[1]):02d}" if item else f" {symbol} "
                else:
                    row += "[?]"
            print(row)