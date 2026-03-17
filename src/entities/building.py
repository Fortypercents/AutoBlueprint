from enum import Enum, auto
from typing import Dict, Tuple, List, Optional
from entities.material import MaterialType
from entities.transport import Direction


# ==========================================
# [新增] 定义游戏内的物理体系
# ==========================================
class SystemType(Enum):
    SYSTEM_A = auto()  # 体系A (如异星工厂：全向输入输出，允许机器贴脸直传)
    SYSTEM_B = auto()  # 体系B (如戴森球/幸福工厂：固定出入口，必须用传送带/分拣器)


class Building:
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        self.component_id = component_id
        self.name = name
        self.size = size  # (width, height)

        # 默认归属体系A
        self.system_type = SystemType.SYSTEM_A

        # 1. 基础 IO 与生产配比属性
        self.needs_input = False
        self.input_materials: Dict[MaterialType, float] = {}
        self.needs_output = False
        self.output_materials: Dict[MaterialType, float] = {}
        self.production_speed = 1.0
        self.consumes_power = False
        self.power_consumption = 0.0
        self.max_inventory: float = 20.0
        self.allowed_input_materials: List[MaterialType] = []

        # 2. 端口特性声明 (将被子类覆盖)
        self.allows_omni_ports = True
        self.allows_direct_insertion = True
        self.input_side = Direction.UP
        self.output_side = Direction.DOWN

        # 3. 动态连接状态
        self.active_input_ports: List[Tuple[int, int]] = []
        self.active_output_ports: List[Tuple[int, int]] = []

    def reset_ports(self):
        self.active_input_ports.clear()
        self.active_output_ports.clear()


# ==========================================
# [新增] 派生类：体系 A 建筑 (全向、允许直连)
# ==========================================
class SystemABuilding(Building):
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        super().__init__(component_id, size, name)
        self.system_type = SystemType.SYSTEM_A
        self.allows_omni_ports = True
        self.allows_direct_insertion = True


# ==========================================
# [新增] 派生类：体系 B 建筑 (定向、禁止直连)
# ==========================================
class SystemBBuilding(Building):
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        super().__init__(component_id, size, name)
        self.system_type = SystemType.SYSTEM_B
        self.allows_omni_ports = False
        self.allows_direct_insertion = False
        # 统一规定体系 B 的输入在上方，输出在下方
        self.input_side = Direction.UP
        self.output_side = Direction.DOWN