import copy
from entities.building import SystemABuilding, SystemBBuilding
from entities.material import MaterialType

# 引入我们刚刚重写的所有 SystemA 和 SystemB 运输元件
from entities.transport import (
    SystemABelt, SystemAPipe,
    SystemALogicRouter, SystemAPipeRouter,
    SystemAOverflowGate, SystemAPipeOverflowGate,
    SystemABridge, SystemAPipeBridge,
    SystemACrosser, SystemAPipeCrosser,
    SystemBBelt, SystemBPipe,
    SystemBSplitter, SystemBPipeSplitter,
    SystemBMerger, SystemBPipeMerger,
    SystemBBeltAccess, SystemBPipeAccess,
    SystemBCrosser, SystemBPipeCrosser
)

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

press = SystemABuilding(component_id=202, size=(3, 3), name="压制机")
press.needs_input = True
press.input_materials = {MaterialType.IRON_PLATE: 2.0}
press.needs_output = True
press.output_materials = {MaterialType.IRON_INGOT: 1.0}
press.max_inventory = 10.0
press.allowed_input_materials = [MaterialType.IRON_PLATE]
BUILDING_CATALOG[202] = press


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

# ---------------- 1. 精炼炉 (3x3) ----------------
# 源石 -> 晶体外壳
refinery_ori = SystemBBuilding(component_id=511, size=(3, 3), name="精炼炉(源石)")
refinery_ori.needs_input, refinery_ori.needs_output = True, True
refinery_ori.input_materials = {MaterialType.ORIGINIUM: 1.0}
refinery_ori.output_materials = {MaterialType.CRYSTAL_SHELL: 1.0}
refinery_ori.allowed_input_materials = [MaterialType.ORIGINIUM]
refinery_ori.max_inventory = 50.0
BUILDING_CATALOG[511] = refinery_ori

# 紫晶 -> 紫晶纤维
refinery_ame = SystemBBuilding(component_id=512, size=(3, 3), name="精炼炉(紫晶)")
refinery_ame.needs_input, refinery_ame.needs_output = True, True
refinery_ame.input_materials = {MaterialType.AMETHYST: 1.0}
refinery_ame.output_materials = {MaterialType.AMETHYST_FIBER: 1.0}
refinery_ame.allowed_input_materials = [MaterialType.AMETHYST]
refinery_ame.max_inventory = 50.0
BUILDING_CATALOG[512] = refinery_ame

# 蓝铁 -> 蓝铁块
refinery_iron = SystemBBuilding(component_id=513, size=(3, 3), name="精炼炉(蓝铁)")
refinery_iron.needs_input, refinery_iron.needs_output = True, True
refinery_iron.input_materials = {MaterialType.BLUE_IRON: 1.0}
refinery_iron.output_materials = {MaterialType.BLUE_IRON_INGOT: 1.0}
refinery_iron.allowed_input_materials = [MaterialType.BLUE_IRON]
refinery_iron.max_inventory = 50.0
BUILDING_CATALOG[513] = refinery_iron

# ---------------- 2. 粉碎机 (3x3) ----------------
# 晶体外壳 -> 外壳粉末
crusher_shell = SystemBBuilding(component_id=521, size=(3, 3), name="粉碎机(外壳)")
crusher_shell.needs_input, crusher_shell.needs_output = True, True
crusher_shell.input_materials = {MaterialType.CRYSTAL_SHELL: 1.0}
crusher_shell.output_materials = {MaterialType.CRYSTAL_SHELL_POWDER: 1.0}
crusher_shell.allowed_input_materials = [MaterialType.CRYSTAL_SHELL]
crusher_shell.max_inventory = 50.0
BUILDING_CATALOG[521] = crusher_shell

# 紫晶纤维 -> 紫晶粉
crusher_ame = SystemBBuilding(component_id=522, size=(3, 3), name="粉碎机(紫晶)")
crusher_ame.needs_input, crusher_ame.needs_output = True, True
crusher_ame.input_materials = {MaterialType.AMETHYST_FIBER: 1.0}
crusher_ame.output_materials = {MaterialType.AMETHYST_POWDER: 1.0}
crusher_ame.allowed_input_materials = [MaterialType.AMETHYST_FIBER]
crusher_ame.max_inventory = 50.0
BUILDING_CATALOG[522] = crusher_ame

# 蓝铁块 -> 蓝铁粉
crusher_iron = SystemBBuilding(component_id=523, size=(3, 3), name="粉碎机(蓝铁)")
crusher_iron.needs_input, crusher_iron.needs_output = True, True
crusher_iron.input_materials = {MaterialType.BLUE_IRON_INGOT: 1.0}
crusher_iron.output_materials = {MaterialType.BLUE_IRON_POWDER: 1.0}
crusher_iron.allowed_input_materials = [MaterialType.BLUE_IRON_INGOT]
crusher_iron.max_inventory = 50.0
BUILDING_CATALOG[523] = crusher_iron

# 源石 -> 源石粉 (直通配方)
crusher_ori = SystemBBuilding(component_id=524, size=(3, 3), name="粉碎机(源石)")
crusher_ori.needs_input, crusher_ori.needs_output = True, True
crusher_ori.input_materials = {MaterialType.ORIGINIUM: 1.0}
crusher_ori.output_materials = {MaterialType.ORIGINIUM_POWDER: 1.0}
crusher_ori.allowed_input_materials = [MaterialType.ORIGINIUM]
crusher_ori.max_inventory = 50.0
BUILDING_CATALOG[524] = crusher_ori

# ---------------- 3. 配件机 (3x3) ----------------
# 紫晶纤维 -> 紫晶零件
part_ame = SystemBBuilding(component_id=531, size=(3, 3), name="配件机(紫晶)")
part_ame.needs_input, part_ame.needs_output = True, True
part_ame.input_materials = {MaterialType.AMETHYST_FIBER: 1.0}
part_ame.output_materials = {MaterialType.AMETHYST_PART: 1.0}
part_ame.allowed_input_materials = [MaterialType.AMETHYST_FIBER]
part_ame.max_inventory = 50.0
BUILDING_CATALOG[531] = part_ame

# 蓝铁块 -> 蓝铁零件
part_iron = SystemBBuilding(component_id=532, size=(3, 3), name="配件机(蓝铁)")
part_iron.needs_input, part_iron.needs_output = True, True
part_iron.input_materials = {MaterialType.BLUE_IRON_INGOT: 1.0}
part_iron.output_materials = {MaterialType.BLUE_IRON_PART: 1.0}
part_iron.allowed_input_materials = [MaterialType.BLUE_IRON_INGOT]
part_iron.max_inventory = 50.0
BUILDING_CATALOG[532] = part_iron

# ---------------- 4. 压制机 (3x3) ----------------
# 紫晶纤维 -> 紫晶瓶
press_ame = SystemBBuilding(component_id=541, size=(3, 3), name="压制机(紫晶瓶)")
press_ame.needs_input, press_ame.needs_output = True, True
press_ame.input_materials = {MaterialType.AMETHYST_FIBER: 2.0}
press_ame.output_materials = {MaterialType.AMETHYST_BOTTLE: 1.0}
press_ame.allowed_input_materials = [MaterialType.AMETHYST_FIBER]
press_ame.max_inventory = 50.0
BUILDING_CATALOG[541] = press_ame

# 蓝铁块 -> 蓝铁瓶
press_iron = SystemBBuilding(component_id=542, size=(3, 3), name="压制机(蓝铁瓶)")
press_iron.needs_input, press_iron.needs_output = True, True
press_iron.input_materials = {MaterialType.BLUE_IRON_INGOT: 2.0}
press_iron.output_materials = {MaterialType.BLUE_IRON_BOTTLE: 1.0}
press_iron.allowed_input_materials = [MaterialType.BLUE_IRON_INGOT]
press_iron.max_inventory = 50.0
BUILDING_CATALOG[542] = press_iron

# ---------------- 5. 封装机 (5x3) 多输入多输出 ----------------
# 5紫晶零件 + 10源石粉末 = 低容谷地电池
pack_low = SystemBBuilding(component_id=551, size=(5, 3), name="封装机(低容)")
pack_low.needs_input, pack_low.needs_output = True, True
pack_low.input_materials = {MaterialType.AMETHYST_PART: 1.0, MaterialType.ORIGINIUM_POWDER: 2.0}
pack_low.output_materials = {MaterialType.LOW_CAP_BATTERY: 1.0}
pack_low.allowed_input_materials = [MaterialType.AMETHYST_PART, MaterialType.ORIGINIUM_POWDER]
pack_low.max_inventory = 200.0
BUILDING_CATALOG[551] = pack_low

# 10蓝铁零件 + 15源石粉末 = 中容谷地电池
pack_mid = SystemBBuilding(component_id=552, size=(5, 3), name="封装机(中容)")
pack_mid.needs_input, pack_mid.needs_output = True, True
pack_mid.input_materials = {MaterialType.BLUE_IRON_PART: 2.0, MaterialType.ORIGINIUM_POWDER: 3.0}
pack_mid.output_materials = {MaterialType.MID_CAP_BATTERY: 1.0}
pack_mid.allowed_input_materials = [MaterialType.BLUE_IRON_PART, MaterialType.ORIGINIUM_POWDER]
pack_mid.max_inventory = 200.0
BUILDING_CATALOG[552] = pack_mid

# ---------------- 6. 新增高容电池生产链 ----------------
# 砂叶种子 -> 砂叶
planter_sandleaf = SystemBBuilding(component_id=403, size=(4, 4), name="种植机(砂叶)")
planter_sandleaf.needs_input, planter_sandleaf.needs_output = True, True
planter_sandleaf.input_materials = {MaterialType.SANDLEAF_SEED: 1.0}
planter_sandleaf.output_materials = {MaterialType.SANDLEAF: 1.0}
planter_sandleaf.allowed_input_materials = [MaterialType.SANDLEAF_SEED]
planter_sandleaf.max_inventory = 20.0
BUILDING_CATALOG[403] = planter_sandleaf

# 砂叶 -> 砂叶种子
seed_extractor_sandleaf = SystemBBuilding(component_id=404, size=(4, 4), name="采种机(砂叶)")
seed_extractor_sandleaf.needs_input, seed_extractor_sandleaf.needs_output = True, True
seed_extractor_sandleaf.input_materials = {MaterialType.SANDLEAF: 1.0}
seed_extractor_sandleaf.output_materials = {MaterialType.SANDLEAF_SEED: 2.0}
seed_extractor_sandleaf.allowed_input_materials = [MaterialType.SANDLEAF]
seed_extractor_sandleaf.max_inventory = 20.0
BUILDING_CATALOG[404] = seed_extractor_sandleaf

# 砂叶 -> 砂叶粉末
crusher_sandleaf = SystemBBuilding(component_id=525, size=(3, 3), name="粉碎机(砂叶)")
crusher_sandleaf.needs_input, crusher_sandleaf.needs_output = True, True
crusher_sandleaf.input_materials = {MaterialType.SANDLEAF: 1.0}
crusher_sandleaf.output_materials = {MaterialType.SANDLEAF_POWDER: 2.0}
crusher_sandleaf.allowed_input_materials = [MaterialType.SANDLEAF]
crusher_sandleaf.max_inventory = 50.0
BUILDING_CATALOG[525] = crusher_sandleaf

# 蓝铁粉末 + 砂叶粉末 -> 致密蓝铁粉末
grinder_dense_iron = SystemBBuilding(component_id=561, size=(6, 4), name="研磨机(致密蓝铁)")
grinder_dense_iron.needs_input, grinder_dense_iron.needs_output = True, True
grinder_dense_iron.input_materials = {MaterialType.BLUE_IRON_POWDER: 1.2, MaterialType.SANDLEAF_POWDER: 1.0}
grinder_dense_iron.output_materials = {MaterialType.DENSE_BLUE_IRON_POWDER: 1.0}
grinder_dense_iron.allowed_input_materials = [MaterialType.BLUE_IRON_POWDER, MaterialType.SANDLEAF_POWDER]
grinder_dense_iron.max_inventory = 100.0
BUILDING_CATALOG[561] = grinder_dense_iron

# 源石粉末 + 砂叶粉末 -> 致密源石粉末
grinder_dense_originium = SystemBBuilding(component_id=562, size=(6, 4), name="研磨机(致密源石)")
grinder_dense_originium.needs_input, grinder_dense_originium.needs_output = True, True
grinder_dense_originium.input_materials = {MaterialType.ORIGINIUM_POWDER: 2.2, MaterialType.SANDLEAF_POWDER: 1.0}
grinder_dense_originium.output_materials = {MaterialType.DENSE_ORIGINIUM_POWDER: 1.0}
grinder_dense_originium.allowed_input_materials = [MaterialType.ORIGINIUM_POWDER, MaterialType.SANDLEAF_POWDER]
grinder_dense_originium.max_inventory = 100.0
BUILDING_CATALOG[562] = grinder_dense_originium

# 致密蓝铁粉末 -> 钢块
refinery_steel = SystemBBuilding(component_id=514, size=(3, 3), name="精炼炉(钢块)")
refinery_steel.needs_input, refinery_steel.needs_output = True, True
refinery_steel.input_materials = {MaterialType.DENSE_BLUE_IRON_POWDER: 1.0}
refinery_steel.output_materials = {MaterialType.STEEL_BLOCK: 1.0}
refinery_steel.allowed_input_materials = [MaterialType.DENSE_BLUE_IRON_POWDER]
refinery_steel.max_inventory = 50.0
BUILDING_CATALOG[514] = refinery_steel

# 钢块 -> 钢制零件
part_steel = SystemBBuilding(component_id=533, size=(3, 3), name="配件机(钢制零件)")
part_steel.needs_input, part_steel.needs_output = True, True
part_steel.input_materials = {MaterialType.STEEL_BLOCK: 1.0}
part_steel.output_materials = {MaterialType.STEEL_PART: 1.0}
part_steel.allowed_input_materials = [MaterialType.STEEL_BLOCK]
part_steel.max_inventory = 50.0
BUILDING_CATALOG[533] = part_steel

# 钢制零件 + 致密源石粉末 -> 高容谷地电池
pack_high = SystemBBuilding(component_id=553, size=(5, 3), name="封装机(高容)")
pack_high.needs_input, pack_high.needs_output = True, True
pack_high.input_materials = {MaterialType.STEEL_PART: 2.0, MaterialType.DENSE_ORIGINIUM_POWDER: 3.0}
pack_high.output_materials = {MaterialType.HIGH_CAP_BATTERY: 1.0}
pack_high.allowed_input_materials = [MaterialType.STEEL_PART, MaterialType.DENSE_ORIGINIUM_POWDER]
pack_high.max_inventory = 200.0
BUILDING_CATALOG[553] = pack_high


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
        router = SystemALogicRouter(110, "分配器(A)")
        router.max_capacity = 12.0
        return router
    if component_id == 111:
        overflowgate = SystemAOverflowGate(111, "溢流门(A)")
        overflowgate.max_capacity = 12.0
        return overflowgate
    if component_id == 112:
        bridge = SystemABridge(112, "基础传送桥(A)", min_length=1, max_length=3)
        bridge.max_capacity = 12.0
        return bridge
    if component_id == 113:
        crosser = SystemACrosser(113, "交叉器(A)")
        crosser.max_capacity = 12.0
        return crosser

    # ---------------- 体系 A (液体) ----------------
    if component_id == 151:
        pipe = SystemAPipe(151, "基础管道(A)")
        pipe.max_capacity = 12.0
        return pipe
    if component_id == 160:
        router = SystemAPipeRouter(160, "管道分配器(A)")
        router.max_capacity = 12.0
        return router
    if component_id == 161:
        overflowgate = SystemAPipeOverflowGate(161, "管道溢流门(A)")
        overflowgate.max_capacity = 12.0
        return overflowgate
    if component_id == 162:
        bridge = SystemAPipeBridge(162, "基础管道桥(A)", min_length=1, max_length=3)
        bridge.max_capacity = 12.0
        return bridge
    if component_id == 163:
        crosser = SystemAPipeCrosser(163, "管道交叉器(A)")
        crosser.max_capacity = 12.0
        return crosser

    # ---------------- 体系 B (基础线缆) ----------------
    if component_id == 301:
        belt = SystemBBelt(301, "生物传送带(B)")
        belt.max_capacity = 1.0
        return belt
    if component_id == 302:
        pipe = SystemBPipe(302, "生物管道(B)")
        pipe.max_capacity = 1.0
        return pipe

    # ---------------- 体系 B (固体物流元件) ----------------
    if component_id == 311:
        splitter = SystemBSplitter(311, "传送分流器(B)")
        splitter.max_capacity = 1.0
        return splitter
    if component_id == 312:
        merger = SystemBMerger(312, "传送汇流器(B)")
        merger.max_capacity = 1.0
        return merger
    if component_id == 313:
        access = SystemBBeltAccess(313, "传送准入器(B)")
        access.max_capacity = 1.0
        return access
    if component_id == 314:
        crosser = SystemBCrosser(314, "交叉器(B)")
        crosser.max_capacity = 1.0
        return crosser

    # ---------------- 体系 B (液体物流元件) ----------------
    if component_id == 321:
        splitter = SystemBPipeSplitter(321, "管道分流器(B)")
        splitter.max_capacity = 1.0
        return splitter
    if component_id == 322:
        merger = SystemBPipeMerger(322, "管道汇流器(B)")
        merger.max_capacity = 1.0
        return merger
    if component_id == 323:
        access = SystemBPipeAccess(323, "管道准入器(B)")
        access.max_capacity = 1.0
        return access
    if component_id == 324:
        crosser = SystemBPipeCrosser(324, "管道交叉器(B)")
        crosser.max_capacity = 1.0
        return crosser

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
