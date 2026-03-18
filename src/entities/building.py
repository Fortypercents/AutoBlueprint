from enum import Enum, auto
from typing import Dict, Tuple, List, Optional
from entities.material import MaterialType
from entities.transport import Direction


class SystemType(Enum):
    SYSTEM_A = auto()
    SYSTEM_B = auto()


class Building:
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        self.component_id = component_id
        self.name = name
        self.size = size  # (width, height)

        self.system_type = SystemType.SYSTEM_A

        self.needs_input = False
        self.input_materials: Dict[MaterialType, float] = {}
        self.needs_output = False
        self.output_materials: Dict[MaterialType, float] = {}
        self.production_speed = 1.0
        self.consumes_power = False
        self.power_consumption = 0.0
        self.max_inventory: float = 20.0
        self.allowed_input_materials: List[MaterialType] = []

        self.allows_omni_ports = True
        self.allows_direct_insertion = True

        # 默认方向和出入面
        self.direction = Direction.UP
        self.input_side = Direction.UP
        self.output_side = Direction.DOWN

        self.active_input_ports: List[Tuple[int, int]] = []
        self.active_output_ports: List[Tuple[int, int]] = []

    def set_direction(self, direction: Direction):
        """核心机制1：旋转建筑，自动设定对立面为输入输出口"""
        self.direction = direction

        if not self.allows_omni_ports:
            # 假定旋转方向即为“输入口”的朝向，那么输出口必然在对面
            self.input_side = direction
            if direction == Direction.UP:
                self.output_side = Direction.DOWN
            elif direction == Direction.DOWN:
                self.output_side = Direction.UP
            elif direction == Direction.LEFT:
                self.output_side = Direction.RIGHT
            elif direction == Direction.RIGHT:
                self.output_side = Direction.LEFT

    def reset_ports(self):
        self.active_input_ports.clear()
        self.active_output_ports.clear()


class SystemABuilding(Building):
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        super().__init__(component_id, size, name)
        self.system_type = SystemType.SYSTEM_A
        self.allows_omni_ports = True
        self.allows_direct_insertion = True


class SystemBBuilding(Building):
    def __init__(self, component_id: int, size: Tuple[int, int], name: str = "Unknown"):
        super().__init__(component_id, size, name)
        self.system_type = SystemType.SYSTEM_B
        self.allows_omni_ports = False
        self.allows_direct_insertion = False