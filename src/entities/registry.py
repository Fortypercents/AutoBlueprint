import copy
from entities.building import SystemABuilding, SystemBBuilding
from entities.material import MaterialType

# 引入我们刚刚重写的所有 SystemA 和 SystemB 运输元件
from entities.transport import *

BUILDING_CATALOG = {}

# ==========================================
# 体系 A 建筑注册 (经典体系：全向输入输出，允许直连)
# ==========================================
furnace = SystemABuilding(component_id=201, size=(3, 3), name="石炉")
furnace.needs_input = True
furnace.input_materials = {MaterialType.IRON_ORE: 2.0}
furnace.needs_output = True
furnace.output_materials = {MaterialType.IRON_PLATE: 1.0}
furnace.max_inventory = 10.0
furnace.allowed_input_materials = [MaterialType.IRON_ORE]
BUILDING_CATALOG[201] = furnace


# ==========================================
# 体系 B 建筑注册 (严格体系：定向出入、禁止直连)
# ==========================================
planter = SystemBBuilding(component_id=401, size=(4, 4), name="种植机")
planter.needs_input = True
planter.input_materials = {MaterialType.APPLE_SEED: 1.0}
planter.needs_output = True
planter.output_materials = {MaterialType.APPLE: 1.0}
planter.max_inventory = 20.0
planter.allowed_input_materials = [MaterialType.APPLE_SEED]
BUILDING_CATALOG[401] = planter

seed_extractor = SystemBBuilding(component_id=402, size=(4, 4), name="采种机")
seed_extractor.needs_input = True
seed_extractor.input_materials = {MaterialType.APPLE: 1.0}
seed_extractor.needs_output = True
seed_extractor.output_materials = {MaterialType.APPLE_SEED: 2.0}
seed_extractor.max_inventory = 20.0
seed_extractor.allowed_input_materials = [MaterialType.APPLE]
BUILDING_CATALOG[402] = seed_extractor


# ==========================================
# 运输组件实例工厂 (支持 SystemA 和 SystemB 固液全系)
# ==========================================
def get_transport_instance(component_id: int):
    # ---------------- 体系 A (固体) ----------------
    if component_id == 101:
        belt = SystemABelt(101, "基础传送带(A)")
        belt.max_capacity = 3.0
        return belt
    if component_id == 102:
        belt = SystemABelt(102, "装甲传送带(A)")
        belt.max_capacity = 12.0
        return belt
    if component_id == 110:
        return SystemALogicRouter(110, "分配器(A)")
    if component_id == 111:
        return SystemAOverflowGate(111, "溢流门(A)")
    if component_id == 112:
        return SystemABridge(112, "基础传送桥(A)", min_length=1, max_length=3)

    # ---------------- 体系 A (液体) ----------------
    if component_id == 151:
        pipe = SystemAPipe(151, "基础管道(A)")
        pipe.max_capacity = 12.0
        return pipe
    if component_id == 160:
        return SystemAPipeRouter(160, "管道分配器(A)")
    if component_id == 161:
        return SystemAPipeOverflowGate(161, "管道溢流门(A)")
    if component_id == 162:
        return SystemAPipeBridge(162, "基础管道桥(A)", min_length=1, max_length=3)

    # ---------------- 体系 B (基础线缆) ----------------
    if component_id == 301:
        return SystemBBelt(301, "生物传送带(B)")
    if component_id == 302:
        return SystemBPipe(302, "生物管道(B)")

    # ---------------- 体系 B (固体物流元件) ----------------
    if component_id == 311:
        return SystemBSplitter(311, "传送分流器(B)")
    if component_id == 312:
        return SystemBMerger(312, "传送汇流器(B)")
    if component_id == 313:
        return SystemBBeltAccess(313, "传送准入器(B)")

    # ---------------- 体系 B (液体物流元件) ----------------
    if component_id == 321:
        return SystemBPipeSplitter(321, "管道分流器(B)")
    if component_id == 322:
        return SystemBPipeMerger(322, "管道汇流器(B)")
    if component_id == 323:
        return SystemBPipeAccess(323, "管道准入器(B)")

    raise ValueError(f"未知的运输组件 ID: {component_id}")


# ==========================================
# 建筑组件实例工厂
# ==========================================
def get_building_instance(component_id: int) -> SystemABuilding:
    """
    工厂方法：Agent 每次在地图上放置建筑时，调用这个方法获取一个【全新的副本】，
    防止多个同类建筑共享同一个内存地址。
    """
    if component_id not in BUILDING_CATALOG:
        raise ValueError(f"未知的建筑组件编号: {component_id}")

    # 必须使用深拷贝 (deepcopy)，确保每个建筑实体的库存、接口状态独立
    return copy.deepcopy(BUILDING_CATALOG[component_id])