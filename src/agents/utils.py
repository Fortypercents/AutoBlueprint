from typing import Dict, Any
from entities.registry import BUILDING_CATALOG

def get_recipe_catalog() -> Dict[int, Dict[str, Any]]:
    'Layout status message.'
    recipes = {}
    for cid, b_proto in BUILDING_CATALOG.items():
        recipes[cid] = {
            'in': getattr(b_proto, 'input_materials', {}),
            'out': getattr(b_proto, 'output_materials', {}),
            'speed': getattr(b_proto, 'production_speed', 1.0)
        }
    return recipes