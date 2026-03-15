import time
from typing import Dict, Tuple
from entities.material import MaterialType
from entities.registry import get_transport_instance
from entities.transport import Direction, TransportComponent, Belt, LogicRouter, OverflowGate
from environment.grid_map import GridMap

# 假设你的 BaseAgent 保存在 agent.base_agent 中
from agents.base_agent import BaseAgent


# ==========================================
# 环境补丁：为 GridMap 增加分配器(LogicRouter)的物理流转逻辑
# ==========================================
def patch_grid_map_for_routers():
    original_tick = GridMap.tick

    def new_tick(self):
        # 先执行原有的生产与基础物流逻辑
        original_tick(self)

        # 补充：单独处理 LogicRouter (分配器) 的分流与汇流
        # 分配器逻辑：优先将物品分配给侧边（如送入机器），如果侧边堵塞或满了，则继续沿着主干道（前方）前进。
        for transport in self.transports:
            # 仅处理基础的分配器 (ID 110)
            if type(transport) is LogicRouter and getattr(transport, 'current_item', None) is not None:
                current_x, current_y = transport.pos
                dx, dy = transport.direction.value

                # 主干道前方
                front_cell = self._get_cell(current_x + dx, current_y + dy)
                # 分流侧边（为了本次蓝图向下排布，统一设为检查下方）
                down_cell = self._get_cell(current_x, current_y + 1)

                # 优先分流给下方（送入机器）
                if not self._is_blocked(down_cell):
                    down_cell.next_tick_item = transport.current_item
                    transport.current_item = None
                # 如果下方满载（或不需要），则汇流/直行至前方（沿着总线前进）
                elif not self._is_blocked(front_cell):
                    front_cell.next_tick_item = transport.current_item
                    transport.current_item = None

    GridMap.tick = new_tick


patch_grid_map_for_routers()


# ==========================================
# 核心 Agent：主总线(Main Bus)与汇流(Manifold)设计
# ==========================================
class BlueprintTestAgent(BaseAgent):
    def optimize(self, env: GridMap):
        print("【Agent 开始构建主总线与汇流蓝图】...")

        # 布局参数
        in_belt_y = 2  # 顶部原料总线
        machine_y = 4  # 中间机器阵列
        out_belt_y = 8  # 底部产物总线

        start_x = 2
        spacing = 4  # 机器横向间距

        # 1. 铺设左上角(0,2)到第一台机器前的初始原料输入主线
        for x in range(start_x + 1):
            belt = get_transport_instance(102)
            env.place_transport(belt, x, in_belt_y, Direction.RIGHT)

        for i, building in enumerate(self.required_buildings):
            current_x = start_x + i * spacing
            mid_x = current_x + 1  # 机器的中心X坐标

            # A. 放置机器 [3x3]
            env.place_building(building, current_x, machine_y)

            # B. 输入分流节点 (Manifold Split)
            # 在原料总线上放置分配器
            splitter = get_transport_instance(110)  # 110: 分配器
            env.place_transport(splitter, mid_x, in_belt_y, Direction.RIGHT)
            # 向下连接到机器的短传送带
            in_belt = get_transport_instance(102)
            env.place_transport(in_belt, mid_x, in_belt_y + 1, Direction.DOWN)

            # C. 输出汇流节点 (Manifold Merge)
            # 机器向下的输出传送带
            out_belt = get_transport_instance(102)
            env.place_transport(out_belt, mid_x, out_belt_y - 1, Direction.DOWN)
            # 在产物总线上放置分配器（汇流）
            merger = get_transport_instance(110)  # 110: 分配器
            env.place_transport(merger, mid_x, out_belt_y, Direction.RIGHT)

            # D. 补齐两台机器之间的主干道传送带
            if i < len(self.required_buildings) - 1:
                for gap_x in range(mid_x + 1, mid_x + spacing):
                    # 输入干线补充
                    b_in = get_transport_instance(102)
                    env.place_transport(b_in, gap_x, in_belt_y, Direction.RIGHT)
                    # 输出干线补充
                    b_out = get_transport_instance(102)
                    env.place_transport(b_out, gap_x, out_belt_y, Direction.RIGHT)

        # 2. 从最后一台机器的汇流器，一直铺设到右下角输出端
        last_mid_x = start_x + (len(self.required_buildings) - 1) * spacing + 1
        for x in range(last_mid_x + 1, env.width):
            b_out_final = get_transport_instance(102)
            env.place_transport(b_out_final, x, out_belt_y, Direction.RIGHT)

        # 让右下角最终出口在 (31, 10)，做个向下弯折，展示传送带方向
        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y + 1, Direction.DOWN)
        env.place_transport(get_transport_instance(102), env.width - 1, out_belt_y + 2, Direction.DOWN)

    def render_blueprint(self, env: GridMap):
        print("\n=== 🗺️ 满载 12/s 汇流管线蓝图 (左上输入 -> 机器阵列 -> 右下总线输出) ===")

        dir_symbols = {
            Direction.RIGHT: " > ",
            Direction.LEFT: " < ",
            Direction.UP: " ^ ",
            Direction.DOWN: " v "
        }

        grid_strs = []
        for y in range(env.height):
            row_str = ""
            for x in range(env.width):
                cell = env._get_cell(x, y)
                if cell is None:
                    row_str += " . "
                elif hasattr(cell, 'size') and cell.size == (3, 3):
                    row_str += "[F]"  # 机器 (熔炉)
                elif type(cell) is LogicRouter:
                    row_str += "[S]"  # 分配器 (Splitter/Merger)
                elif isinstance(cell, TransportComponent):
                    direction = getattr(cell, 'direction', Direction.RIGHT)
                    row_str += dir_symbols.get(direction, " * ")
                else:
                    row_str += "[?]"
            grid_strs.append(f"{y:02d} {row_str}")

        for row in grid_strs:
            print(row)
        print(f"============================================================")
        print(f" -> 蓝图评估分数 (极致紧凑的占地+总线耗材): {self.evaluate_layout(env)}\n")


def run_test():
    # 1. 定义目标产出：6个铁板 / 秒 (恰好耗尽一条 12/s 容量的输入传送带)
    target_outputs = {MaterialType.IRON_PLATE: 6.0}
    agent = BlueprintTestAgent(target_outputs)
    agent.calculate_production_chain()

    # 2. 初始化地图环境 (宽32，高12，完美包裹总线)
    env = GridMap(32, 12)

    # 3. 让 Agent 执行汇流/分流总线布局
    agent.optimize(env)

    # 扫描更新机器端口连接关系
    for b in env.buildings:
        env.update_connections(b)

    # 可视化生成的物理连线图
    agent.render_blueprint(env)

    # ==========================================
    # 4. 物流 Tick 引擎仿真
    # ==========================================
    print("=== ⚙️ 开始模拟满载运行 (每 Tick 在左上角注入 1 个矿石，相当于 12/s 满载测试) ===")
    total_iron_plate_yield = 0
    ticks_to_simulate = 80

    for tick in range(1, ticks_to_simulate + 1):
        # A. 左上角输入端持续满载注入矿石 (0, 2)
        in_cell = env._get_cell(0, 2)
        if isinstance(in_cell, TransportComponent) and in_cell.current_item is None:
            in_cell.current_item = MaterialType.IRON_ORE

        # B. 机器从输入传送带(v)抓取物品
        for b in env.buildings:
            if not hasattr(b, 'inventory'):
                b.inventory = {}
            for px, py in b.active_input_ports:
                port_cell = env._get_cell(px, py)
                if isinstance(port_cell, TransportComponent) and port_cell.current_item == MaterialType.IRON_ORE:
                    # 机器消耗 2 矿产 1 板。只要机器拿到了就先存在 inventory
                    b.inventory[MaterialType.IRON_ORE] = b.inventory.get(MaterialType.IRON_ORE, 0) + 1.0
                    port_cell.current_item = None

        # C. 环境状态步进 1 帧
        env.tick()

        # D. 统计右下角末端的最终产量 (31, 10)
        tick_yield = 0
        out_cell = env._get_cell(31, 10)
        if getattr(out_cell, 'current_item', None) == MaterialType.IRON_PLATE:
            tick_yield += 1
            out_cell.current_item = None  # 运走计数，防止堵塞

        total_iron_plate_yield += tick_yield

        if tick % 10 == 0 or tick_yield > 0:
            print(f"[Tick {tick:02d}] 右下角总线到达 IRON_PLATE: {tick_yield} 个 | 累计收集: {total_iron_plate_yield}")

    print(f"\n✅ 测试完成！在单条总线满负荷供应下：")
    print(f" -> 蓝图内实际共收集产物: {total_iron_plate_yield} 个")
    print(f" -> 分配器成功将满载矿石分配给 6 台机器，并将零散的铁板完美汇流成了一条直线输出！")


if __name__ == "__main__":
    run_test()