import heapq
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from agents.fdp_sa_agent_v2 import FdpSaAgentV2
from entities.material import MaterialType
from entities.registry import get_building_instance
from entities.transport import Direction
from environment.grid_map import GridMap


@dataclass
class ProductionCell:
    cell_id: int
    sinks: List[int]
    lanes: List[List[int]]
    side_groups: List[List[int]]
    node_ids: List[int]
    depth: int


@dataclass
class CellVariant:
    width: int
    height: int
    offsets: Dict[int, Tuple[int, int, Direction]]


class SequencePairSaAgentV2(FdpSaAgentV2):
    """
    Hypergraph production-cell floorplanner with B*-tree packing and
    negotiated-congestion routing.

    V2 keeps the stable recipe/port primitives from FdpSaAgentV2, but replaces
    the layout search and final routing strategy.
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        super().__init__(target_outputs, available_inputs)
        self.cells: List[ProductionCell] = []
        self.cell_variants: Dict[int, List[CellVariant]] = {}
        self.cell_by_id: Dict[int, ProductionCell] = {}
        self.btree_initial_temp = 450.0
        self.btree_min_temp = 1.0
        self.btree_cooling = 0.92
        self.btree_iters_per_temp = 28
        self.btree_restarts = 10
        self.negotiation_rounds = 5
        self.cell_gap = 2

    def optimize(self, env: GridMap):
        print("\n[SequencePairSaAgentV2] Starting hypergraph cell + B*-tree layout...")
        self._calculate_ratios_and_instances()
        self._build_instance_graph()
        self._build_production_cells(env)

        self.node_positions = self._optimize_btree_layout(env)

        for nid, state in self.node_positions.items():
            building = self.nodes[nid]
            if not env.place_building(building, state['x'], state['y'], state['dir']):
                print(f"[Warning] Building {building.name} could not be placed at ({state['x']},{state['y']}), legalizing...")
                if not self._legalize_placement(env, building, state['x'], state['y'], state['dir'], nid):
                    print(f"[Error] Failed to legalize placement for {building.name}.")

        print("[SequencePairSaAgentV2] Routing selected layout with negotiated congestion...")
        self._reset_routing_state()
        success = self._route_connections_negotiated(env, self.node_positions)
        if not success:
            failed = ", ".join(t['mat'].name for t in self.failed_routes)
            print(f"[SequencePairSaAgentV2] Routed with unresolved tasks: {failed}")
        print("[SequencePairSaAgentV2] Blueprint generation complete.")

    def _build_production_cells(self, env: GridMap):
        incoming, outgoing = self._graph_adjacency()
        depths = self._node_depths()
        sinks = [
            nid for nid, building in self.nodes.items()
            if any(mat in self.target_outputs_dict for mat in building.output_materials)
        ] or [nid for nid in self.nodes if not outgoing[nid]]

        sink_groups = self._merge_parallel_sinks(sinks)
        used = set()
        cells = []
        for cell_id, group_sinks in enumerate(sink_groups):
            lanes = []
            side_groups = []
            for sink in group_sinks:
                sink_sides = []
                for src in sorted(incoming.get(sink, []), key=lambda nid: (-depths.get(nid, 0), nid)):
                    chain = self._primary_chain(src, incoming, used, depths)
                    if len(chain) > 1:
                        lanes.append(chain)
                    elif chain:
                        sink_sides.extend(chain)
                    used.update(chain)
                side_groups.append(sink_sides)
                used.add(sink)

            node_ids = sorted(set(group_sinks) | {n for lane in lanes for n in lane} | {n for side in side_groups for n in side})
            cells.append(ProductionCell(cell_id, group_sinks, lanes, side_groups, node_ids, max(depths.get(n, 0) for n in node_ids)))

        leftovers = [nid for nid in sorted(self.nodes) if nid not in used]
        for nid in leftovers:
            cell_id = len(cells)
            cells.append(ProductionCell(cell_id, [nid], [], [[]], [nid], depths.get(nid, 0)))

        self.cells = cells
        self.cell_by_id = {cell.cell_id: cell for cell in cells}
        self.cell_variants = {cell.cell_id: self._make_cell_variants(cell, env) for cell in cells}

    def _graph_adjacency(self):
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for edge in self.edges:
            incoming[edge['dst']].append(edge['src'])
            outgoing[edge['src']].append(edge['dst'])
        return incoming, outgoing

    def _merge_parallel_sinks(self, sinks: List[int]) -> List[List[int]]:
        grouped = defaultdict(list)
        for nid in sorted(sinks):
            building = self.nodes[nid]
            key = (
                building.component_id,
                tuple(sorted(building.input_materials.keys(), key=lambda mat: mat.name)),
                tuple(sorted(building.output_materials.keys(), key=lambda mat: mat.name)),
            )
            grouped[key].append(nid)
        return [grouped[key] for key in sorted(grouped, key=lambda k: (grouped[k][0], len(grouped[k])))]

    def _primary_chain(self, nid: int, incoming: Dict[int, List[int]], used: Set[int], depths: Dict[int, int]) -> List[int]:
        if nid in used:
            return []
        preds = [p for p in incoming.get(nid, []) if p not in used]
        if not preds:
            return [nid]
        primary = max(preds, key=lambda p: (depths.get(p, 0), -p))
        return self._primary_chain(primary, incoming, used, depths) + [nid]

    def _make_cell_variants(self, cell: ProductionCell, env: GridMap) -> List[CellVariant]:
        variants = []
        seen = set()
        for lane_gap in (0, 1, 2):
            for row_gap in (1, 2, 3):
                for side_gap in (1, 2, 3):
                    for sink_gap in (1, 2, 3):
                        local = self._place_cell_array(cell, lane_gap, row_gap, side_gap, sink_gap)
                        if set(local) != set(cell.node_ids):
                            continue
                        local = self._normalize_local_state(local)
                        _, _, max_x, max_y, _, _ = self._bounding_metrics(local)
                        shape = (max_x, max_y, tuple(sorted((nid, s['x'], s['y']) for nid, s in local.items())))
                        if shape in seen:
                            continue
                        seen.add(shape)
                        variants.append(CellVariant(max_x, max_y, {
                            nid: (s['x'], s['y'], s['dir']) for nid, s in local.items()
                        }))

        if not variants:
            nid = cell.node_ids[0]
            w, h = self.nodes[nid].size
            variants.append(CellVariant(w, h, {nid: (0, 0, Direction.UP)}))
        variants.sort(key=lambda v: (v.width * v.height, v.width + v.height))
        return variants[:96]

    def _place_cell_array(self, cell: ProductionCell, lane_gap: int, row_gap: int, side_gap: int, sink_gap: int) -> Dict:
        state = {}
        sinks = cell.sinks
        lanes = cell.lanes
        sink_sizes = [self._real_size({'size': self.nodes[nid].size, 'dir': Direction.UP}) for nid in sinks]
        sink_block_w = sum(w for w, _ in sink_sizes) + max(0, len(sink_sizes) - 1) * lane_gap
        sink_h = max((h for _, h in sink_sizes), default=0)

        lane_widths = [max(self.nodes[nid].size[0] for nid in lane) for lane in lanes]
        lane_heights = [sum(self.nodes[nid].size[1] for nid in lane) + max(0, len(lane) - 1) * row_gap for lane in lanes]
        lane_block_w = sum(lane_widths) + max(0, len(lane_widths) - 1) * lane_gap
        lane_block_h = max(lane_heights, default=0)
        center_w = max(sink_block_w, lane_block_w)

        left_sides, right_sides = [], []
        for idx, side_group in enumerate(cell.side_groups):
            (left_sides if idx % 2 == 0 else right_sides).extend(side_group)
        left_w = max((self.nodes[nid].size[0] for nid in left_sides), default=0)
        right_w = max((self.nodes[nid].size[0] for nid in right_sides), default=0)
        left_block_w = left_w + side_gap if left_sides else 0

        center_x = left_block_w
        x = center_x + max(0, (center_w - lane_block_w) // 2)
        for lane, lane_w, lane_h in zip(lanes, lane_widths, lane_heights):
            y = max(0, lane_block_h - lane_h)
            for nid in lane:
                w, h = self.nodes[nid].size
                state[nid] = {'x': x + max(0, (lane_w - w) // 2), 'y': y, 'dir': Direction.UP, 'size': self.nodes[nid].size}
                y += h + row_gap
            x += lane_w + lane_gap

        sink_y = lane_block_h + sink_gap
        sink_x = center_x + max(0, (center_w - sink_block_w) // 2)
        for nid, (w, _h) in zip(sinks, sink_sizes):
            state[nid] = {'x': sink_x, 'y': sink_y, 'dir': Direction.UP, 'size': self.nodes[nid].size}
            sink_x += w + lane_gap

        right_x = center_x + center_w + side_gap
        for side_list, side_x in ((left_sides, 0), (right_sides, right_x)):
            y = 0
            for nid in side_list:
                state[nid] = {'x': side_x, 'y': y, 'dir': Direction.UP, 'size': self.nodes[nid].size}
                y += self.nodes[nid].size[1] + row_gap
        return state

    def _normalize_local_state(self, state: Dict) -> Dict:
        min_x, min_y, _, _, _, _ = self._bounding_metrics(state)
        normalized = {}
        for nid, s in state.items():
            normalized[nid] = {'x': s['x'] - min_x, 'y': s['y'] - min_y, 'dir': s['dir'], 'size': s['size']}
        return normalized

    def _optimize_btree_layout(self, env: GridMap) -> Dict:
        best_state = None
        best_score = (float('inf'), float('inf'), float('inf'), float('inf'))

        for idx, candidate in enumerate(self._cell_variant_seed_states(env), start=1):
            failed, routes, area, congestion = self._trial_negotiated_route_state(env, candidate)
            score = (failed, area + routes * 0.12 + congestion * 0.05, routes, self._layout_feedback_cost(candidate, env))
            if score < best_score:
                best_score, best_state = score, candidate
                print(f"[SequencePairSaAgentV2] Cell seed {idx}: failed={failed}, route_cells={routes}, area={area}")

        if len(self.cells) > 1:
            for restart in range(self.btree_restarts):
                tree = self._initial_btree_state(restart)
                tree = self._anneal_btree(env, tree)
                candidate = self._btree_to_building_state(tree, env)
                failed, routes, area, congestion = self._trial_negotiated_route_state(env, candidate)
                score = (failed, area + routes * 0.12 + congestion * 0.05, routes, self._layout_feedback_cost(candidate, env))
                print(f"[SequencePairSaAgentV2] B*-tree candidate {restart + 1}: failed={failed}, route_cells={routes}, area={area}")
                if score < best_score:
                    best_score, best_state = score, candidate

        if best_state is None:
            best_state = self._cell_variant_seed_states(env)[0]

        compacted = self._route_preserving_compact_v2(best_state, env)
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, compacted)
        compacted_score = (failed, area + routes * 0.12 + congestion * 0.05, routes, self._layout_feedback_cost(compacted, env))
        print(f"[SequencePairSaAgentV2] Route-preserving compact: failed={failed}, route_cells={routes}, area={area}")
        if compacted_score <= best_score:
            best_state = compacted

        self._reset_routing_state()
        return best_state

    def _cell_variant_seed_states(self, env: GridMap) -> List[Dict]:
        if not self.cells:
            return []
        variant_count = max(len(v) for v in self.cell_variants.values())
        seeds = []
        for variant_idx in range(variant_count):
            state = {}
            x = self.map_margin
            for cell in sorted(self.cells, key=lambda c: (-c.depth, c.cell_id)):
                variants = self.cell_variants[cell.cell_id]
                variant = variants[min(variant_idx, len(variants) - 1)]
                for nid, (ox, oy, direction) in variant.offsets.items():
                    state[nid] = {'x': x + ox, 'y': self.map_margin + oy, 'dir': direction, 'size': self.nodes[nid].size}
                x += variant.width + self.cell_gap
            if len(state) == len(self.nodes):
                seeds.append(self._fit_state_to_map_v2(state, env))
        return seeds

    def _initial_btree_state(self, restart: int) -> Dict:
        cell_ids = [cell.cell_id for cell in sorted(self.cells, key=lambda c: (-c.depth, c.cell_id))]
        if restart:
            random.shuffle(cell_ids)
        root = cell_ids[0]
        parent = {}
        branch = {}
        for prev, cid in zip(cell_ids, cell_ids[1:]):
            parent[cid] = prev
            branch[cid] = 'left' if random.random() < 0.65 else 'right'
        variants = {cid: random.randrange(len(self.cell_variants[cid])) if restart else 0 for cid in cell_ids}
        return {'root': root, 'parent': parent, 'branch': branch, 'variants': variants}

    def _anneal_btree(self, env: GridMap, initial: Dict) -> Dict:
        current = self._copy_btree(initial)
        current_cost = self._btree_cost(current, env)
        best = self._copy_btree(current)
        best_cost = current_cost
        temp = self.btree_initial_temp
        while temp > self.btree_min_temp:
            for _ in range(self.btree_iters_per_temp):
                candidate = self._mutate_btree(current)
                candidate_cost = self._btree_cost(candidate, env)
                delta = candidate_cost - current_cost
                if delta < 0 or math.exp(-delta / temp) > random.random():
                    current, current_cost = candidate, candidate_cost
                    if current_cost < best_cost:
                        best, best_cost = self._copy_btree(current), current_cost
            temp *= self.btree_cooling
        return best

    def _mutate_btree(self, tree: Dict) -> Dict:
        mutated = self._copy_btree(tree)
        action = random.random()
        ids = [cell.cell_id for cell in self.cells]
        if action < 0.45 and ids:
            cid = random.choice(ids)
            mutated['variants'][cid] = random.randrange(len(self.cell_variants[cid]))
        elif action < 0.70 and mutated['branch']:
            cid = random.choice(list(mutated['branch']))
            mutated['branch'][cid] = 'right' if mutated['branch'][cid] == 'left' else 'left'
        elif action < 0.90 and len(ids) > 2:
            cid = random.choice([i for i in ids if i != mutated['root']])
            possible = [i for i in ids if i != cid]
            mutated['parent'][cid] = random.choice(possible)
        elif len(ids) > 1:
            a, b = random.sample(ids, 2)
            self._swap_tree_labels(mutated, a, b)
        self._sanitize_btree(mutated)
        return mutated

    def _sanitize_btree(self, tree: Dict):
        ids = {cell.cell_id for cell in self.cells}
        if tree['root'] not in ids:
            tree['root'] = min(ids)
        tree['parent'].pop(tree['root'], None)
        for cid in ids:
            tree['variants'].setdefault(cid, 0)
            max_variant = max(0, len(self.cell_variants.get(cid, [])) - 1)
            tree['variants'][cid] = max(0, min(tree['variants'][cid], max_variant))
            if cid == tree['root']:
                continue
            parent = tree['parent'].get(cid)
            if parent not in ids or parent == cid or self._tree_has_ancestor(tree, parent, cid):
                tree['parent'][cid] = tree['root']
            tree['branch'].setdefault(cid, 'left')

        for cid in list(tree['parent']):
            if cid not in ids or cid == tree['root']:
                tree['parent'].pop(cid, None)
        for cid in list(tree['branch']):
            if cid not in ids or cid == tree['root']:
                tree['branch'].pop(cid, None)

    def _tree_has_ancestor(self, tree: Dict, cid: int, ancestor: int) -> bool:
        seen = set()
        while cid in tree['parent'] and cid not in seen:
            seen.add(cid)
            cid = tree['parent'][cid]
            if cid == ancestor:
                return True
        return False

    def _swap_tree_labels(self, tree: Dict, a: int, b: int):
        if tree['root'] == a:
            tree['root'] = b
        elif tree['root'] == b:
            tree['root'] = a
        for child, parent in list(tree['parent'].items()):
            new_child = b if child == a else a if child == b else child
            new_parent = b if parent == a else a if parent == b else parent
            if new_child != child:
                tree['parent'].pop(child)
            tree['parent'][new_child] = new_parent
        for child, side in list(tree['branch'].items()):
            new_child = b if child == a else a if child == b else child
            if new_child != child:
                tree['branch'].pop(child)
            tree['branch'][new_child] = side
        tree['variants'][a], tree['variants'][b] = tree['variants'][b], tree['variants'][a]

    def _btree_cost(self, tree: Dict, env: GridMap) -> float:
        state = self._btree_to_building_state(tree, env)
        return self._layout_feedback_cost(state, env)

    def _btree_to_building_state(self, tree: Dict, env: GridMap) -> Dict:
        cell_pos = self._pack_btree_cells(tree)
        state = {}
        for cid, (base_x, base_y) in cell_pos.items():
            variant = self.cell_variants[cid][tree['variants'][cid]]
            for nid, (ox, oy, direction) in variant.offsets.items():
                state[nid] = {'x': base_x + ox + self.map_margin, 'y': base_y + oy + self.map_margin, 'dir': direction, 'size': self.nodes[nid].size}
        return self._fit_state_to_map_v2(state, env)

    def _pack_btree_cells(self, tree: Dict) -> Dict[int, Tuple[int, int]]:
        children = defaultdict(list)
        for child, parent in tree['parent'].items():
            children[parent].append(child)

        positions = {tree['root']: (0, 0)}
        queue = [tree['root']]
        while queue:
            parent = queue.pop(0)
            px, py = positions[parent]
            parent_variant = self.cell_variants[parent][tree['variants'][parent]]
            for child in children[parent]:
                child_variant = self.cell_variants[child][tree['variants'][child]]
                if tree['branch'].get(child, 'left') == 'left':
                    cx, cy = px + parent_variant.width + self.cell_gap, py
                else:
                    cx, cy = px, py + parent_variant.height + self.cell_gap
                while self._cell_rect_overlaps(cx, cy, child_variant, positions, tree):
                    cx += self.cell_gap
                    cy += self.cell_gap if tree['branch'].get(child) == 'right' else 0
                positions[child] = (cx, cy)
                queue.append(child)
        return positions

    def _cell_rect_overlaps(self, x: int, y: int, variant: CellVariant, positions: Dict[int, Tuple[int, int]], tree: Dict) -> bool:
        for cid, (ox, oy) in positions.items():
            other = self.cell_variants[cid][tree['variants'][cid]]
            if not (x + variant.width + self.cell_gap <= ox or ox + other.width + self.cell_gap <= x or
                    y + variant.height + self.cell_gap <= oy or oy + other.height + self.cell_gap <= y):
                return True
        return False

    def _copy_btree(self, tree: Dict) -> Dict:
        return {'root': tree['root'], 'parent': dict(tree['parent']), 'branch': dict(tree['branch']), 'variants': dict(tree['variants'])}

    def _layout_feedback_cost(self, state: Dict, env: GridMap) -> float:
        min_x, min_y, max_x, max_y, occupied, area = self._bounding_metrics(state)
        cost = area * 20.0 + max(0, area - occupied) * 1.5
        depths = self._node_depths()
        corridor_usage = defaultdict(int)
        for edge in self.edges:
            src = state[edge['src']]
            dst = state[edge['dst']]
            sx, sy = self._state_center(src)
            dx, dy = self._state_center(dst)
            manhattan = abs(sx - dx) + abs(sy - dy)
            cost += manhattan * 7.0
            if depths.get(edge['src'], 0) < depths.get(edge['dst'], 0) and src['y'] > dst['y']:
                cost += 900.0
            x0, x1 = sorted((int(sx), int(dx)))
            y0, y1 = sorted((int(sy), int(dy)))
            for x in range(x0, x1 + 1):
                corridor_usage[(x, int(sy))] += 1
            for y in range(y0, y1 + 1):
                corridor_usage[(int(dx), y)] += 1
        cost += sum((count - 1) ** 2 * 18.0 for count in corridor_usage.values() if count > 1)
        if min_x < self.map_margin or min_y < self.map_margin or max_x > env.width - self.map_margin or max_y > env.height - self.map_margin:
            cost += 100000.0
        return cost

    def _trial_negotiated_route_state(self, env: GridMap, state: Dict) -> Tuple[int, int, int, int]:
        result = self._negotiate_paths(env, state, keep_paths=False)
        _, _, _, _, _, area = self._bounding_metrics(state)
        return result['failed'], result['route_cells'], area, result['congestion']

    def _route_connections_negotiated(self, env: GridMap, state: Dict) -> bool:
        result = self._negotiate_paths(env, state, keep_paths=True)
        self.failed_routes = []
        self._reset_routing_state()
        if result['failed_tasks']:
            self.failed_routes = list(result['failed_tasks'])

        for task, path in result['paths']:
            self._lay_path(env, path, task)
        return not self.failed_routes

    def _negotiate_paths(self, env: GridMap, state: Dict, keep_paths: bool) -> Dict:
        saved = self._save_routing_context()
        congestion = defaultdict(float)
        best = {'failed': float('inf'), 'route_cells': float('inf'), 'congestion': float('inf'), 'paths': [], 'failed_tasks': []}
        tasks = self._routing_tasks_for_state(state)

        for _round in range(self.negotiation_rounds):
            trial_env = GridMap(env.width, env.height)
            self.node_positions = {k: v.copy() for k, v in state.items()}
            self._reset_routing_state()
            placement_failed = 0
            for nid, s in self.node_positions.items():
                building = get_building_instance(self.nodes[nid].component_id)
                if not trial_env.place_building(building, s['x'], s['y'], s['dir']):
                    placement_failed += 1

            paths = []
            failed_tasks = []
            usage = defaultdict(int)
            if placement_failed == 0:
                for task in tasks:
                    starts = self._task_starts(trial_env, task)
                    goals = self._task_goals(trial_env, task)
                    if not starts or not goals:
                        failed_tasks.append(task)
                        continue
                    protected_io = set()
                    for ports in self.generated_inputs.values():
                        protected_io.update(ports)
                    for ports in self.generated_outputs.values():
                        protected_io.update(ports)
                    forbidden = (self.all_building_ports | protected_io) - set(starts) - set(goals)
                    path = self._a_star_route_multi_negotiated(trial_env, starts, goals, forbidden, task, congestion)
                    if path is None:
                        failed_tasks.append(task)
                        continue
                    paths.append((task, path))
                    for p in path:
                        usage[p] += 1
                    self._lay_path(trial_env, path, task)

            failed_count = placement_failed + len(failed_tasks)
            congestion_score = sum(max(0, count - 1) for count in usage.values())
            route_cells = len(trial_env.transports)
            if (failed_count, route_cells + congestion_score, route_cells) < (best['failed'], best['route_cells'] + best['congestion'], best['route_cells']):
                best = {
                    'failed': failed_count,
                    'route_cells': route_cells,
                    'congestion': congestion_score,
                    'paths': paths if keep_paths else [],
                    'failed_tasks': failed_tasks,
                }

            for p, count in usage.items():
                if count > 1:
                    congestion[p] += (count - 1) * 8.0
                else:
                    congestion[p] += 0.15
            for task in failed_tasks:
                for nid_key in ('src', 'dst'):
                    if task.get(f'{nid_key}_type') == 'node':
                        s = state[task[nid_key]]
                        sx, sy = self._state_center(s)
                        congestion[(int(sx), int(sy))] += 20.0

        self._restore_routing_context(saved)
        return best

    def _routing_tasks_for_state(self, state: Dict) -> List[Dict]:
        self.node_positions = state
        self.all_building_ports = set()
        for nid in self.nodes:
            self.all_building_ports.update(self._get_all_ports_of_node(nid, True))
            self.all_building_ports.update(self._get_all_ports_of_node(nid, False))
        tasks = [{'src_type': 'node', 'src': e['src'], 'dst_type': 'node', 'dst': e['dst'], 'mat': e['mat']} for e in self.edges]
        for nid, building in self.nodes.items():
            for mat in building.input_materials:
                if mat in self.available_inputs:
                    tasks.append({'src_type': 'ext_in', 'src': None, 'dst_type': 'node', 'dst': nid, 'mat': mat})
            for mat in building.output_materials:
                if mat in self.target_outputs_dict:
                    tasks.append({'src_type': 'node', 'src': nid, 'dst_type': 'ext_out', 'dst': None, 'mat': mat})
        tasks.sort(key=lambda t: (t['src_type'] == 'ext_in' or t['dst_type'] == 'ext_out', self._route_task_distance(t)))
        return tasks

    def _a_star_route_multi_negotiated(
        self,
        env: GridMap,
        starts: List[Tuple[int, int]],
        goals: List[Tuple[int, int]],
        forbidden: Set[Tuple[int, int]],
        task: Dict,
        congestion: Dict[Tuple[int, int], float],
    ) -> Optional[List[Tuple[int, int]]]:
        frontier = []
        came_from = {}
        g_score = {}
        counter = 0
        for start in starts:
            h = min(abs(start[0] - g[0]) + abs(start[1] - g[1]) for g in goals)
            heapq.heappush(frontier, (h, counter, start))
            counter += 1
            came_from[start] = None
            g_score[start] = 0

        best_goal = None
        while frontier:
            current = heapq.heappop(frontier)[2]
            if current in goals:
                best_goal = current
                break
            x, y = current
            allowed_moves = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            cell_current = env._get_cell(x, y)
            if cell_current is not None and type(cell_current).__name__ == "SystemBBelt" and current not in starts and current not in goals and came_from[current] is not None:
                px, py = came_from[current]
                allowed_moves = [(x - px, y - py)]

            for dx, dy in allowed_moves:
                nx, ny = x + dx, y + dy
                if not env.is_in_bounds(nx, ny) or (nx, ny) in forbidden:
                    continue
                cell_next = env._get_cell(nx, ny)
                crossable = self._is_crossable_step(cell_next, nx, ny, x, y, starts, goals)
                if cell_next is not None and (nx, ny) not in starts and (nx, ny) not in goals and not crossable:
                    continue

                turn_penalty = 0
                if came_from[current] is not None:
                    px, py = came_from[current]
                    if (x - px) != dx or (y - py) != dy:
                        turn_penalty = 2
                cost = (
                    1
                    + turn_penalty
                    + (12 if crossable else 0)
                    + congestion.get((nx, ny), 0)
                    + self._route_corridor_penalty(task, nx, ny)
                )
                new_cost = g_score[current] + cost
                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    h = min(abs(nx - gx) + abs(ny - gy) for gx, gy in goals)
                    heapq.heappush(frontier, (new_cost + h, counter, (nx, ny)))
                    counter += 1
                    came_from[(nx, ny)] = current

        if best_goal is None:
            return None
        path = []
        current = best_goal
        while current is not None:
            path.append(current)
            current = came_from[current]
        return path[::-1]

    def _is_crossable_step(self, cell_next, nx, ny, x, y, starts, goals) -> bool:
        if cell_next is None or (nx, ny) in starts or (nx, ny) in goals:
            return False
        if type(cell_next).__name__ != "SystemBBelt":
            return False
        move_dir = Direction.RIGHT if nx > x else Direction.LEFT if nx < x else Direction.DOWN if ny > y else Direction.UP
        belt_out = getattr(cell_next, 'direction', Direction.RIGHT)
        belt_in = getattr(cell_next, 'in_dir', self._get_opposite_dir(belt_out))
        straight = (belt_out, belt_in) in [
            (Direction.RIGHT, Direction.LEFT),
            (Direction.LEFT, Direction.RIGHT),
            (Direction.UP, Direction.DOWN),
            (Direction.DOWN, Direction.UP),
        ]
        return straight and (
            (move_dir in (Direction.UP, Direction.DOWN) and belt_out in (Direction.LEFT, Direction.RIGHT))
            or (move_dir in (Direction.LEFT, Direction.RIGHT) and belt_out in (Direction.UP, Direction.DOWN))
        )

    def _route_preserving_compact_v2(self, state: Dict, env: GridMap) -> Dict:
        current = {nid: item.copy() for nid, item in state.items()}
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, current)
        if failed:
            return current
        for _ in range(5):
            changed = False
            for nid, axis, direction in self._compact_move_order(current):
                while True:
                    trial = {k: v.copy() for k, v in current.items()}
                    trial[nid][axis] += direction
                    if not self._is_state_legal(trial, env, gap=0):
                        break
                    t_failed, t_routes, t_area, t_congestion = self._trial_negotiated_route_state(env, trial)
                    if t_failed:
                        break
                    if t_area < area or (t_area == area and t_routes + t_congestion < routes + congestion):
                        current, routes, area, congestion = trial, t_routes, t_area, t_congestion
                        changed = True
                    else:
                        break
            if not changed:
                break
        return current

    def _compact_move_order(self, state: Dict) -> List[Tuple[int, str, int]]:
        min_x, min_y, max_x, max_y, _, _ = self._bounding_metrics(state)
        moves = []
        for nid, item in state.items():
            w, h = self._real_size(item)
            if item['x'] == min_x:
                moves.append((nid, 'x', 1))
            if item['x'] + w == max_x:
                moves.append((nid, 'x', -1))
            if item['y'] == min_y:
                moves.append((nid, 'y', 1))
            if item['y'] + h == max_y:
                moves.append((nid, 'y', -1))
        return moves

    def _fit_state_to_map_v2(self, state: Dict, env: GridMap) -> Dict:
        fitted = {k: v.copy() for k, v in state.items()}
        min_x, min_y, max_x, max_y, _, _ = self._bounding_metrics(fitted)
        dx = self.map_margin - min_x
        dy = self.map_margin - min_y
        if max_x + dx > env.width - self.map_margin:
            dx -= max_x + dx - (env.width - self.map_margin)
        if max_y + dy > env.height - self.map_margin:
            dy -= max_y + dy - (env.height - self.map_margin)
        for item in fitted.values():
            item['x'] += dx
            item['y'] += dy
        return fitted

    def _save_routing_context(self):
        return (
            self.node_positions,
            set(self.used_ports),
            defaultdict(list, {k: v[:] for k, v in self.generated_inputs.items()}),
            defaultdict(list, {k: v[:] for k, v in self.generated_outputs.items()}),
            list(self.failed_routes),
            set(getattr(self, 'all_building_ports', set())),
        )

    def _restore_routing_context(self, saved):
        self.node_positions, self.used_ports, self.generated_inputs, self.generated_outputs, self.failed_routes, self.all_building_ports = saved
