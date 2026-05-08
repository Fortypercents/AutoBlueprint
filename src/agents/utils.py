from typing import Dict, Any
from entities.registry import BUILDING_CATALOG

def get_recipe_catalog() -> Dict[int, Dict[str, Any]]:
    """
    构建全局配比映射关系：提取注册表中所有建筑的输入、输出和生产速度。
    返回格式: {building_id: {'in': {MaterialType: amount}, 'out': {MaterialType: amount}, 'speed': float}}
    """
    recipes = {}
    for cid, b_proto in BUILDING_CATALOG.items():
        recipes[cid] = {
            'in': getattr(b_proto, 'input_materials', {}),
            'out': getattr(b_proto, 'output_materials', {}),
            'speed': getattr(b_proto, 'production_speed', 1.0)
        }
    return recipes