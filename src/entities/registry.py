import copy

from entities.building import SystemABuilding, SystemBBuilding
from entities.material import MaterialType
from entities.transport import (
    SystemABelt,
    SystemAPipe,
    SystemALogicRouter,
    SystemAPipeRouter,
    SystemAOverflowGate,
    SystemAPipeOverflowGate,
    SystemABridge,
    SystemAPipeBridge,
    SystemACrosser,
    SystemAPipeCrosser,
    SystemBBelt,
    SystemBPipe,
    SystemBSplitter,
    SystemBPipeSplitter,
    SystemBMerger,
    SystemBPipeMerger,
    SystemBBeltAccess,
    SystemBPipeAccess,
    SystemBCrosser,
    SystemBPipeCrosser,
)


BUILDING_CATALOG = {}


def _register(building):
    BUILDING_CATALOG[building.component_id] = building
    return building


# System A sample buildings.
furnace = _register(SystemABuilding(component_id=201, size=(3, 3), name="Furnace"))
furnace.needs_input = True
furnace.input_materials = {MaterialType.IRON_ORE: 2.0}
furnace.needs_output = True
furnace.output_materials = {MaterialType.IRON_PLATE: 1.0}
furnace.max_inventory = 10.0
furnace.allowed_input_materials = [MaterialType.IRON_ORE]

press = _register(SystemABuilding(component_id=202, size=(3, 3), name="Press"))
press.needs_input = True
press.input_materials = {MaterialType.IRON_PLATE: 2.0}
press.needs_output = True
press.output_materials = {MaterialType.IRON_INGOT: 1.0}
press.max_inventory = 10.0
press.allowed_input_materials = [MaterialType.IRON_PLATE]


# System B agriculture buildings.
planter = _register(SystemBBuilding(component_id=401, size=(4, 4), name="Planter apple"))
planter.needs_input, planter.needs_output = True, True
planter.input_materials = {MaterialType.APPLE_SEED: 1.0}
planter.output_materials = {MaterialType.APPLE: 1.0}
planter.max_inventory = 20.0
planter.allowed_input_materials = [MaterialType.APPLE_SEED]

seed_extractor = _register(SystemBBuilding(component_id=402, size=(4, 4), name="Seed extractor apple"))
seed_extractor.needs_input, seed_extractor.needs_output = True, True
seed_extractor.input_materials = {MaterialType.APPLE: 1.0}
seed_extractor.output_materials = {MaterialType.APPLE_SEED: 2.0}
seed_extractor.max_inventory = 20.0
seed_extractor.allowed_input_materials = [MaterialType.APPLE]

planter_sandleaf = _register(SystemBBuilding(component_id=403, size=(4, 4), name="Planter sandleaf"))
planter_sandleaf.needs_input, planter_sandleaf.needs_output = True, True
planter_sandleaf.input_materials = {MaterialType.SANDLEAF_SEED: 1.0}
planter_sandleaf.output_materials = {MaterialType.SANDLEAF: 1.0}
planter_sandleaf.allowed_input_materials = [MaterialType.SANDLEAF_SEED]
planter_sandleaf.max_inventory = 20.0

seed_extractor_sandleaf = _register(SystemBBuilding(component_id=404, size=(4, 4), name="Seed extractor sandleaf"))
seed_extractor_sandleaf.needs_input, seed_extractor_sandleaf.needs_output = True, True
seed_extractor_sandleaf.input_materials = {MaterialType.SANDLEAF: 1.0}
seed_extractor_sandleaf.output_materials = {MaterialType.SANDLEAF_SEED: 2.0}
seed_extractor_sandleaf.allowed_input_materials = [MaterialType.SANDLEAF]
seed_extractor_sandleaf.max_inventory = 20.0


# System B refinery recipes.
refinery_ori = _register(SystemBBuilding(component_id=511, size=(3, 3), name="Refinery originium"))
refinery_ori.needs_input, refinery_ori.needs_output = True, True
refinery_ori.input_materials = {MaterialType.ORIGINIUM: 1.0}
refinery_ori.output_materials = {MaterialType.CRYSTAL_SHELL: 1.0}
refinery_ori.allowed_input_materials = [MaterialType.ORIGINIUM]
refinery_ori.max_inventory = 50.0

refinery_ame = _register(SystemBBuilding(component_id=512, size=(3, 3), name="Refinery amethyst"))
refinery_ame.needs_input, refinery_ame.needs_output = True, True
refinery_ame.input_materials = {MaterialType.AMETHYST: 1.0}
refinery_ame.output_materials = {MaterialType.AMETHYST_FIBER: 1.0}
refinery_ame.allowed_input_materials = [MaterialType.AMETHYST]
refinery_ame.max_inventory = 50.0

refinery_iron = _register(SystemBBuilding(component_id=513, size=(3, 3), name="Refinery blue iron"))
refinery_iron.needs_input, refinery_iron.needs_output = True, True
refinery_iron.input_materials = {MaterialType.BLUE_IRON: 1.0}
refinery_iron.output_materials = {MaterialType.BLUE_IRON_INGOT: 1.0}
refinery_iron.allowed_input_materials = [MaterialType.BLUE_IRON]
refinery_iron.max_inventory = 50.0

refinery_steel = _register(SystemBBuilding(component_id=514, size=(3, 3), name="Refinery steel block"))
refinery_steel.needs_input, refinery_steel.needs_output = True, True
refinery_steel.input_materials = {MaterialType.DENSE_BLUE_IRON_POWDER: 1.0}
refinery_steel.output_materials = {MaterialType.STEEL_BLOCK: 1.0}
refinery_steel.allowed_input_materials = [MaterialType.DENSE_BLUE_IRON_POWDER]
refinery_steel.max_inventory = 50.0


# System B crusher recipes.
crusher_shell = _register(SystemBBuilding(component_id=521, size=(3, 3), name="Crusher crystal shell"))
crusher_shell.needs_input, crusher_shell.needs_output = True, True
crusher_shell.input_materials = {MaterialType.CRYSTAL_SHELL: 1.0}
crusher_shell.output_materials = {MaterialType.CRYSTAL_SHELL_POWDER: 1.0}
crusher_shell.allowed_input_materials = [MaterialType.CRYSTAL_SHELL]
crusher_shell.max_inventory = 50.0

crusher_ame = _register(SystemBBuilding(component_id=522, size=(3, 3), name="Crusher amethyst"))
crusher_ame.needs_input, crusher_ame.needs_output = True, True
crusher_ame.input_materials = {MaterialType.AMETHYST_FIBER: 1.0}
crusher_ame.output_materials = {MaterialType.AMETHYST_POWDER: 1.0}
crusher_ame.allowed_input_materials = [MaterialType.AMETHYST_FIBER]
crusher_ame.max_inventory = 50.0

crusher_iron = _register(SystemBBuilding(component_id=523, size=(3, 3), name="Crusher blue iron"))
crusher_iron.needs_input, crusher_iron.needs_output = True, True
crusher_iron.input_materials = {MaterialType.BLUE_IRON_INGOT: 1.0}
crusher_iron.output_materials = {MaterialType.BLUE_IRON_POWDER: 1.0}
crusher_iron.allowed_input_materials = [MaterialType.BLUE_IRON_INGOT]
crusher_iron.max_inventory = 50.0

crusher_ori = _register(SystemBBuilding(component_id=524, size=(3, 3), name="Crusher originium"))
crusher_ori.needs_input, crusher_ori.needs_output = True, True
crusher_ori.input_materials = {MaterialType.ORIGINIUM: 1.0}
crusher_ori.output_materials = {MaterialType.ORIGINIUM_POWDER: 1.0}
crusher_ori.allowed_input_materials = [MaterialType.ORIGINIUM]
crusher_ori.max_inventory = 50.0

crusher_sandleaf = _register(SystemBBuilding(component_id=525, size=(3, 3), name="Crusher sandleaf"))
crusher_sandleaf.needs_input, crusher_sandleaf.needs_output = True, True
crusher_sandleaf.input_materials = {MaterialType.SANDLEAF: 1.0}
crusher_sandleaf.output_materials = {MaterialType.SANDLEAF_POWDER: 2.0}
crusher_sandleaf.allowed_input_materials = [MaterialType.SANDLEAF]
crusher_sandleaf.max_inventory = 50.0


# System B parts-machine recipes.
part_ame = _register(SystemBBuilding(component_id=531, size=(3, 3), name="Parts machine amethyst"))
part_ame.needs_input, part_ame.needs_output = True, True
part_ame.input_materials = {MaterialType.AMETHYST_FIBER: 1.0}
part_ame.output_materials = {MaterialType.AMETHYST_PART: 1.0}
part_ame.allowed_input_materials = [MaterialType.AMETHYST_FIBER]
part_ame.max_inventory = 50.0

part_iron = _register(SystemBBuilding(component_id=532, size=(3, 3), name="Parts machine blue iron"))
part_iron.needs_input, part_iron.needs_output = True, True
part_iron.input_materials = {MaterialType.BLUE_IRON_INGOT: 1.0}
part_iron.output_materials = {MaterialType.BLUE_IRON_PART: 1.0}
part_iron.allowed_input_materials = [MaterialType.BLUE_IRON_INGOT]
part_iron.max_inventory = 50.0

part_steel = _register(SystemBBuilding(component_id=533, size=(3, 3), name="Parts machine steel"))
part_steel.needs_input, part_steel.needs_output = True, True
part_steel.input_materials = {MaterialType.STEEL_BLOCK: 1.0}
part_steel.output_materials = {MaterialType.STEEL_PART: 1.0}
part_steel.allowed_input_materials = [MaterialType.STEEL_BLOCK]
part_steel.max_inventory = 50.0


# System B press recipes.
press_ame = _register(SystemBBuilding(component_id=541, size=(3, 3), name="Press amethyst bottle"))
press_ame.needs_input, press_ame.needs_output = True, True
press_ame.input_materials = {MaterialType.AMETHYST_FIBER: 2.0}
press_ame.output_materials = {MaterialType.AMETHYST_BOTTLE: 1.0}
press_ame.allowed_input_materials = [MaterialType.AMETHYST_FIBER]
press_ame.max_inventory = 50.0

press_iron = _register(SystemBBuilding(component_id=542, size=(3, 3), name="Press blue iron bottle"))
press_iron.needs_input, press_iron.needs_output = True, True
press_iron.input_materials = {MaterialType.BLUE_IRON_INGOT: 2.0}
press_iron.output_materials = {MaterialType.BLUE_IRON_BOTTLE: 1.0}
press_iron.allowed_input_materials = [MaterialType.BLUE_IRON_INGOT]
press_iron.max_inventory = 50.0


# System B packager recipes.
pack_low = _register(SystemBBuilding(component_id=551, size=(5, 3), name="Packager low capacity"))
pack_low.needs_input, pack_low.needs_output = True, True
pack_low.input_materials = {MaterialType.AMETHYST_PART: 1.0, MaterialType.ORIGINIUM_POWDER: 2.0}
pack_low.output_materials = {MaterialType.LOW_CAP_BATTERY: 1.0}
pack_low.allowed_input_materials = [MaterialType.AMETHYST_PART, MaterialType.ORIGINIUM_POWDER]
pack_low.max_inventory = 200.0

pack_mid = _register(SystemBBuilding(component_id=552, size=(5, 3), name="Packager medium capacity"))
pack_mid.needs_input, pack_mid.needs_output = True, True
pack_mid.input_materials = {MaterialType.BLUE_IRON_PART: 2.0, MaterialType.ORIGINIUM_POWDER: 3.0}
pack_mid.output_materials = {MaterialType.MID_CAP_BATTERY: 1.0}
pack_mid.allowed_input_materials = [MaterialType.BLUE_IRON_PART, MaterialType.ORIGINIUM_POWDER]
pack_mid.max_inventory = 200.0

pack_high = _register(SystemBBuilding(component_id=553, size=(5, 3), name="Packager high capacity"))
pack_high.needs_input, pack_high.needs_output = True, True
pack_high.input_materials = {MaterialType.STEEL_PART: 2.0, MaterialType.DENSE_ORIGINIUM_POWDER: 3.0}
pack_high.output_materials = {MaterialType.HIGH_CAP_BATTERY: 1.0}
pack_high.allowed_input_materials = [MaterialType.STEEL_PART, MaterialType.DENSE_ORIGINIUM_POWDER]
pack_high.max_inventory = 200.0


# System B grinder recipes.
grinder_dense_iron = _register(SystemBBuilding(component_id=561, size=(6, 4), name="Grinder dense blue iron"))
grinder_dense_iron.needs_input, grinder_dense_iron.needs_output = True, True
grinder_dense_iron.input_materials = {MaterialType.BLUE_IRON_POWDER: 1.2, MaterialType.SANDLEAF_POWDER: 1.0}
grinder_dense_iron.output_materials = {MaterialType.DENSE_BLUE_IRON_POWDER: 1.0}
grinder_dense_iron.allowed_input_materials = [MaterialType.BLUE_IRON_POWDER, MaterialType.SANDLEAF_POWDER]
grinder_dense_iron.max_inventory = 100.0

grinder_dense_originium = _register(SystemBBuilding(component_id=562, size=(6, 4), name="Grinder dense originium"))
grinder_dense_originium.needs_input, grinder_dense_originium.needs_output = True, True
grinder_dense_originium.input_materials = {MaterialType.ORIGINIUM_POWDER: 2.2, MaterialType.SANDLEAF_POWDER: 1.0}
grinder_dense_originium.output_materials = {MaterialType.DENSE_ORIGINIUM_POWDER: 1.0}
grinder_dense_originium.allowed_input_materials = [MaterialType.ORIGINIUM_POWDER, MaterialType.SANDLEAF_POWDER]
grinder_dense_originium.max_inventory = 100.0


def get_transport_instance(component_id: int):
    if component_id == 101:
        belt = SystemABelt(101, "Basic Belt A")
        belt.max_capacity = 3.0
        return belt
    if component_id == 102:
        belt = SystemABelt(102, "Armored Belt A")
        belt.max_capacity = 12.0
        return belt
    if component_id == 110:
        router = SystemALogicRouter(110, "Router A")
        router.max_capacity = 12.0
        return router
    if component_id == 111:
        overflowgate = SystemAOverflowGate(111, "Overflow Gate A")
        overflowgate.max_capacity = 12.0
        return overflowgate
    if component_id == 112:
        bridge = SystemABridge(112, "Bridge A", min_length=1, max_length=3)
        bridge.max_capacity = 12.0
        return bridge
    if component_id == 113:
        crosser = SystemACrosser(113, "Crosser A")
        crosser.max_capacity = 12.0
        return crosser
    if component_id == 151:
        pipe = SystemAPipe(151, "Basic Pipe A")
        pipe.max_capacity = 12.0
        return pipe
    if component_id == 160:
        router = SystemAPipeRouter(160, "Pipe Router A")
        router.max_capacity = 12.0
        return router
    if component_id == 161:
        overflowgate = SystemAPipeOverflowGate(161, "Pipe Overflow Gate A")
        overflowgate.max_capacity = 12.0
        return overflowgate
    if component_id == 162:
        bridge = SystemAPipeBridge(162, "Pipe Bridge A", min_length=1, max_length=3)
        bridge.max_capacity = 12.0
        return bridge
    if component_id == 163:
        crosser = SystemAPipeCrosser(163, "Pipe Crosser A")
        crosser.max_capacity = 12.0
        return crosser
    if component_id == 301:
        belt = SystemBBelt(301, "Belt B")
        belt.max_capacity = 1.0
        return belt
    if component_id == 302:
        pipe = SystemBPipe(302, "Pipe B")
        pipe.max_capacity = 1.0
        return pipe
    if component_id == 311:
        splitter = SystemBSplitter(311, "Belt Splitter B")
        splitter.max_capacity = 1.0
        return splitter
    if component_id == 312:
        merger = SystemBMerger(312, "Belt Merger B")
        merger.max_capacity = 1.0
        return merger
    if component_id == 313:
        access = SystemBBeltAccess(313, "Belt Access B")
        access.max_capacity = 1.0
        return access
    if component_id == 314:
        crosser = SystemBCrosser(314, "Belt Crosser B")
        crosser.max_capacity = 1.0
        return crosser
    if component_id == 321:
        splitter = SystemBPipeSplitter(321, "Pipe Splitter B")
        splitter.max_capacity = 1.0
        return splitter
    if component_id == 322:
        merger = SystemBPipeMerger(322, "Pipe Merger B")
        merger.max_capacity = 1.0
        return merger
    if component_id == 323:
        access = SystemBPipeAccess(323, "Pipe Access B")
        access.max_capacity = 1.0
        return access
    if component_id == 324:
        crosser = SystemBPipeCrosser(324, "Pipe Crosser B")
        crosser.max_capacity = 1.0
        return crosser

    raise ValueError(f"Unknown transport component id: {component_id}")


def get_building_instance(component_id: int) -> SystemABuilding:
    """Return a fresh building instance so mutable runtime state is never shared."""
    if component_id not in BUILDING_CATALOG:
        raise ValueError(f"Unknown building component id: {component_id}")
    return copy.deepcopy(BUILDING_CATALOG[component_id])
