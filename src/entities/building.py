from typing import Dict, Tuple, List, Optional
from entities.material import MaterialType


class Building:
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        self.component_id = component_id
        self.name = name
        self.size = size  # (width, height)

        # 1. 基础 IO 与生产配比属性 (静态数据，来自注册表)
        self.needs_input = False
        self.input_materials: Dict[MaterialType, float] = {}

        self.needs_output = False
        self.output_materials: Dict[MaterialType, float] = {}

        self.production_speed = 1.0
        self.consumes_power = False
        self.power_consumption = 0.0

        # ==========================================
        # [新增] 物流与库存控制属性
        # ==========================================
        self.max_inventory: float = 20.0  # 默认机器每种原料最大可容纳 20 个
        self.allowed_input_materials: List[MaterialType] = [] # 允许输入的原料种类白名单

        # 2. 端口特性声明 (静态能力)
        self.allows_omni_ports = True  # 允许四周任意边缘作为端口
        self.allows_direct_insertion = True  # 允许与其他建筑直接相邻传输（无需传送带）

        # 3. 动态连接状态 (当建筑被放置在地图上后，由 Environment 动态更新)
        # 记录当前作为【输入源】的相邻网格坐标 (x, y)
        self.active_input_ports: List[Tuple[int, int]] = []
        # 记录当前作为【输出目标】的相邻网格坐标 (x, y)
        self.active_output_ports: List[Tuple[int, int]] = []

    def reset_ports(self):
        """在重新规划布局时，清空当前端口连接状态"""
        self.active_input_ports.clear()
        self.active_output_ports.clear()