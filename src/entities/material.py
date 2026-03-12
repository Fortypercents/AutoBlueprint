from enum import Enum, auto

class MaterialState(Enum):
    SOLID = auto()
    LIQUID = auto()

class MaterialType(Enum):

    # ==========================================
    # 1. 原料 (Raw Materials)
    # ==========================================
    SAND = auto()  # 沙子
    COPPER = auto()  # 铜
    LEAD = auto()  # 铅
    IRON = auto()  # 铁
    THORIUM = auto()  # 钍
    COAL = auto()  # 煤炭
    OIL = auto()  # 石油 (液体)
    WATER = auto()  # 水 (液体)
    SPORE_POD = auto()  # 生物孢子

    # ==========================================
    # 2. 一级产物 (Tier 1 Products)
    # ==========================================
    GRAPHITE = auto()  # 石墨 (由煤炭压制)
    SILICON = auto()  # 硅 (由沙子+煤炭烧结)
    PHASE_FABRIC = auto()  # 相织布 (由钍+沙子合成的放射材料)
    SULFIDE = auto()  # 硫化物
    PLASTIC = auto()  # 塑料 (由石油+孢子/钛等合成)
    CRYOFLUID = auto()  # 冷冻液 (液体，通常需要水+钛/混合物)

    # ==========================================
    # 3. 二级产物 (Tier 2 Products)
    # ==========================================
    EXPLOSIVES = auto()  # 爆炸物 (由硫化物/孢子等混合)
    SUPER_ALLOY = auto()  # 超级合金 (由铜+铅+钛+硅等多种材料锻造)


class Material:
    def __init__(self, mat_type: MaterialType, state: MaterialState):
        self.type = mat_type
        self.state = state