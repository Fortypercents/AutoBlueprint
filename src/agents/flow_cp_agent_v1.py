import math
import random
from collections import defaultdict, deque
from typing import Dict, List, Tuple

from agents.sequence_pair_ga_agent_v4 import SequencePairGaAgentV4
from agents.sequence_pair_sa_agent_v2 import CellVariant, ProductionCell
from agents.fdp_sa_agent_v2 import FdpSaAgentV2
from entities.material import MaterialType
from entities.registry import get_building_instance
from entities.transport import Direction
from environment.grid_map import GridMap

try:
    from ortools.sat.python import cp_model
except Exception:
    cp_model = None


class FlowCpAgentV1(SequencePairGaAgentV4):
    """
    Min-cost-flow graph assignment + CP-style production-cell packing.

    This starts a separate algorithm series from sequence_pair_sa_agent_v*.  It
    keeps the mature detailed router from v4, but replaces two earlier choices:
    provider->consumer edges are rebuilt with min-cost flow, and each production
    cell gets bounded exact local compaction before global packing.
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        super().__init__(target_outputs, available_inputs)
        self.cp_variant_limit = 96
        self.cp_refine_limit = 24
        self.cp_local_window = 2
        self.cp_solver_time = 0.35
        self.ga_population = 18
        self.ga_generations = 9
        self.ga_route_top_k = 3
        self.ga_elites = 4
        self.refine_eval_budget = 90
        self.lns_iterations = 58
        self._wide_channel_mode = False
        self._wide_channel_refine = False

    def _configure_budget(self):
        super()._configure_budget()
        self.ga_population = min(self.ga_population, 18)
        self.ga_generations = min(self.ga_generations, 9)
        self.ga_route_top_k = min(self.ga_route_top_k, 3)
        self.ga_elites = min(self.ga_elites, 4)
        self.refine_eval_budget = min(self.refine_eval_budget, 90)
        self.lns_iterations = min(self.lns_iterations, 58)

    def optimize(self, env: GridMap):
        print("\n[FlowCpAgentV1] Starting min-cost-flow + CP-cell layout...")
        self._calculate_ratios_and_instances()
        self._build_instance_graph()
        self._build_production_cells(env)
        self._configure_budget()

        if len(self.nodes) >= 24:
            self.node_positions = self._optimize_large_flow_cp_layout(env)
        else:
            self.node_positions = self._optimize_v4_layout(env)
            self.node_positions = self._ensure_feasible_layout(env, self.node_positions)

        for nid, state in self.node_positions.items():
            building = self.nodes[nid]
            if not env.place_building(building, state['x'], state['y'], state['dir']):
                print(f"[Warning] Building {building.name} could not be placed at ({state['x']},{state['y']}), legalizing...")
                if not self._legalize_placement(env, building, state['x'], state['y'], state['dir'], nid):
                    print(f"[Error] Failed to legalize placement for {building.name}.")

        print("[FlowCpAgentV1] Routing selected layout with detailed rip-up router...")
        self._reset_routing_state()
        success = self._route_connections_negotiated(env, self.node_positions)
        if not success:
            failed = ", ".join(t['mat'].name for t in self.failed_routes)
            print(f"[FlowCpAgentV1] Routed with unresolved tasks: {failed}")
        print("[FlowCpAgentV1] Blueprint generation complete.")

    def _optimize_large_flow_cp_layout(self, env: GridMap) -> Dict:
        direct_refined_wide = len(self.nodes) >= 24
        if direct_refined_wide:
            print("[FlowCpAgentV1] Large flow detected; using refined wide-channel search directly...")
            failed = 999
        else:
            self._fast_routing_mode = True
            state = self._fast_seed_search(env)
            failed, routes, area, _ = self._trial_negotiated_route_state(env, state)
            print(f"[FlowCpAgentV1] Large-flow CP probe: failed={failed}, route_cells={routes}, area={area}")
            self._fast_routing_mode = False
            if self._final_route_replay_ok(env, state):
                return state

            print("[FlowCpAgentV1] Large-flow probe congested; switching to wide-channel variants early...")
        use_refined_wide = direct_refined_wide or failed >= 4
        saved_cp_solver_time = self.cp_solver_time
        if use_refined_wide:
            self.cp_solver_time = min(self.cp_solver_time, 0.06)
        self._wide_channel_mode = True
        self._wide_channel_refine = use_refined_wide
        self._trial_cache.clear()
        self._build_production_cells(env)
        self._fast_routing_mode = True
        state = self._fast_seed_search(env)
        failed, routes, area, _ = self._trial_negotiated_route_state(env, state)
        mode = "Refined wide-channel" if use_refined_wide else "Wide-channel"
        print(f"[FlowCpAgentV1] {mode} probe: failed={failed}, route_cells={routes}, area={area}")
        self._fast_routing_mode = False

        if not use_refined_wide and not self._final_route_replay_ok(env, state):
            print("[FlowCpAgentV1] Light wide-channel probe still congested; enabling refined wide-channel cells...")
            self._wide_channel_refine = True
            self._trial_cache.clear()
            self._build_production_cells(env)
            self._fast_routing_mode = True
            state = self._fast_seed_search(env)
            failed, routes, area, _ = self._trial_negotiated_route_state(env, state)
            print(f"[FlowCpAgentV1] Refined wide-channel probe: failed={failed}, route_cells={routes}, area={area}")
            self._fast_routing_mode = False

        if not self._final_route_replay_ok(env, state):
            print("[FlowCpAgentV1] Wide-channel flow graph still congested; trying round-robin graph fallback...")
            self.edges = []
            FdpSaAgentV2._build_instance_graph(self)
            self._trial_cache.clear()
            self._build_production_cells(env)
            self._fast_routing_mode = True
            state = self._fast_seed_search(env)
            self._fast_routing_mode = False

        self._eval_budget_left = min(self.refine_eval_budget, 45)
        refined = self._budgeted_rotation_search(state, env)
        if self._final_route_replay_ok(env, refined):
            state = refined
        compacted = self._lns_extreme_compact(state, env)
        if self._final_route_replay_ok(env, compacted):
            state = compacted
        self._eval_budget_left = None
        self.cp_solver_time = saved_cp_solver_time
        self._wide_channel_mode = False
        self._wide_channel_refine = False
        self._reset_routing_state()
        return state

    def _ensure_feasible_layout(self, env: GridMap, state: Dict) -> Dict:
        if self._final_route_replay_ok(env, state):
            return state

        print("[FlowCpAgentV1] Min-cost-flow CP layout not fully routable; trying wide-channel CP variants...")
        saved_edges = list(self.edges)
        self._wide_channel_mode = True
        self._wide_channel_refine = True
        self._trial_cache.clear()
        self._build_production_cells(env)
        candidate = self._optimize_v4_layout(env)
        if self._final_route_replay_ok(env, candidate):
            self._wide_channel_mode = False
            self._wide_channel_refine = False
            return candidate

        print("[FlowCpAgentV1] Wide-channel flow layout still congested; trying round-robin graph fallback...")
        self._wide_channel_mode = True
        self.edges = []
        FdpSaAgentV2._build_instance_graph(self)
        self._trial_cache.clear()
        self._build_production_cells(env)
        fallback = self._optimize_v4_layout(env)
        if self._final_route_replay_ok(env, fallback):
            self._wide_channel_mode = False
            self._wide_channel_refine = False
            return fallback

        self.edges = saved_edges
        self._wide_channel_mode = False
        self._wide_channel_refine = False
        return state

    def _build_instance_graph(self):
        self.nodes = {i: b for i, b in enumerate(self.required_buildings)}
        providers = defaultdict(list)
        consumers = defaultdict(list)

        for nid, building in self.nodes.items():
            for mat in building.output_materials:
                providers[mat].append(nid)
            for mat in building.input_materials:
                consumers[mat].append(nid)

        self.edges = []
        for mat in sorted(set(providers).intersection(consumers), key=lambda item: item.name):
            if mat in self.available_inputs:
                continue
            p_list = sorted(providers[mat], key=lambda nid: (self.nodes[nid].component_id, nid))
            c_list = sorted(consumers[mat], key=lambda nid: (self.nodes[nid].component_id, nid))
            for src, dst in self._min_cost_material_assignment(mat, p_list, c_list):
                self.edges.append({'src': src, 'dst': dst, 'mat': mat})

    def _min_cost_material_assignment(self, mat: MaterialType, providers: List[int], consumers: List[int]) -> List[Tuple[int, int]]:
        if not providers or not consumers:
            return []
        total_units = max(len(providers), len(consumers))
        provider_caps = self._balanced_caps(len(providers), total_units)
        consumer_demands = self._balanced_caps(len(consumers), total_units)

        graph = _MinCostFlow()
        source = "source"
        sink = "sink"
        for idx, nid in enumerate(providers):
            graph.add_edge(source, ("p", nid), provider_caps[idx], 0)
        for idx, nid in enumerate(consumers):
            graph.add_edge(("c", nid), sink, consumer_demands[idx], 0)

        for p_idx, src in enumerate(providers):
            for c_idx, dst in enumerate(consumers):
                cost = self._assignment_cost(src, dst, p_idx, c_idx, len(providers), len(consumers))
                graph.add_edge(("p", src), ("c", dst), 1, cost)

        graph.min_cost_flow(source, sink, total_units)
        assignments = []
        for src in providers:
            for edge in graph.used_edges_from(("p", src)):
                if isinstance(edge.to_node, tuple) and edge.to_node[0] == "c":
                    assignments.append((src, edge.to_node[1]))
        assignments.sort(key=lambda item: (item[1], item[0]))
        return assignments

    def _balanced_caps(self, count: int, total: int) -> List[int]:
        base = total // count
        extra = total % count
        return [base + (1 if idx < extra else 0) for idx in range(count)]

    def _assignment_cost(self, src: int, dst: int, p_idx: int, c_idx: int, p_count: int, c_count: int) -> int:
        p_pos = p_idx / max(1, p_count - 1)
        c_pos = c_idx / max(1, c_count - 1)
        component_bias = abs(self.nodes[src].component_id - self.nodes[dst].component_id) // 10
        return int(abs(p_pos - c_pos) * 1000) + component_bias

    def _make_cell_variants(self, cell: ProductionCell, env: GridMap) -> List[CellVariant]:
        raw_variants = super()._make_cell_variants(cell, env)
        if self._wide_channel_mode:
            raw_variants = self._wide_channel_variants(cell, env) + raw_variants
        variants = []
        seen = set()
        refine_limit = self.cp_refine_limit if (not self._wide_channel_mode or self._wide_channel_refine) else 0
        for idx, variant in enumerate(raw_variants[: self.cp_variant_limit]):
            candidates = [variant]
            if idx < refine_limit:
                candidates.insert(0, self._cp_refine_cell_variant(cell, variant, env))
            for candidate in candidates:
                key = (candidate.width, candidate.height, tuple(sorted(candidate.offsets.items())))
                if key in seen:
                    continue
                seen.add(key)
                variants.append(candidate)
        variants.sort(key=lambda item: (item.width * item.height, item.width + item.height))
        return variants[: self.cp_variant_limit]

    def _wide_channel_variants(self, cell: ProductionCell, env: GridMap) -> List[CellVariant]:
        variants = []
        seen = set()
        for lane_gap in (2, 3, 4):
            for row_gap in (2, 3, 4):
                for side_gap in (3, 4, 5, 6):
                    for sink_gap in (2, 3, 4):
                        local = self._place_cell_array(cell, lane_gap, row_gap, side_gap, sink_gap)
                        if set(local) != set(cell.node_ids):
                            continue
                        local = self._normalize_local_state(local)
                        _, _, max_x, max_y, _, _ = self._bounding_metrics(local)
                        key = (max_x, max_y, tuple(sorted((nid, s['x'], s['y']) for nid, s in local.items())))
                        if key in seen:
                            continue
                        seen.add(key)
                        variants.append(CellVariant(max_x, max_y, {nid: (s['x'], s['y'], s['dir']) for nid, s in local.items()}))
        variants.sort(key=lambda item: (item.width * item.height, item.width + item.height))
        return variants[:64]

    def _cp_refine_cell_variant(self, cell: ProductionCell, variant: CellVariant, env: GridMap) -> CellVariant:
        state = {
            nid: {'x': ox, 'y': oy, 'dir': direction, 'size': self.nodes[nid].size}
            for nid, (ox, oy, direction) in variant.offsets.items()
        }
        state = self._normalize_local_state(state)
        if cp_model is not None and len(cell.node_ids) <= 24:
            solved = self._cp_sat_refine_cell_variant(cell, state, variant, env)
            if solved is not None:
                return solved
        return self._bounded_refine_cell_variant(cell, state, env)

    def _bounded_refine_cell_variant(self, cell: ProductionCell, state: Dict, env: GridMap) -> CellVariant:
        best = {nid: item.copy() for nid, item in state.items()}
        best_area = self._bounding_metrics(best)[-1]

        for _ in range(2):
            improved = False
            for nid in self._cell_node_order(cell):
                candidates = self._local_position_candidates(best, nid, env)
                for trial_state in candidates:
                    if not self._local_cell_legal(cell, trial_state, env):
                        continue
                    area = self._bounding_metrics(trial_state)[-1]
                    if area < best_area or (area == best_area and self._local_wire_cost(trial_state) < self._local_wire_cost(best)):
                        best = trial_state
                        best_area = area
                        improved = True
                        break
            if not improved:
                break

        best = self._normalize_local_state(best)
        _, _, max_x, max_y, _, _ = self._bounding_metrics(best)
        return CellVariant(max_x, max_y, {nid: (s['x'], s['y'], s['dir']) for nid, s in best.items()})

    def _cp_sat_refine_cell_variant(self, cell: ProductionCell, state: Dict, variant: CellVariant, env: GridMap):
        profiles = self._cp_direction_profiles(cell, state)
        best_variant = None
        best_score = (float('inf'), float('inf'))
        for directions in profiles:
            solved_state = self._solve_cp_profile(cell, state, directions, variant, env)
            if solved_state is None:
                continue
            solved_state = self._normalize_local_state(solved_state)
            if not self._local_cell_legal(cell, solved_state, env):
                continue
            _, _, max_x, max_y, _, area = self._bounding_metrics(solved_state)
            wire = self._local_wire_cost(solved_state)
            if (area, wire) < best_score:
                best_score = (area, wire)
                best_variant = CellVariant(max_x, max_y, {nid: (s['x'], s['y'], s['dir']) for nid, s in solved_state.items()})
        return best_variant

    def _cp_direction_profiles(self, cell: ProductionCell, state: Dict) -> List[Dict[int, Direction]]:
        original = {nid: state[nid]['dir'] for nid in cell.node_ids}
        profiles = [original, {nid: Direction.UP for nid in cell.node_ids}]
        for direction in (Direction.DOWN, Direction.LEFT, Direction.RIGHT):
            profiles.append({nid: direction for nid in cell.node_ids})

        sink_profile = dict(original)
        for sink in cell.sinks:
            sink_profile[sink] = Direction.UP
        profiles.append(sink_profile)

        unique = []
        seen = set()
        for profile in profiles:
            key = tuple(sorted((nid, direction.name) for nid, direction in profile.items()))
            if key not in seen:
                seen.add(key)
                unique.append(profile)
        return unique[:5]

    def _solve_cp_profile(self, cell: ProductionCell, state: Dict, directions: Dict[int, Direction], variant: CellVariant, env: GridMap):
        model = cp_model.CpModel()
        node_ids = list(cell.node_ids)
        max_w = max([variant.width + 4] + [max(self.nodes[nid].size) + 2 for nid in node_ids])
        max_h = max([variant.height + 4] + [max(self.nodes[nid].size) + 2 for nid in node_ids])

        xs, ys, widths, heights = {}, {}, {}, {}
        x_intervals, y_intervals = [], []
        for nid in node_ids:
            temp = {'size': self.nodes[nid].size, 'dir': directions[nid]}
            w, h = self._real_size(temp)
            widths[nid], heights[nid] = w, h
            xs[nid] = model.NewIntVar(0, max_w - w, f"x_{nid}")
            ys[nid] = model.NewIntVar(0, max_h - h, f"y_{nid}")
            x_intervals.append(model.NewFixedSizeIntervalVar(xs[nid], w, f"xi_{nid}"))
            y_intervals.append(model.NewFixedSizeIntervalVar(ys[nid], h, f"yi_{nid}"))

        model.AddNoOverlap2D(x_intervals, y_intervals)

        bx = model.NewIntVar(1, max_w, "bbox_w")
        by = model.NewIntVar(1, max_h, "bbox_h")
        for nid in node_ids:
            model.Add(xs[nid] + widths[nid] <= bx)
            model.Add(ys[nid] + heights[nid] <= by)

        area = model.NewIntVar(1, max_w * max_h, "bbox_area")
        model.AddMultiplicationEquality(area, [bx, by])

        wire_terms = []
        down_terms = []
        for edge in self.edges:
            if edge['src'] not in xs or edge['dst'] not in xs:
                continue
            src, dst = edge['src'], edge['dst']
            cx_src = model.NewIntVar(0, max_w * 2, f"cxs_{src}_{dst}")
            cy_src = model.NewIntVar(0, max_h * 2, f"cys_{src}_{dst}")
            cx_dst = model.NewIntVar(0, max_w * 2, f"cxd_{src}_{dst}")
            cy_dst = model.NewIntVar(0, max_h * 2, f"cyd_{src}_{dst}")
            model.Add(cx_src == xs[src] * 2 + widths[src])
            model.Add(cy_src == ys[src] * 2 + heights[src])
            model.Add(cx_dst == xs[dst] * 2 + widths[dst])
            model.Add(cy_dst == ys[dst] * 2 + heights[dst])

            dx = model.NewIntVar(0, max_w * 2, f"dx_{src}_{dst}")
            dy = model.NewIntVar(0, max_h * 2, f"dy_{src}_{dst}")
            model.AddAbsEquality(dx, cx_src - cx_dst)
            model.AddAbsEquality(dy, cy_src - cy_dst)
            wire_terms.extend([dx, dy])

            down = model.NewIntVar(0, max_h, f"down_{src}_{dst}")
            model.AddMaxEquality(down, [ys[src] - ys[dst], 0])
            down_terms.append(down)

        model.Minimize(area * 1000 + bx * 20 + by * 20 + sum(wire_terms) * 2 + sum(down_terms) * 80)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.cp_solver_time
        solver.parameters.num_search_workers = 8
        solver.parameters.random_seed = 16
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        solved = {}
        for nid in node_ids:
            solved[nid] = {
                'x': solver.Value(xs[nid]),
                'y': solver.Value(ys[nid]),
                'dir': directions[nid],
                'size': self.nodes[nid].size,
            }
        return solved

    def _cell_node_order(self, cell: ProductionCell) -> List[int]:
        degree = defaultdict(int)
        for edge in self.edges:
            if edge['src'] in cell.node_ids and edge['dst'] in cell.node_ids:
                degree[edge['src']] += 1
                degree[edge['dst']] += 1
        return sorted(cell.node_ids, key=lambda nid: (-degree[nid], nid))

    def _local_position_candidates(self, state: Dict, nid: int, env: GridMap) -> List[Dict]:
        item = state[nid]
        candidates = []
        directions = [item['dir'], Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT]
        for direction in directions:
            rotated = self._rotated_state(item, direction, GridMap(max(env.width, 30), max(env.height, 30)))
            for dx in range(-self.cp_local_window, self.cp_local_window + 1):
                for dy in range(-self.cp_local_window, self.cp_local_window + 1):
                    trial = {k: v.copy() for k, v in state.items()}
                    trial[nid] = rotated.copy()
                    trial[nid]['x'] = max(0, rotated['x'] + dx)
                    trial[nid]['y'] = max(0, rotated['y'] + dy)
                    trial = self._normalize_local_state(trial)
                    candidates.append(trial)
        candidates.sort(key=lambda s: (self._bounding_metrics(s)[-1], self._local_wire_cost(s)))
        return candidates[:36]

    def _local_cell_legal(self, cell: ProductionCell, state: Dict, env: GridMap) -> bool:
        local_env = GridMap(max(env.width, 40), max(env.height, 40))
        shifted = {nid: item.copy() for nid, item in state.items()}
        for item in shifted.values():
            item['x'] += self.map_margin
            item['y'] += self.map_margin
        if not self._is_state_legal(shifted, local_env, gap=0):
            return False
        return self._local_port_supply_ok(cell, shifted, local_env)

    def _local_port_supply_ok(self, cell: ProductionCell, state: Dict, env: GridMap) -> bool:
        saved = self.node_positions
        self.node_positions = state
        try:
            for nid, item in state.items():
                building = get_building_instance(self.nodes[nid].component_id)
                if not env.place_building(building, item['x'], item['y'], item['dir']):
                    return False
            req_in, req_out = self._required_port_counts()
            for nid in cell.node_ids:
                input_ports = [p for p in self._get_all_ports_of_node(nid, True) if env._get_cell(*p) is None]
                output_ports = [p for p in self._get_all_ports_of_node(nid, False) if env._get_cell(*p) is None]
                if len(input_ports) < req_in[nid] or len(output_ports) < req_out[nid]:
                    return False
            return True
        finally:
            self.node_positions = saved

    def _local_wire_cost(self, state: Dict) -> float:
        cost = 0.0
        for edge in self.edges:
            if edge['src'] in state and edge['dst'] in state:
                sx, sy = self._state_center(state[edge['src']])
                dx, dy = self._state_center(state[edge['dst']])
                cost += abs(sx - dx) + abs(sy - dy)
        return cost


class _FlowEdge:
    def __init__(self, to_node, rev, cap, cost):
        self.to_node = to_node
        self.rev = rev
        self.cap = cap
        self.cost = cost
        self.original_cap = cap


class _MinCostFlow:
    def __init__(self):
        self.graph = defaultdict(list)

    def add_edge(self, from_node, to_node, cap: int, cost: int):
        forward = _FlowEdge(to_node, len(self.graph[to_node]), cap, cost)
        backward = _FlowEdge(from_node, len(self.graph[from_node]), 0, -cost)
        self.graph[from_node].append(forward)
        self.graph[to_node].append(backward)

    def min_cost_flow(self, source, sink, amount: int):
        flow = 0
        while flow < amount:
            dist, parent = self._shortest_path(source)
            if sink not in dist:
                break
            add = amount - flow
            node = sink
            while node != source:
                prev, edge_idx = parent[node]
                add = min(add, self.graph[prev][edge_idx].cap)
                node = prev
            node = sink
            while node != source:
                prev, edge_idx = parent[node]
                edge = self.graph[prev][edge_idx]
                edge.cap -= add
                self.graph[node][edge.rev].cap += add
                node = prev
            flow += add
        return flow

    def _shortest_path(self, source):
        dist = {source: 0}
        parent = {}
        queue = deque([source])
        in_queue = {source}
        while queue:
            node = queue.popleft()
            in_queue.discard(node)
            for idx, edge in enumerate(self.graph[node]):
                if edge.cap <= 0:
                    continue
                nd = dist[node] + edge.cost
                if edge.to_node not in dist or nd < dist[edge.to_node]:
                    dist[edge.to_node] = nd
                    parent[edge.to_node] = (node, idx)
                    if edge.to_node not in in_queue:
                        queue.append(edge.to_node)
                        in_queue.add(edge.to_node)
        return dist, parent

    def used_edges_from(self, node):
        for edge in self.graph[node]:
            if edge.original_cap > edge.cap:
                yield edge
