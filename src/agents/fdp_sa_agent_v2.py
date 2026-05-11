import heapq
import math
import random
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from agents.utils import get_recipe_catalog
from entities.material import MaterialType
from entities.registry import get_building_instance, get_transport_instance
from entities.transport import Direction
from environment.grid_map import GridMap


class FdpSaAgentV2:
    """
    Compact routing-aware FDP + simulated annealing agent.

    The optimizer searches several initial layouts, evaluates each one by doing
    a temporary routing pass, and keeps the best fully routed candidate before
    committing buildings and belts to the real environment.
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        self.target_outputs_dict = target_outputs
        self.available_inputs = available_inputs

        self.nodes = {}
        self.edges = []
        self.required_buildings = []
        self.node_positions = {}

        self.used_ports: Set[Tuple[int, int]] = set()
        self.generated_inputs = defaultdict(list)
        self.generated_outputs = defaultdict(list)
        self.generated_outputs = defaultdict(list)
        self.failed_routes = []
        self._last_trial_failed = []

        self.map_margin = 2
        self.high_temp_gap = 3
        self.low_temp_gap = 2
        self.initial_temp = 1200.0
        self.min_temp = 1.0
        self.cooling_rate = 0.95
        self.iters_per_temp = 110
        self.layout_restarts = 10
        self.port_clearance_penalty = 2500.0

        self._sa_progress = 0.0
        self.padding = self.high_temp_gap

    def optimize(self, env: GridMap):
        print("\n[FdpSaAgentV2] Starting compact routing-aware FDP+SA layout...")

        self._calculate_ratios_and_instances()
        self._build_instance_graph()

        print("[FdpSaAgentV2] Selecting layout from routed multi-start candidates...")
        self.node_positions = self._select_layout_candidate(env)

        for nid, state in self.node_positions.items():
            building = self.nodes[nid]
            if not env.place_building(building, state['x'], state['y'], state['dir']):
                print(f"[Warning] Building {building.name} could not be placed at ({state['x']},{state['y']}), legalizing...")
                if not self._legalize_placement(env, building, state['x'], state['y'], state['dir'], nid):
                    print(f"[Error] Failed to legalize placement for {building.name}.")

        print("[FdpSaAgentV2] Routing selected layout...")
        self._reset_routing_state()
        success = self._route_connections(env)
        if not success:
            failed = ", ".join(t['mat'].name for t in self.failed_routes)
            print(f"[FdpSaAgentV2] Routed with unresolved tasks: {failed}")
        print("[FdpSaAgentV2] Blueprint generation complete.")

    def _calculate_ratios_and_instances(self):
        demand_queue = dict(self.target_outputs_dict)
        recipes = get_recipe_catalog()

        while demand_queue:
            mat, amount = demand_queue.popitem()
            if mat in self.available_inputs:
                continue

            producer_cid = next((cid for cid, recipe in recipes.items() if mat in recipe['out']), None)
            if producer_cid is None:
                continue

            recipe = recipes[producer_cid]
            prod_rate = recipe['out'][mat] * recipe['speed']
            building_count = math.ceil(amount / prod_rate)
            for _ in range(building_count):
                self.required_buildings.append(get_building_instance(producer_cid))

            for in_mat, in_amount in recipe['in'].items():
                demand_queue[in_mat] = demand_queue.get(in_mat, 0) + (
                    in_amount * recipe['speed'] * (amount / prod_rate)
                )

    def _build_instance_graph(self):
        self.nodes = {i: b for i, b in enumerate(self.required_buildings)}
        providers = defaultdict(list)
        consumers = defaultdict(list)

        for nid, building in self.nodes.items():
            for mat in building.output_materials:
                providers[mat].append(nid)
            for mat in building.input_materials:
                consumers[mat].append(nid)

        for mat in set(providers).intersection(consumers):
            if mat in self.available_inputs:
                continue

            p_list = providers[mat]
            c_list = consumers[mat]
            for i, p_nid in enumerate(p_list):
                self.edges.append({'src': p_nid, 'dst': c_list[i % len(c_list)], 'mat': mat})
            for i, c_nid in enumerate(c_list):
                if not any(e['dst'] == c_nid and e['mat'] == mat for e in self.edges):
                    self.edges.append({'src': p_list[i % len(p_list)], 'dst': c_nid, 'mat': mat})

    def _select_layout_candidate(self, env: GridMap) -> Dict:
        best_state = None
        best_score = (float('inf'), float('inf'), float('inf'), float('inf'))

        seeds = [self._run_layered_grid_placement(env)]
        for _ in range(max(1, self.layout_restarts - 1)):
            seeds.append(self._run_force_directed_placement(env))

        for idx, seed_state in enumerate(seeds, start=1):
            candidate = self._run_simulated_annealing(env, seed_state)
            candidate = self._compact_state(candidate, env)
            failed_count, route_cells, area = self._trial_route_state(env, candidate)
            eval_cost = self._evaluate_state(candidate, env)
            score = (failed_count, area + route_cells * 0.15, route_cells, eval_cost)
            print(f"[FdpSaAgentV2] Candidate {idx}: failed={failed_count}, route_cells={route_cells}, area={area}")
            if score < best_score:
                best_score = score
                best_state = {k: v.copy() for k, v in candidate.items()}

            if failed_count:
                for distance in (1, 2):
                    repaired = self._expand_state(candidate, env, distance)
                    repaired_failed, repaired_routes, repaired_area = self._trial_route_state(env, repaired)
                    repaired_cost = self._evaluate_state(repaired, env)
                    repaired_score = (repaired_failed, repaired_area + repaired_routes * 0.15, repaired_routes, repaired_cost)
                    print(
                        f"[FdpSaAgentV2] Candidate {idx}.{distance}: "
                        f"failed={repaired_failed}, route_cells={repaired_routes}, area={repaired_area}"
                    )
                    if repaired_score < best_score:
                        best_score = repaired_score
                        best_state = {k: v.copy() for k, v in repaired.items()}

                failed_tasks = list(self._last_trial_failed)
                for distance in (1, 2, 3):
                    repaired = self._repair_failed_endpoints(candidate, env, failed_tasks, distance)
                    repaired_failed, repaired_routes, repaired_area = self._trial_route_state(env, repaired)
                    repaired_cost = self._evaluate_state(repaired, env)
                    repaired_score = (repaired_failed, repaired_area + repaired_routes * 0.15, repaired_routes, repaired_cost)
                    print(
                        f"[FdpSaAgentV2] Candidate {idx}r{distance}: "
                        f"failed={repaired_failed}, route_cells={repaired_routes}, area={repaired_area}"
                    )
                    if repaired_score < best_score:
                        best_score = repaired_score
                        best_state = {k: v.copy() for k, v in repaired.items()}

        self._reset_routing_state()
        return best_state

    def _repair_failed_endpoints(self, state: Dict, env: GridMap, failed_tasks: List[Dict], distance: int) -> Dict:
        repaired = {k: v.copy() for k, v in state.items()}
        for task in failed_tasks:
            movable = []
            if task.get('src_type') == 'node':
                movable.append(task['src'])
            if task.get('dst_type') == 'node':
                movable.append(task['dst'])

            if len(movable) == 2:
                a, b = movable
                ax, ay = self._state_center(repaired[a])
                bx, by = self._state_center(repaired[b])
                dx = -1 if ax < bx else 1
                dy = -1 if ay < by else 1
                moves = [(a, dx, dy), (b, -dx, -dy)]
            else:
                moves = []
                for nid in movable:
                    sx, sy = self._state_center(repaired[nid])
                    moves.append((nid, -1 if sx < env.width / 2 else 1, -1 if sy < env.height / 2 else 1))

            for nid, sx, sy in moves:
                w, h = self._real_size(repaired[nid])
                for axis, sign in [('x', sx), ('y', sy)]:
                    trial = {k: v.copy() for k, v in repaired.items()}
                    trial[nid][axis] = max(
                        self.map_margin,
                        min((env.width if axis == 'x' else env.height) - (w if axis == 'x' else h) - self.map_margin,
                            trial[nid][axis] + sign * distance),
                    )
                    if self._is_state_legal(trial, env, gap=self.low_temp_gap):
                        repaired = trial
        return repaired

    def _state_center(self, state: Dict) -> Tuple[float, float]:
        w, h = self._real_size(state)
        return state['x'] + w / 2, state['y'] + h / 2

    def _expand_state(self, state: Dict, env: GridMap, distance: int) -> Dict:
        expanded = {k: v.copy() for k, v in state.items()}
        min_x, min_y, max_x, max_y, _, _ = self._bounding_metrics(expanded)
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2

        ordered = sorted(
            expanded,
            key=lambda nid: abs(expanded[nid]['x'] - cx) + abs(expanded[nid]['y'] - cy),
            reverse=True,
        )
        for nid in ordered:
            w, h = self._real_size(expanded[nid])
            sx = -1 if expanded[nid]['x'] + w / 2 < cx else 1
            sy = -1 if expanded[nid]['y'] + h / 2 < cy else 1
            trial = {k: v.copy() for k, v in expanded.items()}
            trial[nid]['x'] = max(self.map_margin, min(env.width - w - self.map_margin, trial[nid]['x'] + sx * distance))
            trial[nid]['y'] = max(self.map_margin, min(env.height - h - self.map_margin, trial[nid]['y'] + sy * distance))
            if self._is_state_legal(trial, env, gap=self.low_temp_gap):
                expanded = trial
        return expanded

    def _run_layered_grid_placement(self, env: GridMap) -> Dict[int, Dict]:
        depths = self._node_depths()
        layers = defaultdict(list)
        for nid, depth in depths.items():
            layers[depth].append(nid)

        max_depth = max(layers.keys(), default=0)
        state = {}
        for depth in range(max_depth + 1):
            layer = sorted(layers[depth], key=lambda nid: (self.nodes[nid].component_id, nid))
            total_width = sum(self.nodes[nid].size[0] for nid in layer)
            total_width += max(0, len(layer) - 1) * self.high_temp_gap
            x = max(self.map_margin, (env.width - total_width) // 2)
            y = int(env.height * (depth + 1) / (max_depth + 2))

            for nid in layer:
                direction = Direction.DOWN if depth < max_depth else Direction.UP
                w, h = self._real_size(nid, direction)
                x = min(max(self.map_margin, x), max(self.map_margin, env.width - w - self.map_margin))
                yy = min(max(self.map_margin, y), max(self.map_margin, env.height - h - self.map_margin))
                state[nid] = {'x': x, 'y': yy, 'dir': direction, 'size': self.nodes[nid].size}
                x += w + self.high_temp_gap
        return state

    def _run_force_directed_placement(self, env: GridMap) -> Dict[int, Dict]:
        depths = self._node_depths()
        max_depth = max(depths.values(), default=0)
        pos = {}

        for nid in self.nodes:
            layer = depths.get(nid, 0)
            pos[nid] = [
                env.width / 2 + random.uniform(-6, 6),
                env.height * (layer + 1) / (max_depth + 2) + random.uniform(-3, 3),
            ]

        velocities = {nid: [0.0, 0.0] for nid in self.nodes}
        for _ in range(70):
            forces = {nid: [0.0, 0.0] for nid in self.nodes}
            nids = list(self.nodes)

            for i in range(len(nids)):
                for j in range(i + 1, len(nids)):
                    n1, n2 = nids[i], nids[j]
                    dx, dy = pos[n1][0] - pos[n2][0], pos[n1][1] - pos[n2][1]
                    dist = max(0.1, math.hypot(dx, dy))
                    force = 80.0 / (dist * dist)
                    forces[n1][0] += (dx / dist) * force
                    forces[n1][1] += (dy / dist) * force
                    forces[n2][0] -= (dx / dist) * force
                    forces[n2][1] -= (dy / dist) * force

            for edge in self.edges:
                n1, n2 = edge['src'], edge['dst']
                dx, dy = pos[n2][0] - pos[n1][0], pos[n2][1] - pos[n1][1]
                dist = max(0.1, math.hypot(dx, dy))
                force = 2.0 * dist
                forces[n1][0] += (dx / dist) * force
                forces[n1][1] += (dy / dist) * force
                forces[n2][0] -= (dx / dist) * force
                forces[n2][1] -= (dy / dist) * force

            for nid in self.nodes:
                layer = depths.get(nid, 0)
                target_y = env.height * (layer + 1) / (max_depth + 2)
                forces[nid][0] += (env.width / 2 - pos[nid][0]) * 0.25
                forces[nid][1] += (target_y - pos[nid][1]) * 0.9

            for nid in self.nodes:
                velocities[nid][0] = (velocities[nid][0] + forces[nid][0]) * 0.78
                velocities[nid][1] = (velocities[nid][1] + forces[nid][1]) * 0.78
                pos[nid][0] += velocities[nid][0]
                pos[nid][1] += velocities[nid][1]

        state = {}
        dirs = [Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT]
        for nid in self.nodes:
            direction = dirs[depths.get(nid, 0) % len(dirs)]
            w, h = self._real_size(nid, direction)
            state[nid] = {
                'x': max(self.map_margin, min(env.width - w - self.map_margin, int(pos[nid][0]))),
                'y': max(self.map_margin, min(env.height - h - self.map_margin, int(pos[nid][1]))),
                'dir': direction,
                'size': self.nodes[nid].size,
            }
        return state

    def _run_simulated_annealing(self, env: GridMap, initial_state: Dict) -> Dict:
        current = {k: v.copy() for k, v in initial_state.items()}
        current_cost = self._evaluate_state(current, env)
        best = {k: v.copy() for k, v in current.items()}
        best_cost = current_cost

        temp = self.initial_temp
        total_steps = max(1, int(math.log(self.min_temp / self.initial_temp, self.cooling_rate)))
        step = 0

        while temp > self.min_temp:
            self._sa_progress = min(1.0, step / total_steps)
            self.padding = self._current_gap()
            for _ in range(self.iters_per_temp):
                candidate = self._mutate_state(current, env)
                candidate_cost = self._evaluate_state(candidate, env)
                delta = candidate_cost - current_cost
                if delta < 0 or math.exp(-delta / temp) > random.random():
                    current = candidate
                    current_cost = candidate_cost
                    if current_cost < best_cost:
                        best = {k: v.copy() for k, v in current.items()}
                        best_cost = current_cost
            temp *= self.cooling_rate
            step += 1

        self._sa_progress = 1.0
        self.padding = self.low_temp_gap
        return best

    def _mutate_state(self, state: Dict, env: GridMap) -> Dict:
        new_state = {k: v.copy() for k, v in state.items()}
        nid = random.choice(list(new_state))
        w, h = self._real_size(new_state[nid])

        action = random.random()
        if action < 0.34:
            dx, dy = random.randint(-2, 2), random.randint(-2, 2)
            new_state[nid]['x'] = max(self.map_margin, min(env.width - w - self.map_margin, new_state[nid]['x'] + dx))
            new_state[nid]['y'] = max(self.map_margin, min(env.height - h - self.map_margin, new_state[nid]['y'] + dy))
        elif action < 0.52:
            min_x, min_y, max_x, max_y, _, _ = self._bounding_metrics(new_state)
            cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
            sx = 1 if new_state[nid]['x'] < cx else -1
            sy = 1 if new_state[nid]['y'] < cy else -1
            if random.random() < 0.5:
                new_state[nid]['x'] = max(self.map_margin, min(env.width - w - self.map_margin, new_state[nid]['x'] + sx))
            else:
                new_state[nid]['y'] = max(self.map_margin, min(env.height - h - self.map_margin, new_state[nid]['y'] + sy))
        elif action < 0.68:
            axis = random.choice(['x', 'y'])
            direction = random.choice([-1, 1])
            for mid in self._edge_band_nodes(new_state, axis, direction):
                mw, mh = self._real_size(new_state[mid])
                if axis == 'x':
                    new_state[mid]['x'] = max(self.map_margin, min(env.width - mw - self.map_margin, new_state[mid]['x'] + direction))
                else:
                    new_state[mid]['y'] = max(self.map_margin, min(env.height - mh - self.map_margin, new_state[mid]['y'] + direction))
        elif action < 0.80:
            new_state[nid]['x'] = random.randint(self.map_margin, max(self.map_margin, env.width - w - self.map_margin))
            new_state[nid]['y'] = random.randint(self.map_margin, max(self.map_margin, env.height - h - self.map_margin))
        elif action < 0.92:
            new_state[nid]['dir'] = random.choice([d for d in Direction if d != new_state[nid]['dir']])
            w, h = self._real_size(new_state[nid])
            new_state[nid]['x'] = min(new_state[nid]['x'], max(self.map_margin, env.width - w - self.map_margin))
            new_state[nid]['y'] = min(new_state[nid]['y'], max(self.map_margin, env.height - h - self.map_margin))
        else:
            nid2 = random.choice(list(new_state))
            new_state[nid]['x'], new_state[nid]['y'], new_state[nid2]['x'], new_state[nid2]['y'] = (
                new_state[nid2]['x'], new_state[nid2]['y'], new_state[nid]['x'], new_state[nid]['y']
            )
        return new_state

    def _evaluate_state(self, state: Dict, env: GridMap) -> float:
        cost = 0.0
        nids = list(state)
        gap = self._current_gap()
        min_x, min_y, max_x, max_y, occupied_area, bbox_area = self._bounding_metrics(state)
        bbox_w, bbox_h = max_x - min_x, max_y - min_y
        empty_area = max(0, bbox_area - occupied_area)
        area_weight = 2.0 + 18.0 * self._sa_progress

        cost += bbox_area * area_weight
        cost += empty_area * (0.8 + 4.0 * self._sa_progress)
        cost += abs(bbox_w - bbox_h) * 6.0

        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        for nid in nids:
            s = state[nid]
            w, h = self._real_size(s)
            if not self._fits_bounds(s, env):
                cost += 100000.0
            cost += (abs(s['x'] + w / 2 - cx) + abs(s['y'] + h / 2 - cy)) * (1.0 + 3.0 * self._sa_progress)

        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                if self._rects_overlap(state[nids[i]], state[nids[j]], gap):
                    cost += 500000.0

        for edge in self.edges:
            out_ports = self._state_ports(edge['src'], state, is_input=False)
            in_ports = self._state_ports(edge['dst'], state, is_input=True)
            if out_ports and in_ports:
                cost += min(abs(px - qx) + abs(py - qy) for px, py in out_ports for qx, qy in in_ports) * 10.0

        for px, py in self._active_state_ports(state):
            if not env.is_in_bounds(px, py):
                cost += self.port_clearance_penalty
                continue
            for s in state.values():
                w, h = self._real_size(s)
                if s['x'] <= px < s['x'] + w and s['y'] <= py < s['y'] + h:
                    cost += self.port_clearance_penalty

        for nid, s in state.items():
            building = self.nodes[nid]
            if any(mat in self.available_inputs for mat in building.input_materials):
                cost += s['y'] * 12.0
            if any(mat in self.target_outputs_dict for mat in building.output_materials):
                cost += (env.height - s['y']) * 12.0
        return cost

    def _compact_state(self, state: Dict, env: GridMap) -> Dict:
        compacted = {k: v.copy() for k, v in state.items()}
        for _ in range(6):
            changed = False
            for axis, direction in [('x', -1), ('y', -1), ('x', 1), ('y', 1)]:
                ordered = sorted(compacted, key=lambda nid: compacted[nid][axis], reverse=direction > 0)
                for nid in ordered:
                    while True:
                        trial = {k: v.copy() for k, v in compacted.items()}
                        trial[nid][axis] += direction
                        if not self._is_state_legal(trial, env, gap=self.low_temp_gap):
                            break
                        if self._evaluate_state(trial, env) > self._evaluate_state(compacted, env):
                            break
                        compacted = trial
                        changed = True
            if not changed:
                break
        return compacted

    def _trial_route_state(self, env: GridMap, state: Dict) -> Tuple[int, int, int]:
        saved_positions = self.node_positions
        saved_used = set(self.used_ports)
        saved_inputs = defaultdict(list, {k: v[:] for k, v in self.generated_inputs.items()})
        saved_outputs = defaultdict(list, {k: v[:] for k, v in self.generated_outputs.items()})
        saved_failed = list(self.failed_routes)

        trial_env = GridMap(env.width, env.height)
        self.node_positions = {k: v.copy() for k, v in state.items()}
        self._reset_routing_state()

        placement_failed = 0
        for nid, s in self.node_positions.items():
            building = get_building_instance(self.nodes[nid].component_id)
            if not trial_env.place_building(building, s['x'], s['y'], s['dir']):
                placement_failed += 1

        if placement_failed == 0:
            self._route_connections(trial_env, verbose=False)

        self._last_trial_failed = list(self.failed_routes)
        failed_count = placement_failed + len(self.failed_routes)
        route_cells = len(trial_env.transports)
        _, _, _, _, _, area = self._bounding_metrics(state)

        self.node_positions = saved_positions
        self.used_ports = saved_used
        self.generated_inputs = saved_inputs
        self.generated_outputs = saved_outputs
        self.failed_routes = saved_failed
        return failed_count, route_cells, area

    def _route_connections(self, env: GridMap, verbose: bool = True) -> bool:
        self.failed_routes = []
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

        tasks.sort(key=lambda t: (t['src_type'] == 'ext_in' or t['dst_type'] == 'ext_out',
                                  self._route_task_distance(t)))

        for task in tasks:
            starts = self._task_starts(env, task)
            goals = self._task_goals(env, task)
            if not starts or not goals:
                self.failed_routes.append(task)
                continue

            protected_io = set()
            for ports in self.generated_inputs.values():
                protected_io.update(ports)
            for ports in self.generated_outputs.values():
                protected_io.update(ports)

            forbidden = self.all_building_ports | protected_io
            forbidden = forbidden - set(starts) - set(goals)
            path = self._a_star_route_multi(env, starts, goals, forbidden, task)
            if path is None:
                self.failed_routes.append(task)
                if verbose:
                    print(f"[Warning] Congestion: unable to route {task['mat'].name}")
                continue
            self._lay_path(env, path, task)

        return not self.failed_routes

    def _task_starts(self, env: GridMap, task: Dict) -> List[Tuple[int, int]]:
        if task['src_type'] == 'node':
            return self._get_available_ports(task['src'], is_input=False, env=env)
        return [p for p in self._edge_window_ports(env, task['dst'], top=True) if env._get_cell(*p) is None]

    def _task_goals(self, env: GridMap, task: Dict) -> List[Tuple[int, int]]:
        if task['dst_type'] == 'node':
            return self._get_available_ports(task['dst'], is_input=True, env=env)
        return [p for p in self._edge_window_ports(env, task['src'], top=False) if env._get_cell(*p) is None]

    def _lay_path(self, env: GridMap, path: List[Tuple[int, int]], task: Dict):
        start_p, end_p = path[0], path[-1]
        if task['src_type'] == 'node':
            self.used_ports.add(start_p)
        if task['dst_type'] == 'node':
            self.used_ports.add(end_p)
        if task['src_type'] == 'ext_in':
            self.generated_inputs[task['mat']].append(start_p)
        if task['dst_type'] == 'ext_out':
            self.generated_outputs[task['mat']].append(end_p)

        for i, (px, py) in enumerate(path):
            if i + 1 < len(path):
                out_dir = self._dir_between(path[i], path[i + 1])
            elif task['dst_type'] == 'node':
                out_dir = self._get_opposite_dir(self.node_positions[task['dst']]['dir'])
            else:
                out_dir = Direction.DOWN

            if i > 0:
                in_dir = self._dir_between(path[i], path[i - 1])
            elif task['src_type'] == 'node':
                in_dir = self.node_positions[task['src']]['dir']
            else:
                in_dir = Direction.UP

            cell = env._get_cell(px, py)
            if cell is None:
                comp = get_transport_instance(301)
                comp.in_dir = in_dir
                env.place_transport(comp, px, py, out_dir)
            elif type(cell).__name__ == "SystemBBelt":
                if self._should_upgrade_to_crosser(cell, in_dir, out_dir):
                    self._replace_belt_with_crosser(env, cell, px, py)
                elif (px, py) == start_p or (px, py) == end_p:
                    cell.in_dir = in_dir
                else:
                    self._replace_belt_with_crosser(env, cell, px, py)

    def _should_upgrade_to_crosser(self, cell, new_in: Direction, new_out: Direction) -> bool:
        old_out = getattr(cell, 'direction', Direction.RIGHT)
        old_in = getattr(cell, 'in_dir', self._get_opposite_dir(old_out))
        old_axis = self._straight_axis(old_in, old_out)
        new_axis = self._straight_axis(new_in, new_out)
        if old_axis is None or new_axis is None:
            return False
        return old_axis != new_axis

    def _straight_axis(self, in_dir: Direction, out_dir: Direction):
        if in_dir == Direction.LEFT and out_dir == Direction.RIGHT:
            return 'h'
        if in_dir == Direction.RIGHT and out_dir == Direction.LEFT:
            return 'h'
        if in_dir == Direction.UP and out_dir == Direction.DOWN:
            return 'v'
        if in_dir == Direction.DOWN and out_dir == Direction.UP:
            return 'v'
        return None

    def _replace_belt_with_crosser(self, env: GridMap, cell, x: int, y: int):
        original_dir = getattr(cell, 'direction', Direction.RIGHT)
        original_in = getattr(cell, 'in_dir', self._get_opposite_dir(original_dir))
        if cell in env.transports:
            env.transports.remove(cell)
        env.grid[y][x] = None
        comp = get_transport_instance(314)
        comp.in_dir = original_in
        env.place_transport(comp, x, y, original_dir)

    def _a_star_route_multi(
        self,
        env: GridMap,
        starts: List[Tuple[int, int]],
        goals: List[Tuple[int, int]],
        forbidden: Set[Tuple[int, int]],
        task: Dict = None,
    ) -> Optional[List[Tuple[int, int]]]:
        frontier = []
        came_from = {}
        g_score = {}

        for start in starts:
            h = min(abs(start[0] - g[0]) + abs(start[1] - g[1]) for g in goals)
            heapq.heappush(frontier, (h, start))
            came_from[start] = None
            g_score[start] = 0

        best_goal = None
        while frontier:
            current = heapq.heappop(frontier)[1]
            if current in goals:
                best_goal = current
                break

            x, y = current
            allowed_moves = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            cell_current = env._get_cell(x, y)
            on_crossable_belt = (
                cell_current is not None
                and type(cell_current).__name__ == "SystemBBelt"
                and current not in starts
                and current not in goals
            )
            if on_crossable_belt and came_from[current] is not None:
                px, py = came_from[current]
                allowed_moves = [(x - px, y - py)]

            for dx, dy in allowed_moves:
                nx, ny = x + dx, y + dy
                if not env.is_in_bounds(nx, ny) or (nx, ny) in forbidden:
                    continue

                cell_next = env._get_cell(nx, ny)
                crossable = False
                if cell_next is not None and (nx, ny) not in starts and (nx, ny) not in goals:
                    if type(cell_next).__name__ == "SystemBBelt":
                        move_dir = Direction.RIGHT if nx > x else Direction.LEFT if nx < x else Direction.DOWN if ny > y else Direction.UP
                        belt_out = getattr(cell_next, 'direction', Direction.RIGHT)
                        belt_in = getattr(cell_next, 'in_dir', self._get_opposite_dir(belt_out))
                        straight = (belt_out, belt_in) in [
                            (Direction.RIGHT, Direction.LEFT),
                            (Direction.LEFT, Direction.RIGHT),
                            (Direction.UP, Direction.DOWN),
                            (Direction.DOWN, Direction.UP),
                        ]
                        if straight:
                            crossable = (
                                move_dir in (Direction.UP, Direction.DOWN) and belt_out in (Direction.LEFT, Direction.RIGHT)
                            ) or (
                                move_dir in (Direction.LEFT, Direction.RIGHT) and belt_out in (Direction.UP, Direction.DOWN)
                            )
                    if not crossable:
                        continue

                turn_penalty = 0
                if came_from[current] is not None:
                    px, py = came_from[current]
                    if (x - px) != dx or (y - py) != dy:
                        turn_penalty = 2
                corridor_penalty = self._route_corridor_penalty(task, nx, ny) if task else 0
                new_cost = g_score[current] + 1 + turn_penalty + corridor_penalty + (15 if crossable else 0)

                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    h = min(abs(nx - gx) + abs(ny - gy) for gx, gy in goals)
                    heapq.heappush(frontier, (new_cost + h, (nx, ny)))
                    came_from[(nx, ny)] = current

        if best_goal is None:
            return None

        path = []
        current = best_goal
        while current is not None:
            path.append(current)
            current = came_from[current]
        return path[::-1]

    def _route_corridor_penalty(self, task: Dict, x: int, y: int) -> int:
        if task.get('src_type') != 'node' or task.get('dst_type') != 'node':
            return 0
        src = self.node_positions.get(task['src'])
        dst = self.node_positions.get(task['dst'])
        if not src or not dst:
            return 0

        sw, sh = self._real_size(src)
        dw, dh = self._real_size(dst)
        min_x = min(src['x'], dst['x']) - 2
        max_x = max(src['x'] + sw, dst['x'] + dw) + 2
        min_y = min(src['y'], dst['y']) - 1
        max_y = max(src['y'] + sh, dst['y'] + dh) + 2

        outside = 0
        if x < min_x:
            outside += min_x - x
        elif x > max_x:
            outside += x - max_x
        if y < min_y:
            outside += (min_y - y) * 2
        elif y > max_y:
            outside += y - max_y
        return outside * 3

    def _legalize_placement(self, env: GridMap, building, start_x, start_y, direction, nid) -> bool:
        max_radius = max(env.width, env.height)
        for radius in range(1, max_radius):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                    nx, ny = start_x + dx, start_y + dy
                    if env.is_in_bounds(nx, ny) and env.place_building(building, nx, ny, direction):
                        self.node_positions[nid]['x'] = nx
                        self.node_positions[nid]['y'] = ny
                        return True
        return False

    def _reset_routing_state(self):
        self.used_ports.clear()
        self.generated_inputs.clear()
        self.generated_outputs.clear()
        self.failed_routes = []

    def _node_depths(self) -> Dict[int, int]:
        incoming = defaultdict(list)
        for edge in self.edges:
            incoming[edge['dst']].append(edge['src'])

        depths = {nid: 0 for nid in self.nodes}
        changed = True
        while changed:
            changed = False
            for nid in self.nodes:
                if incoming[nid]:
                    depth = max(depths[p] + 1 for p in incoming[nid])
                    if depth > depths[nid]:
                        depths[nid] = depth
                        changed = True
        return depths

    def _real_size(self, node_or_state, direction: Direction = None) -> Tuple[int, int]:
        if isinstance(node_or_state, dict):
            w, h = node_or_state['size']
            direction = node_or_state['dir']
        else:
            w, h = self.nodes[node_or_state].size
        return (h, w) if direction in (Direction.LEFT, Direction.RIGHT) else (w, h)

    def _current_gap(self) -> int:
        return self.high_temp_gap if self._sa_progress < 0.35 else self.low_temp_gap

    def _fits_bounds(self, state: Dict, env: GridMap) -> bool:
        w, h = self._real_size(state)
        return (
            self.map_margin <= state['x']
            and self.map_margin <= state['y']
            and state['x'] + w <= env.width - self.map_margin
            and state['y'] + h <= env.height - self.map_margin
        )

    def _rects_overlap(self, a: Dict, b: Dict, gap: int) -> bool:
        aw, ah = self._real_size(a)
        bw, bh = self._real_size(b)
        return not (
            a['x'] + aw + gap <= b['x']
            or b['x'] + bw + gap <= a['x']
            or a['y'] + ah + gap <= b['y']
            or b['y'] + bh + gap <= a['y']
        )

    def _is_state_legal(self, state: Dict, env: GridMap, gap: int = 0) -> bool:
        nids = list(state)
        for nid in nids:
            if not self._fits_bounds(state[nid], env):
                return False
        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                if self._rects_overlap(state[nids[i]], state[nids[j]], gap):
                    return False
        return True

    def _bounding_metrics(self, state: Dict) -> Tuple[int, int, int, int, int, int]:
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = -float('inf'), -float('inf')
        occupied = 0
        for s in state.values():
            w, h = self._real_size(s)
            min_x = min(min_x, s['x'])
            min_y = min(min_y, s['y'])
            max_x = max(max_x, s['x'] + w)
            max_y = max(max_y, s['y'] + h)
            occupied += w * h
        return min_x, min_y, max_x, max_y, occupied, (max_x - min_x) * (max_y - min_y)

    def _edge_band_nodes(self, state: Dict, axis: str, direction: int) -> List[int]:
        min_x, min_y, max_x, max_y, _, _ = self._bounding_metrics(state)
        members = []
        for nid, s in state.items():
            w, h = self._real_size(s)
            if axis == 'x':
                edge = s['x'] if direction > 0 else s['x'] + w
                target = min_x if direction > 0 else max_x
            else:
                edge = s['y'] if direction > 0 else s['y'] + h
                target = min_y if direction > 0 else max_y
            if abs(edge - target) <= 2:
                members.append(nid)
        return members or [random.choice(list(state))]

    def _active_state_ports(self, state: Dict) -> List[Tuple[int, int]]:
        ports = []
        for edge in self.edges:
            ports.extend(self._state_ports(edge['src'], state, is_input=False))
            ports.extend(self._state_ports(edge['dst'], state, is_input=True))
        return ports

    def _state_ports(self, nid: int, state: Dict, is_input: bool) -> List[Tuple[int, int]]:
        s = state[nid]
        x, y, direction = s['x'], s['y'], s['dir']
        w, h = self._real_size(s)
        side = direction if is_input else self._get_opposite_dir(direction)

        if side == Direction.UP:
            return [(x + dx, y - 1) for dx in range(w)]
        if side == Direction.DOWN:
            return [(x + dx, y + h) for dx in range(w)]
        if side == Direction.LEFT:
            return [(x - 1, y + dy) for dy in range(h)]
        if side == Direction.RIGHT:
            return [(x + w, y + dy) for dy in range(h)]
        return []

    def _get_all_ports_of_node(self, nid: int, is_input: bool) -> List[Tuple[int, int]]:
        if nid not in self.node_positions:
            return []
        return self._state_ports(nid, self.node_positions, is_input)

    def _get_available_ports(self, nid: int, is_input: bool, env: GridMap = None) -> List[Tuple[int, int]]:
        ports = [p for p in self._get_all_ports_of_node(nid, is_input) if p not in self.used_ports]
        if env is None:
            return ports
        return [p for p in ports if env._get_cell(*p) is None]

    def _edge_window_ports(self, env: GridMap, nid: int, top: bool) -> List[Tuple[int, int]]:
        state = self.node_positions[nid]
        w, _ = self._real_size(state)
        center = state['x'] + w // 2
        radius = max(8, min(16, env.width // 3))
        y = 0 if top else env.height - 1
        return [(x, y) for x in range(max(0, center - radius), min(env.width, center + radius + 1))]

    def _route_task_distance(self, task: Dict) -> int:
        if task['src_type'] != 'node' or task['dst_type'] != 'node':
            return 0
        src = self.node_positions[task['src']]
        dst = self.node_positions[task['dst']]
        return abs(src['x'] - dst['x']) + abs(src['y'] - dst['y'])

    def _get_opposite_dir(self, direction: Direction) -> Direction:
        return {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }[direction]

    def _dir_between(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> Direction:
        if p2[0] > p1[0]:
            return Direction.RIGHT
        if p2[0] < p1[0]:
            return Direction.LEFT
        if p2[1] > p1[1]:
            return Direction.DOWN
        return Direction.UP
