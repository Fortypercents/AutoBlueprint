import heapq
from typing import List, Tuple, Dict, Optional, Any

from entities.registry import get_transport_instance
from entities.transport import Direction, TransportComponent
from entities.building import Building
from environment.grid_map import GridMap
from agents.base_agent import BaseAgent


class CompactLayoutAgent(BaseAgent):
    'Layout status message.'

    def __init__(self, target_outputs, ext_in=(0, 2), ext_out=(31, 20)):
        super().__init__(target_outputs)
        self.ext_in = ext_in
        self.ext_out = ext_out
        self.belt_id = 101  # Implementation note.

    def _sort_buildings_by_dependency(self) -> List[Building]:
        'AutoBlueprint status message.'
        sorted_buildings = []
        pending = list(self.required_buildings)
        available_mats = set(self.raw_material_inputs.keys())

        while pending:
            ready_buildings = [b for b in pending if all(mat in available_mats for mat in b.input_materials)]
            if not ready_buildings:
                print('Warning: planning issue detected.')
                sorted_buildings.extend(pending)
                break

            for b in ready_buildings:
                sorted_buildings.append(b)
                pending.remove(b)
                for out_mat in b.output_materials:
                    available_mats.add(out_mat)

        return sorted_buildings

    def _is_adjacent(self, x1: int, y1: int, w1: int, h1: int,
                     x2: int, y2: int, w2: int, h2: int) -> bool:
        'AutoBlueprint status message.'
        # Implementation note.
        if (x1 + w1 == x2 or x2 + w2 == x1):
            if max(y1, y2) < min(y1 + h1, y2 + h2):
                return True
        # Implementation note.
        if (y1 + h1 == y2 or y2 + h2 == y1):
            if max(x1, x2) < min(x1 + w1, x2 + w2):
                return True
        return False

    def _get_empty_perimeter(self, env: GridMap, b: Building) -> Optional[Tuple[int, int]]:
        'Layout status message.'
        for px, py in env.get_perimeter_coords(b):
            if env._get_cell(px, py) is None:
                return (px, py)
        return None

    # ==========================================
    # Routing logic.
    # ==========================================
    def _manhattan_distance(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

    def _get_neighbors(self, current: Tuple[int, int]) -> List[Tuple[int, int]]:
        x, y = current
        return [(x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)]

    def find_path_astar(self, env: GridMap, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[
        List[Tuple[int, int]]]:
        open_set = []
        heapq.heappush(open_set, (0, start))
        came_from = {}
        g_score = {start: 0}
        f_score = {start: self._manhattan_distance(start, goal)}

        while open_set:
            current_f, current = heapq.heappop(open_set)

            if current == goal:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path

            for neighbor in self._get_neighbors(current):
                nx, ny = neighbor
                if not (0 <= nx < env.width and 0 <= ny < env.height):
                    continue

                cell = env._get_cell(nx, ny)
                if cell is not None and neighbor != goal and neighbor != start:
                    continue

                tentative_g_score = g_score[current] + 1
                if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + self._manhattan_distance(neighbor, goal)
                    if not any(item[1] == neighbor for item in open_set):
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
        return None

    def _build_belt_path(self, env: GridMap, path: List[Tuple[int, int]], start_pos: Tuple[int, int]):
        'Routing status message.'
        if not path: return

        # Implementation note.
        sx, sy = start_pos
        source_belt = env._get_cell(sx, sy)
        if isinstance(source_belt, TransportComponent):
            fx, fy = path[0]
            if fx > sx:
                source_belt.direction = Direction.RIGHT
            elif fx < sx:
                source_belt.direction = Direction.LEFT
            elif fy > sy:
                source_belt.direction = Direction.DOWN
            else:
                source_belt.direction = Direction.UP

        # Implementation note.
        for step_idx in range(len(path)):
            px, py = path[step_idx]
            if step_idx < len(path) - 1:
                nx, ny = path[step_idx + 1]
                if nx > px:
                    belt_dir = Direction.RIGHT
                elif nx < px:
                    belt_dir = Direction.LEFT
                elif ny > py:
                    belt_dir = Direction.DOWN
                else:
                    belt_dir = Direction.UP
            else:
                belt_dir = Direction.DOWN  # Implementation note.

            if env._get_cell(px, py) is None:
                belt = get_transport_instance(self.belt_id)
                env.place_transport(belt, px, py, belt_dir)

    def optimize(self, env: GridMap):
        print('Agent status message.')
        self.calculate_production_chain()
        ordered_buildings = self._sort_buildings_by_dependency()

        # Building placement logic.
        available_sources: Dict[Any, Any] = {}
        main_input_mat = list(self.raw_material_inputs.keys())[0] if self.raw_material_inputs else None

        if main_input_mat:
            available_sources[main_input_mat] = "EXT_IN"
            start_belt = get_transport_instance(self.belt_id)
            env.place_transport(start_belt, self.ext_in[0], self.ext_in[1], Direction.RIGHT)

        for b in ordered_buildings:
            placed = False
            bw, bh = b.size
            req_mat = list(b.input_materials.keys())[0] if b.input_materials else None
            provider = available_sources.get(req_mat)

            if provider == "EXT_IN":
                print(f"Layout status for building: {b.name}")
                # Implementation note.
                for y in range(2, 6):
                    if placed: break
                    for x in range(2, 6):
                        if env.can_place_building(b, x, y):
                            env.place_building(b, x, y)

                            # Implementation note.
                            target_in = self._get_empty_perimeter(env, b)
                            path = self.find_path_astar(env, self.ext_in, target_in)

                            if path is not None:
                                self._build_belt_path(env, path, self.ext_in)
                                # Implementation note.
                                last_belt = env._get_cell(target_in[0], target_in[1])
                                if last_belt:
                                    if target_in[0] < x:
                                        last_belt.direction = Direction.RIGHT
                                    elif target_in[0] >= x + bw:
                                        last_belt.direction = Direction.LEFT
                                    elif target_in[1] < y:
                                        last_belt.direction = Direction.DOWN
                                    else:
                                        last_belt.direction = Direction.UP

                                placed = True
                                for out_mat in b.output_materials:
                                    available_sources[out_mat] = b  # Building placement logic.
                                break

            elif isinstance(provider, Building):
                print(f"Layout status for building: {b.name}")
                # Building placement logic.
                px, py = provider.anchor_pos
                pw, ph = provider.size

                # Building placement logic.
                for y in range(max(0, py - bh), min(env.height - bh, py + ph + 1)):
                    if placed: break
                    for x in range(max(0, px - bw), min(env.width - bw, px + pw + 1)):
                        # Implementation note.
                        if self._is_adjacent(x, y, bw, bh, px, py, pw, ph):
                            if env.can_place_building(b, x, y):
                                env.place_building(b, x, y)
                                placed = True
                                print("AutoBlueprint status message.")
                                for out_mat in b.output_materials:
                                    available_sources[out_mat] = b
                                break

            if not placed:
                print(f"Layout status for building: {b.name}")

        # ==========================================
        # Input/output port handling.
        # ==========================================
        target_mat = list(self.target_outputs.keys())[0]
        final_provider = available_sources.get(target_mat)

        if isinstance(final_provider, Building):
            print(f"Connecting final output for {target_mat.name}.")
            out_start = self._get_empty_perimeter(env, final_provider)

            if out_start:
                belt = get_transport_instance(self.belt_id)
                env.place_transport(belt, out_start[0], out_start[1], Direction.RIGHT)  # Implementation note.

                # Implementation note.
                px, py = final_provider.anchor_pos
                pw, ph = final_provider.size
                if out_start[0] < px:
                    belt.direction = Direction.LEFT
                elif out_start[0] >= px + pw:
                    belt.direction = Direction.RIGHT
                elif out_start[1] < py:
                    belt.direction = Direction.UP
                else:
                    belt.direction = Direction.DOWN

                final_path = self.find_path_astar(env, out_start, self.ext_out)
                if final_path:
                    self._build_belt_path(env, final_path, out_start)
                    print('AutoBlueprint status message.')

    def render_blueprint(self, env: GridMap, tick: int = 0, current_yield: Dict = None):
        yield_str = ", ".join([f"[{getattr(m, 'name', str(m))}]: {v}" for m, v in (current_yield or {}).items()])
        b_legend = {}
        letter_char = 'A'
        for b in env.buildings:
            if b.name not in b_legend:
                b_legend[b.name] = letter_char
                letter_char = chr(ord(letter_char) + 1)

        legend_str = " | ".join([f"[{v}] {k}" for k, v in b_legend.items()])

        print("\n" * 2)
        print("AutoBlueprint status message.")
        print(f"Terminal output: {yield_str}")
        print(f"Building legend: {legend_str}")
        print("=" * 64)

        dir_symbols = {Direction.RIGHT: ">", Direction.LEFT: "<", Direction.UP: "^", Direction.DOWN: "v"}
        for y in range(env.height):
            row_str = ""
            for x in range(env.width):
                cell = env._get_cell(x, y)
                if cell is None:
                    row_str += " . "
                elif hasattr(cell, 'size'):
                    letter = b_legend.get(getattr(cell, 'name', '?'), '?')
                    row_str += f"[{letter}]"
                elif isinstance(cell, TransportComponent):
                    item = getattr(cell, 'current_item', None)
                    c_name = type(cell).__name__
                    is_router = "Router" in c_name or "Splitter" in c_name or "Merger" in c_name
                    base_char = "S" if is_router else dir_symbols.get(cell.direction, "*")

                    if item:
                        amt = int(item[1]) if isinstance(item, tuple) else 1
                        row_str += f"{amt:02d}{base_char}"
                    else:
                        row_str += f"[S]" if is_router else f" {base_char} "
                else:
                    row_str += "[?]"
            print(f"{y:02d} {row_str}")
        print("==================================================================")