from enum import Enum, auto

class MaterialState(Enum):
    SOLID = auto()
    LIQUID = auto()

class MaterialType(Enum):

    # MINDUSTRY
    # ==========================================
    # 0. Test
    # ==========================================
    IRON_ORE = auto()
    IRON_PLATE = auto()
    IRON_INGOT = auto()

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

    # ENDFIELD
    # ==========================================
    # 1. 农业与生物链 (Agriculture)
    # ==========================================
    APPLE_SEED = auto()  # 苹果种子
    APPLE = auto()  # 苹果
    SANDLEAF_SEED = auto()  # 砂叶种子
    SANDLEAF = auto()  # 砂叶

    # ==========================================
    # 2. 矿物生产链
    # ==========================================
    # [矿物原料]
    ORIGINIUM = auto()
    AMETHYST = auto()  # 紫晶
    BLUE_IRON = auto()  # 蓝铁

    # [一级产物]
    ORIGINIUM_POWDER = auto()  # 源石粉
    CRYSTAL_SHELL = auto()  # 晶体外壳
    AMETHYST_FIBER = auto()  # 紫晶纤维
    BLUE_IRON_INGOT = auto()  # 蓝铁块

    # [二级产物]
    CRYSTAL_SHELL_POWDER = auto()  # 晶体外壳粉末
    AMETHYST_POWDER = auto()  # 紫晶粉
    BLUE_IRON_POWDER = auto()  # 蓝铁粉
    SANDLEAF_POWDER = auto()  # 砂叶粉末
    DENSE_BLUE_IRON_POWDER = auto()  # 致密蓝铁粉末
    DENSE_ORIGINIUM_POWDER = auto()  # 致密源石粉末
    AMETHYST_PART = auto()  # 紫晶零件
    BLUE_IRON_PART = auto()  # 蓝铁零件
    STEEL_BLOCK = auto()  # 钢块
    STEEL_PART = auto()  # 钢制零件
    AMETHYST_BOTTLE = auto()  # 紫晶瓶
    BLUE_IRON_BOTTLE = auto()  # 蓝铁瓶

    # [三级产物]
    LOW_CAP_BATTERY = auto()  # 低容谷地电池
    MID_CAP_BATTERY = auto()  # 中容谷地电池
    HIGH_CAP_BATTERY = auto()  # 高容谷地电池


class Material:
    def __init__(self, mat_type: MaterialType, state: MaterialState):
        self.type = mat_type
        self.state = state
