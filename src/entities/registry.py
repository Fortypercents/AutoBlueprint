import copy
from entities.material import MaterialType
from entities.building import Building

# 建立一个全局的字典作为“建筑图鉴”
BUILDING_CATALOG = {}

# --- 1. 注册熔炉 (ID: 201) ---
furnace = Building(component_id=201, size=(3, 3), name="石炉 (Stone Furnace)")
furnace.needs_input = True
furnace.input_materials = {MaterialType.IRON_ORE: 2.0}
furnace.needs_output = True
furnace.output_materials = {MaterialType.IRON_PLATE: 1.0}
furnace.consumes_power = True
furnace.power_consumption = 90.0

BUILDING_CATALOG[201] = furnace


# --- 2. 注册组装机 (ID: 202) ---
# assembler = Building(...)
# BUILDING_CATALOG[202] = assembler

def get_building_instance(component_id: int) -> Building:
    """
    工厂方法：Agent 每次在地图上放置建筑时，调用这个方法获取一个【全新的副本】，
    防止多个同类建筑共享同一个内存地址。
    """
    if component_id not in BUILDING_CATALOG:
        raise ValueError(f"未知的建筑组件编号: {component_id}")

    # 必须使用深拷贝 (deepcopy)，这样你在地图上放 10 个熔炉，它们的独立状态才不会互相干扰
    return copy.deepcopy(BUILDING_CATALOG[component_id])