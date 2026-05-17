# Implementation note.

from typing import Dict, List, Tuple, Optional
import math
import heapq
from entities.material import MaterialType
from entities.building import Building
from entities.registry import get_building_instance, BUILDING_CATALOG, get_transport_instance
from environment.grid_map import GridMap


class BaseAgent:
    'Routing status message.'

    def __init__(self, target_outputs: Dict[MaterialType, float]):
        'AutoBlueprint status message.'
        self.target_outputs = target_outputs
        self.required_buildings: List[Building] = []
        self.raw_material_inputs: Dict[MaterialType, float] = {}

        # Building placement logic.
        self.recipe_lookup = self._build_recipe_lookup()

    def _build_recipe_lookup(self) -> Dict[MaterialType, int]:
        'Layout status message.'
        lookup = {}
        for b_id, building in BUILDING_CATALOG.items():
            for out_mat in building.output_materials:
                lookup[out_mat] = b_id
        return lookup

    def calculate_production_chain(self):
        'Layout status message.'
        demand_queue = self.target_outputs.copy()
        self.required_buildings = []
        self.raw_material_inputs = {}

        while demand_queue:
            mat, amount = demand_queue.popitem()

            if mat not in self.recipe_lookup:
                # Building placement logic.
                self.raw_material_inputs[mat] = self.raw_material_inputs.get(mat, 0) + amount
                continue

            # Building placement logic.
            b_id = self.recipe_lookup[mat]
            proto_building = BUILDING_CATALOG[b_id]

            # Building placement logic.
            speed = getattr(proto_building, 'production_speed', 1.0)
            production_rate = proto_building.output_materials[mat] * speed

            # Building placement logic.
            num_buildings = math.ceil(amount / production_rate)

            for _ in range(num_buildings):
                # Implementation note.
                new_building = get_building_instance(b_id)
                self.required_buildings.append(new_building)

            # Building placement logic.
            for in_mat, in_amount in proto_building.input_materials.items():
                # Implementation note.
                total_in_needed = (in_amount * speed) * (amount / production_rate)
                demand_queue[in_mat] = demand_queue.get(in_mat, 0) + total_in_needed

        print('Agent status message.')
        print(f" -> Target outputs: {self.target_outputs}")
        print(f" -> Required raw inputs: {self.raw_material_inputs}")
        print(f" -> Required buildings: {len(self.required_buildings)}\n")

    def evaluate_layout(self, env: GridMap) -> float:
        'AutoBlueprint status message.'
        if not env.buildings:
            return float('inf')

        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = 0, 0

        # Building placement logic.
        for b in env.buildings:
            ax, ay = b.anchor_pos
            w, h = b.size
            min_x = min(min_x, ax)
            min_y = min(min_y, ay)
            max_x = max(max_x, ax + w)
            max_y = max(max_y, ay + h)

        # Implementation note.
        area = (max_x - min_x) * (max_y - min_y)

        # Implementation note.
        belt_count = len(env.transports)

        # Cost and penalty calculation.
        # Building placement logic.
        fitness = area + (belt_count * 1.5)

        return fitness

    def a_star_route(self, env: GridMap, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[
        List[Tuple[int, int]]]:
        'Routing status message.'

        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        frontier = []
        heapq.heappush(frontier, (0, start))
        came_from = {start: None}
        g_score = {start: 0}

        while frontier:
            current = heapq.heappop(frontier)[1]

            if current == goal:
                break

            x, y = current
            # Implementation note.
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = x + dx, y + dy

                # Implementation note.
                if not env.is_in_bounds(nx, ny):
                    continue

                # Building placement logic.
                # Building placement logic.
                if env.grid[ny][nx] is not None and (nx, ny) != goal:
                    continue

                new_cost = g_score[current] + 1
                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    priority = new_cost + heuristic((nx, ny), goal)
                    heapq.heappush(frontier, (priority, (nx, ny)))
                    came_from[(nx, ny)] = current

        # Routing logic.
        path = []
        if goal in came_from:
            curr = goal
            while curr != start:
                path.append(curr)
                curr = came_from[curr]
            path.reverse()
            return path
        return None

    def optimize(self, env: GridMap):
        'Layout status message.'
        raise NotImplementedError('Layout status message.')