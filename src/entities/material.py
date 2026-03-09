from enum import Enum, auto

class MaterialState(Enum):
    SOLID = auto()
    LIQUID = auto()

class MaterialType(Enum):
    IRON_ORE = auto()
    COPPER_ORE = auto()
    IRON_PLATE = auto()
    # 后续可继续添加十余种材料...

class Material:
    def __init__(self, mat_type: MaterialType, state: MaterialState):
        self.type = mat_type
        self.state = state