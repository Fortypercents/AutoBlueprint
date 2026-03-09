from typing import Dict, Tuple
from entities.material import MaterialType


class Building:
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        # 基础属性
        self.component_id = component_id
        self.name = name
        self.size = size  # 例如 (3, 3) 代表 3x3 大小

        # IO 与生产配比属性
        self.needs_input = False
        self.input_materials: Dict[MaterialType, float] = {}  # {材料: 每秒消耗量}

        self.needs_output = False
        self.output_materials: Dict[MaterialType, float] = {}  # {材料: 每秒产出量}

        self.production_speed = 1.0  # 生产速度倍率

        # 电力属性
        self.consumes_power = False
        self.power_consumption = 0.0  # 耗电大小 (例如 kW)

        # 地块属性
        self.is_special_tile = False
        self.special_tile_type = None  # 预留扩展字段