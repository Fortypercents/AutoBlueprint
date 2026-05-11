import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from agents.fdp_sa_agent_v2 import FdpSaAgentV2
from entities.material import MaterialType
from entities.transport import Direction
from environment.grid_map import GridMap


@dataclass
class ModuleVariant:
    width: int
    height: int
    offsets: Dict[int, Tuple[int, int, Direction]]


@dataclass
class LayoutModule:
    module_id: int
    node_ids: List[int]
    preferred_layer: int
    variants: List[ModuleVariant]


class SequencePairSaAgentV1(FdpSaAgentV2):
    """
    Sequence Pair + SA floorplanning agent.

    Buildings are first grouped into production modules. SA then searches
    sequence-pair permutations and module packing variants instead of raw
    building coordinates.
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        super().__init__(target_outputs, available_inputs)
        self.modules: List[LayoutModule] = []
        self.module_by_id: Dict[int, LayoutModule] = {}
        self.module_gap = 3
        self.internal_gap = 2
        self.sp_initial_temp = 700.0
        self.sp_min_temp = 1.0
        self.sp_cooling_rate = 0.94
        self.sp_iters_per_temp = 35
        self.sp_restarts = 12

    def optimize(self, env: GridMap):
        print("\n[SequencePairSaAgentV1] Starting modular Sequence Pair + SA layout...")

        self._calculate_ratios_and_instances()
        self._build_instance_graph()
        self._build_modules()

        self.node_positions = self._optimize_sequence_pair(env)

        for nid, state in self.node_positions.items():
            building = self.nodes[nid]
            if not env.place_building(building, state['x'], state['y'], state['dir']):
                print(f"[Warning] Building {building.name} could not be placed at ({state['x']},{state['y']}), legalizing...")
                if not self._legalize_placement(env, building, state['x'], state['y'], state['dir'], nid):
                    print(f"[Error] Failed to legalize placement for {building.name}.")

        print("[SequencePairSaAgentV1] Routing selected layout...")
        self._reset_routing_state()
        success = self._route_connections(env)
        if not success:
            failed = ", ".join(task['mat'].name for task in self.failed_routes)
            print(f"[SequencePairSaAgentV1] Routed with unresolved tasks: {failed}")
        print("[SequencePairSaAgentV1] Blueprint generation complete.")

    def _build_modules(self):
        depths = self._node_depths()
        grouped = defaultdict(list)
        for nid, building in self.nodes.items():
            grouped[(depths.get(nid, 0), building.component_id)].append(nid)

        modules = []
        for module_id, ((depth, _component_id), node_ids) in enumerate(sorted(grouped.items())):
            node_ids = sorted(node_ids)
            modules.append(
                LayoutModule(
                    module_id=module_id,
                    node_ids=node_ids,
                    preferred_layer=depth,
                    variants=self._make_module_variants(node_ids),
                )
            )

        self.modules = modules
        self.module_by_id = {module.module_id: module for module in modules}

    def _make_module_variants(self, node_ids: List[int]) -> List[ModuleVariant]:
        n = len(node_ids)
        if n == 0:
            return []

        col_options = {n, 1, max(1, math.ceil(math.sqrt(n)))}
        if n > 2:
            col_options.add(max(1, math.ceil(n / 2)))

        variants = []
        seen_shapes = set()
        for cols in sorted(col_options):
            rows = math.ceil(n / cols)
            offsets = {}
            max_w_by_col = [0] * cols
            max_h_by_row = [0] * rows

            for idx, nid in enumerate(node_ids):
                row, col = divmod(idx, cols)
                w, h = self.nodes[nid].size
                max_w_by_col[col] = max(max_w_by_col[col], w)
                max_h_by_row[row] = max(max_h_by_row[row], h)

            x_starts = [0]
            for col in range(1, cols):
                x_starts.append(x_starts[-1] + max_w_by_col[col - 1] + self.internal_gap)

            y_starts = [0]
            for row in range(1, rows):
                y_starts.append(y_starts[-1] + max_h_by_row[row - 1] + self.internal_gap)

            for idx, nid in enumerate(node_ids):
                row, col = divmod(idx, cols)
                offsets[nid] = (x_starts[col], y_starts[row], Direction.UP)

            width = sum(max_w_by_col) + max(0, cols - 1) * self.internal_gap
            height = sum(max_h_by_row) + max(0, rows - 1) * self.internal_gap
            shape = (width, height, tuple(sorted(offsets.items())))
            if shape in seen_shapes:
                continue
            seen_shapes.add(shape)
            variants.append(ModuleVariant(width=width, height=height, offsets=offsets))

        return variants

    def _optimize_sequence_pair(self, env: GridMap) -> Dict:
        if not self.modules:
            return {}

        best_state = None
        best_score = (float('inf'), float('inf'), float('inf'), float('inf'))
        base_state = self._initial_sp_state()
        for seed_idx, semantic_seed in enumerate(self._semantic_lane_candidates(env), start=1):
            failed, routes, area = self._trial_route_state(env, semantic_seed)
            score = (failed, area + routes * 0.15, routes, self._cheap_building_cost(semantic_seed, env))
            if score < best_score:
                best_score = score
                best_state = semantic_seed
                print(f"[SequencePairSaAgentV1] Semantic lane seed {seed_idx}: failed={failed}, route_cells={routes}, area={area}")

        for restart in range(self.sp_restarts):
            sp_state = self._randomize_sp_state(base_state, restart)
            current = self._anneal_sequence_pair(env, sp_state)
            building_state = self._sp_to_building_state(current, env)
            failed, routes, area = self._trial_route_state(env, building_state)
            score = (failed, area + routes * 0.15, routes, self._cheap_sp_cost(current, env))
            print(f"[SequencePairSaAgentV1] Candidate {restart + 1}: failed={failed}, route_cells={routes}, area={area}")

            if score < best_score:
                best_score = score
                best_state = building_state

            if failed:
                for distance in (1, 2):
                    repaired = self._expand_state(building_state, env, distance)
                    r_failed, r_routes, r_area = self._trial_route_state(env, repaired)
                    r_score = (r_failed, r_area + r_routes * 0.15, r_routes, self._cheap_building_cost(repaired, env))
                    print(
                        f"[SequencePairSaAgentV1] Candidate {restart + 1}.{distance}: "
                        f"failed={r_failed}, route_cells={r_routes}, area={r_area}"
                    )
                    if r_score < best_score:
                        best_score = r_score
                        best_state = repaired

        if best_state is not None:
            compacted_state = self._route_preserving_compact(best_state, env)
            failed, routes, area = self._trial_route_state(env, compacted_state)
            compacted_score = (failed, area + routes * 0.15, routes, self._cheap_building_cost(compacted_state, env))
            print(f"[SequencePairSaAgentV1] Route-preserving compact: failed={failed}, route_cells={routes}, area={area}")
            if compacted_score <= best_score:
                best_state = compacted_state

        self._reset_routing_state()
        return best_state

    def _semantic_lane_candidates(self, env: GridMap) -> List[Dict]:
        groups = self._production_lane_groups()
        if not groups:
            return []

        candidates = []
        for lane_gap in (0, 1, 2):
            for row_gap in (1, 2, 3):
                for side_gap in (1, 2, 3):
                    for sink_gap in (1, 2, 3):
                        state = {}
                        group_x = self.map_margin
                        base_y = self.map_margin

                        for group in groups:
                            placed = self._place_lane_group(
                                group,
                                state,
                                group_x,
                                base_y,
                                lane_gap,
                                row_gap,
                                side_gap,
                                sink_gap,
                            )
                            group_x += placed['width'] + max(2, lane_gap + 2)

                        if len(state) == len(self.nodes) and self._is_state_legal(state, env, gap=0):
                            candidates.append(self._fit_state_to_map(state, env))
        return candidates

    def _production_lane_groups(self) -> List[Dict]:
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for edge in self.edges:
            incoming[edge['dst']].append(edge['src'])
            outgoing[edge['src']].append(edge['dst'])

        target_sinks = [
            nid for nid, building in self.nodes.items()
            if any(mat in self.target_outputs_dict for mat in building.output_materials)
        ]
        sinks = target_sinks or [nid for nid in self.nodes if not outgoing[nid]]
        if not sinks:
            return []

        depths = self._node_depths()
        used = set()
        groups = []
        ordered_sinks = sorted(sinks, key=lambda nid: (-depths.get(nid, 0), nid))
        if len(ordered_sinks) > 1:
            merged_lanes = []
            side_groups = []
            for sink in ordered_sinks:
                lanes, side_nodes = self._lanes_for_sink(sink, incoming, used, depths)
                if not lanes and side_nodes:
                    lanes.append([side_nodes.pop(0)])
                merged_lanes.extend(lanes)
                side_groups.append(side_nodes)
                used.add(sink)
            groups.append({
                'sinks': ordered_sinks,
                'lanes': merged_lanes,
                'sides': [nid for side_group in side_groups for nid in side_group],
                'side_groups': side_groups,
            })
        else:
            for sink in ordered_sinks:
                lanes, side_nodes = self._lanes_for_sink(sink, incoming, used, depths)
                if not lanes and side_nodes:
                    lanes.append([side_nodes.pop(0)])

                if lanes or side_nodes or sink not in used:
                    groups.append({'sink': sink, 'sinks': [sink], 'lanes': lanes, 'sides': side_nodes})
                    used.add(sink)

        leftovers = [nid for nid in sorted(self.nodes) if nid not in used]
        for nid in leftovers:
            groups.append({'sink': nid, 'sinks': [nid], 'lanes': [], 'sides': []})
        return groups

    def _lanes_for_sink(self, sink: int, incoming: Dict[int, List[int]], used: set, depths: Dict[int, int]):
        lanes = []
        side_nodes = []
        for src in sorted(incoming.get(sink, []), key=lambda nid: (-depths.get(nid, 0), nid)):
            chain = self._primary_chain_to_node(src, incoming, used)
            if len(chain) > 1:
                lanes.append(chain)
                used.update(chain)
            elif chain:
                side_nodes.extend(chain)
                used.update(chain)
        return lanes, side_nodes

    def _primary_chain_to_node(self, nid: int, incoming: Dict[int, List[int]], used: set) -> List[int]:
        if nid in used:
            return []
        preds = [p for p in incoming.get(nid, []) if p not in used]
        if not preds:
            return [nid]

        depths = self._node_depths()
        primary = max(preds, key=lambda p: (depths.get(p, 0), -p))
        chain = self._primary_chain_to_node(primary, incoming, used)
        return chain + [nid]

    def _place_lane_group(
        self,
        group: Dict,
        state: Dict,
        group_x: int,
        base_y: int,
        lane_gap: int,
        row_gap: int,
        side_gap: int,
        sink_gap: int,
    ) -> Dict[str, int]:
        sinks = group['sinks'] if 'sinks' in group else [group['sink']]
        sink = sinks[0]
        lanes = group['lanes'] or []
        sides = group['sides'] or []
        sink_sizes = [self._real_size({'size': self.nodes[nid].size, 'dir': Direction.UP}) for nid in sinks]
        sink_block_w = sum(w for w, _ in sink_sizes) + max(0, len(sink_sizes) - 1) * lane_gap
        sink_h = max((h for _, h in sink_sizes), default=0)

        lane_widths = [max(self.nodes[nid].size[0] for nid in lane) for lane in lanes]
        lane_heights = [
            sum(self.nodes[nid].size[1] for nid in lane) + max(0, len(lane) - 1) * row_gap
            for lane in lanes
        ]
        lane_block_w = sum(lane_widths) + max(0, len(lane_widths) - 1) * lane_gap
        lane_block_h = max(lane_heights, default=0)
        center_block_w = max(lane_block_w, sink_block_w)

        if group.get('side_groups'):
            left_sides = []
            right_sides = []
            for idx, side_group in enumerate(group['side_groups']):
                (left_sides if idx % 2 == 0 else right_sides).extend(side_group)
        else:
            side_nodes = list(sides)
            left_sides = side_nodes[::2]
            right_sides = side_nodes[1::2]
        left_w = max((self.nodes[nid].size[0] for nid in left_sides), default=0)
        right_w = max((self.nodes[nid].size[0] for nid in right_sides), default=0)
        left_block_w = left_w + side_gap if left_sides else 0
        right_block_w = right_w + side_gap if right_sides else 0

        center_x = group_x + left_block_w
        lane_x = center_x + max(0, (center_block_w - lane_block_w) // 2)
        x = lane_x
        for lane, lane_w, lane_h in zip(lanes, lane_widths, lane_heights):
            y = base_y + max(0, lane_block_h - lane_h)
            for nid in lane:
                w, h = self.nodes[nid].size
                state[nid] = {'x': x + max(0, (lane_w - w) // 2), 'y': y, 'dir': Direction.UP, 'size': self.nodes[nid].size}
                y += h + row_gap
            x += lane_w + lane_gap

        sink_y = base_y + lane_block_h + sink_gap
        sink_x = center_x + max(0, (center_block_w - sink_block_w) // 2)
        for nid, (w, _h) in zip(sinks, sink_sizes):
            state[nid] = {'x': sink_x, 'y': sink_y, 'dir': Direction.UP, 'size': self.nodes[nid].size}
            sink_x += w + lane_gap

        for side_list, side_x in ((left_sides, group_x), (right_sides, center_x + center_block_w + side_gap)):
            if not side_list:
                continue
            y = base_y
            for nid in side_list:
                state[nid] = {'x': side_x, 'y': y, 'dir': Direction.UP, 'size': self.nodes[nid].size}
                y += self.nodes[nid].size[1] + row_gap

        width = left_block_w + center_block_w + right_block_w
        height = max(lane_block_h + sink_gap + sink_h, max((s['y'] + self._real_size(s)[1] - base_y for s in state.values()), default=0))
        return {'width': width, 'height': height}

    def _initial_sp_state(self) -> Dict:
        ordered = sorted(self.modules, key=lambda m: (m.preferred_layer, m.module_id))
        seq_pos = [module.module_id for module in ordered]
        seq_neg = []
        for layer in sorted({module.preferred_layer for module in self.modules}):
            same_layer = [m.module_id for m in ordered if m.preferred_layer == layer]
            seq_neg = same_layer + seq_neg
        return {
            'seq_pos': seq_pos,
            'seq_neg': seq_neg,
            'variants': {module.module_id: self._default_variant_index(module) for module in self.modules},
        }

    def _default_variant_index(self, module: LayoutModule) -> int:
        best_idx = 0
        best_score = float('inf')
        for idx, variant in enumerate(module.variants):
            score = variant.width * variant.height + abs(variant.width - variant.height) * 2
            if len(module.node_ids) > 2 and variant.width >= variant.height:
                score -= 8
            if score < best_score:
                best_idx = idx
                best_score = score
        return best_idx

    def _randomize_sp_state(self, base_state: Dict, restart: int) -> Dict:
        state = {
            'seq_pos': list(base_state['seq_pos']),
            'seq_neg': list(base_state['seq_neg']),
            'variants': dict(base_state['variants']),
        }
        if restart == 0:
            return state

        swaps = 1 + restart % max(1, len(self.modules))
        for _ in range(swaps):
            target = state['seq_pos'] if random.random() < 0.5 else state['seq_neg']
            if len(target) >= 2:
                i, j = random.sample(range(len(target)), 2)
                target[i], target[j] = target[j], target[i]

        for module in self.modules:
            if random.random() < 0.35:
                state['variants'][module.module_id] = random.randrange(len(module.variants))
        return state

    def _anneal_sequence_pair(self, env: GridMap, initial_state: Dict) -> Dict:
        current = self._copy_sp_state(initial_state)
        current_cost = self._cheap_sp_cost(current, env)
        best = self._copy_sp_state(current)
        best_cost = current_cost

        temp = self.sp_initial_temp
        while temp > self.sp_min_temp:
            for _ in range(self.sp_iters_per_temp):
                candidate = self._mutate_sp_state(current)
                candidate_cost = self._cheap_sp_cost(candidate, env)
                delta = candidate_cost - current_cost
                if delta < 0 or math.exp(-delta / temp) > random.random():
                    current = candidate
                    current_cost = candidate_cost
                    if current_cost < best_cost:
                        best = self._copy_sp_state(current)
                        best_cost = current_cost
            temp *= self.sp_cooling_rate
        return best

    def _mutate_sp_state(self, state: Dict) -> Dict:
        mutated = self._copy_sp_state(state)
        action = random.random()
        if action < 0.35:
            self._swap_random(mutated['seq_pos'])
        elif action < 0.70:
            self._swap_random(mutated['seq_neg'])
        elif action < 0.85:
            self._swap_random(mutated['seq_pos'])
            self._swap_random(mutated['seq_neg'])
        else:
            module = random.choice(self.modules)
            mutated['variants'][module.module_id] = random.randrange(len(module.variants))
        return mutated

    def _swap_random(self, seq: List[int]):
        if len(seq) < 2:
            return
        i, j = random.sample(range(len(seq)), 2)
        seq[i], seq[j] = seq[j], seq[i]

    def _cheap_sp_cost(self, sp_state: Dict, env: GridMap) -> float:
        building_state = self._sp_to_building_state(sp_state, env)
        return self._cheap_building_cost(building_state, env)

    def _cheap_building_cost(self, building_state: Dict, env: GridMap) -> float:
        min_x, min_y, max_x, max_y, occupied, area = self._bounding_metrics(building_state)
        cost = area * 18.0 + max(0, area - occupied) * 2.5

        depths = self._node_depths()
        for edge in self.edges:
            src = building_state[edge['src']]
            dst = building_state[edge['dst']]
            cost += (abs(src['x'] - dst['x']) + abs(src['y'] - dst['y'])) * 8.0
            if depths.get(edge['src'], 0) < depths.get(edge['dst'], 0) and src['y'] > dst['y']:
                cost += 800.0

        for nid, state in building_state.items():
            building = self.nodes[nid]
            if any(mat in self.available_inputs for mat in building.input_materials):
                cost += state['y'] * 20.0
            if any(mat in self.target_outputs_dict for mat in building.output_materials):
                cost += (env.height - state['y']) * 20.0

        if min_x < self.map_margin or min_y < self.map_margin or max_x > env.width - self.map_margin or max_y > env.height - self.map_margin:
            cost += 100000.0
        return cost

    def _sp_to_building_state(self, sp_state: Dict, env: GridMap) -> Dict:
        module_positions = self._pack_sequence_pair(sp_state)
        min_x = min((pos[0] for pos in module_positions.values()), default=0)
        min_y = min((pos[1] for pos in module_positions.values()), default=0)

        building_state = {}
        for module in self.modules:
            variant = module.variants[sp_state['variants'][module.module_id]]
            base_x, base_y = module_positions[module.module_id]
            base_x += self.map_margin - min_x
            base_y += self.map_margin - min_y
            for nid, (ox, oy, direction) in variant.offsets.items():
                building_state[nid] = {
                    'x': int(base_x + ox),
                    'y': int(base_y + oy),
                    'dir': direction,
                    'size': self.nodes[nid].size,
                }

        return self._fit_state_to_map(building_state, env)

    def _pack_sequence_pair(self, sp_state: Dict) -> Dict[int, Tuple[int, int]]:
        seq_pos = sp_state['seq_pos']
        seq_neg = sp_state['seq_neg']
        pos_index = {module_id: idx for idx, module_id in enumerate(seq_pos)}
        neg_index = {module_id: idx for idx, module_id in enumerate(seq_neg)}

        x_edges = defaultdict(list)
        y_edges = defaultdict(list)
        module_ids = list(seq_pos)

        for i in range(len(module_ids)):
            for j in range(i + 1, len(module_ids)):
                a, b = module_ids[i], module_ids[j]
                if pos_index[a] < pos_index[b] and neg_index[a] < neg_index[b]:
                    x_edges[b].append(a)
                elif pos_index[a] < pos_index[b] and neg_index[a] > neg_index[b]:
                    y_edges[b].append(a)
                elif pos_index[a] > pos_index[b] and neg_index[a] < neg_index[b]:
                    y_edges[a].append(b)
                else:
                    x_edges[a].append(b)

        x_pos = self._longest_positions(module_ids, x_edges, sp_state, axis='x')
        y_pos = self._longest_positions(module_ids, y_edges, sp_state, axis='y')
        return {module_id: (x_pos[module_id], y_pos[module_id]) for module_id in module_ids}

    def _longest_positions(self, module_ids: List[int], edges: Dict[int, List[int]], sp_state: Dict, axis: str) -> Dict[int, int]:
        positions = {module_id: 0 for module_id in module_ids}
        changed = True
        while changed:
            changed = False
            for dst, srcs in edges.items():
                for src in srcs:
                    src_variant = self.module_by_id[src].variants[sp_state['variants'][src]]
                    span = src_variant.width if axis == 'x' else src_variant.height
                    value = positions[src] + span + self.module_gap
                    if value > positions[dst]:
                        positions[dst] = value
                        changed = True
        return positions

    def _fit_state_to_map(self, state: Dict, env: GridMap) -> Dict:
        fitted = {k: v.copy() for k, v in state.items()}
        min_x, min_y, max_x, max_y, _, _ = self._bounding_metrics(fitted)
        dx = 0
        dy = 0
        if max_x > env.width - self.map_margin:
            dx = env.width - self.map_margin - max_x
        if min_x + dx < self.map_margin:
            dx += self.map_margin - (min_x + dx)
        if max_y > env.height - self.map_margin:
            dy = env.height - self.map_margin - max_y
        if min_y + dy < self.map_margin:
            dy += self.map_margin - (min_y + dy)
        for item in fitted.values():
            item['x'] += dx
            item['y'] += dy
        return fitted

    def _route_preserving_compact(self, state: Dict, env: GridMap) -> Dict:
        current = self._copy_building_state(state)
        failed, current_routes, current_area = self._trial_route_state(env, current)
        if failed:
            return current

        for _ in range(5):
            changed = False
            move_order = self._compact_move_order(current)
            for nid, axis, direction in move_order:
                while True:
                    trial = self._copy_building_state(current)
                    trial[nid][axis] += direction
                    if not self._is_state_legal(trial, env, gap=0):
                        break

                    t_failed, t_routes, t_area = self._trial_route_state(env, trial)
                    if t_failed:
                        break

                    improves_area = t_area < current_area
                    improves_route = t_area == current_area and t_routes < current_routes
                    if not improves_area and not improves_route:
                        break

                    current = trial
                    current_routes = t_routes
                    current_area = t_area
                    changed = True

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

    def _copy_building_state(self, state: Dict) -> Dict:
        return {nid: item.copy() for nid, item in state.items()}

    def _copy_sp_state(self, state: Dict) -> Dict:
        return {
            'seq_pos': list(state['seq_pos']),
            'seq_neg': list(state['seq_neg']),
            'variants': dict(state['variants']),
        }
