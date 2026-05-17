from enum import Enum, auto


class MaterialState(Enum):
    SOLID = auto()
    LIQUID = auto()


class MaterialType(Enum):
    # Mindustry-style sample materials.
    IRON_ORE = auto()
    IRON_PLATE = auto()
    IRON_INGOT = auto()

    SAND = auto()
    COPPER = auto()
    LEAD = auto()
    IRON = auto()
    THORIUM = auto()
    COAL = auto()
    OIL = auto()
    WATER = auto()
    SPORE_POD = auto()

    GRAPHITE = auto()
    SILICON = auto()
    PHASE_FABRIC = auto()
    SULFIDE = auto()
    PLASTIC = auto()
    CRYOFLUID = auto()

    EXPLOSIVES = auto()
    SUPER_ALLOY = auto()

    # Endfield-style agriculture chain.
    APPLE_SEED = auto()
    APPLE = auto()
    SANDLEAF_SEED = auto()
    SANDLEAF = auto()

    # Endfield-style mineral chain.
    ORIGINIUM = auto()
    AMETHYST = auto()
    BLUE_IRON = auto()

    ORIGINIUM_POWDER = auto()
    CRYSTAL_SHELL = auto()
    AMETHYST_FIBER = auto()
    BLUE_IRON_INGOT = auto()

    CRYSTAL_SHELL_POWDER = auto()
    AMETHYST_POWDER = auto()
    BLUE_IRON_POWDER = auto()
    SANDLEAF_POWDER = auto()
    DENSE_BLUE_IRON_POWDER = auto()
    DENSE_ORIGINIUM_POWDER = auto()
    AMETHYST_PART = auto()
    BLUE_IRON_PART = auto()
    STEEL_BLOCK = auto()
    STEEL_PART = auto()
    AMETHYST_BOTTLE = auto()
    BLUE_IRON_BOTTLE = auto()

    LOW_CAP_BATTERY = auto()
    MID_CAP_BATTERY = auto()
    HIGH_CAP_BATTERY = auto()


class Material:
    def __init__(self, mat_type: MaterialType, state: MaterialState):
        self.type = mat_type
        self.state = state
