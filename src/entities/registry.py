import copy
from entities.material import MaterialType, MaterialState
from entities.building import Building
from entities.transport import Belt, Bridge, LogicRouter, Sorter, OverflowGate


# 建立一个全局的字典作为“建筑图鉴”
TRANSPORT_CATALOG = {}
BUILDING_CATALOG = {}

# --- 传输类 ---

# --- 1. 注册传送带系列 ---
# 普通传送带: 接受侧面输入，不侧漏
TRANSPORT_CATALOG[101] = Belt(
    component_id=101, name="基础传送带", allowed_state=MaterialState.SOLID,
    speed=3.0, max_capacity=3, accepts_side_input=True, allows_side_output=True
)

# 装甲传送带: 拒绝侧面输入
TRANSPORT_CATALOG[102] = Belt(
    component_id=102, name="装甲传送带", allowed_state=MaterialState.SOLID,
    speed=5.0, max_capacity=5, accepts_side_input=False, allows_side_output=False
)

TRANSPORT_CATALOG[103] = Belt(
    component_id=103, name="液体管道", allowed_state=MaterialState.LIQUID,
    speed=5.0, max_capacity=5, accepts_side_input=True, allows_side_output=False
)

# --- 2. 注册桥接器系列 ---
# 物品传输桥
TRANSPORT_CATALOG[104] = Bridge(
    component_id=104, name="物品传输桥", allowed_state=MaterialState.SOLID,
    min_len=1, max_len=3
)

# 液体管道桥 (复用 Bridge 类，但限定为 LIQUID)
TRANSPORT_CATALOG[105] = Bridge(
    component_id=105, name="液体管道桥", allowed_state=MaterialState.LIQUID,
    min_len=1, max_len=3
)

# --- 3. 注册逻辑路由器件 ---
TRANSPORT_CATALOG[110] = LogicRouter(110, "分配器")

TRANSPORT_CATALOG[111] = Sorter(111, "分类器", inverted=False)
TRANSPORT_CATALOG[112] = Sorter(112, "反向分类器", inverted=True)

TRANSPORT_CATALOG[113] = OverflowGate(113, "溢流门", inverted=False)
TRANSPORT_CATALOG[114] = OverflowGate(114, "反向溢流门", inverted=True)

# --- 建筑类 ---

# --- 1. 注册熔炉 (ID: 201) ---
furnace = Building(component_id=201, size=(3, 3), name="石炉 (Stone Furnace)")
furnace.needs_input = True
furnace.input_materials = {MaterialType.IRON_ORE: 2.0}
furnace.needs_output = True
furnace.output_materials = {MaterialType.IRON_PLATE: 1.0}
furnace.consumes_power = True
furnace.power_consumption = 90.0
furnace.allowed_input_materials = [MaterialType.IRON_ORE]

BUILDING_CATALOG[201] = furnace

# --- 3. 注册种植机 (ID: 203) ---
planter = Building(component_id=203, size=(4, 4), name="种植机 (Planter)")
planter.needs_input = True
# 每 tick 消耗 1 份苹果种子
planter.input_materials = {MaterialType.APPLE_SEED: 1.0}
planter.needs_output = True
# 每 tick 产出 1 份苹果
planter.output_materials = {MaterialType.APPLE: 1.0}
planter.consumes_power = True
planter.power_consumption = 40.0
# 设置最大库存，防止上游种子无限堆积
planter.max_inventory = 20.0
planter.allowed_input_materials = [MaterialType.APPLE_SEED]
# 不允许建筑间直接传输
planter.allows_direct_insertion = False

BUILDING_CATALOG[203] = planter

# --- 4. 注册采种机 (ID: 204) ---
seed_extractor = Building(component_id=204, size=(4, 4), name="采种机 (Seed Extractor)")
seed_extractor.needs_input = True
# 每 tick 消耗 1 份苹果
seed_extractor.input_materials = {MaterialType.APPLE: 1.0}
seed_extractor.needs_output = True
# 每 tick 产出 2 份苹果种子
seed_extractor.output_materials = {MaterialType.APPLE_SEED: 2.0}
seed_extractor.consumes_power = True
seed_extractor.power_consumption = 60.0
# 设置最大库存
seed_extractor.max_inventory = 20.0
seed_extractor.allowed_input_materials = [MaterialType.APPLE]
# 不允许建筑间直接传输
seed_extractor.allows_direct_insertion = False

BUILDING_CATALOG[204] = seed_extractor


def get_transport_instance(component_id: int):
    """工厂方法：获取运输组件副本"""
    if component_id not in TRANSPORT_CATALOG:
        raise ValueError(f"未知的运输组件编号: {component_id}")
    return copy.deepcopy(TRANSPORT_CATALOG[component_id])

def get_building_instance(component_id: int) -> Building:
    """
    工厂方法：Agent 每次在地图上放置建筑时，调用这个方法获取一个【全新的副本】，
    防止多个同类建筑共享同一个内存地址。
    """
    if component_id not in BUILDING_CATALOG:
        raise ValueError(f"未知的建筑组件编号: {component_id}")

    # 必须使用深拷贝 (deepcopy)，这样你在地图上放 10 个熔炉，它们的独立状态才不会互相干扰
    return copy.deepcopy(BUILDING_CATALOG[component_id])