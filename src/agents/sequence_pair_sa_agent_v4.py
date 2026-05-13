import heapq
import random
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from agents.sequence_pair_sa_agent_v3 import SequencePairSaAgentV3
from entities.material import MaterialType
from entities.registry import get_building_instance
from entities.transport import Direction
from environment.grid_map import GridMap


class SequencePairSaAgentV4(SequencePairSaAgentV3):
    """
    V4 adds three search upgrades:
    - detailed beam/K-shortest routing with full rip-up reroute rounds;
    - GA search over production-cell order, variants, and building rotations;
    - budgeted LNS extreme compaction to avoid long stalls on larger targets.
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        super().__init__(target_outputs, available_inputs)
        self.ga_population = 26
        self.ga_generations = 14
        self.ga_elites = 6
        self.ga_route_top_k = 5
        self.beam_width = 220
        self.k_shortest = 3
        self.ripup_rounds = 5
        self.fast_route_rounds = 2
        self.lns_iterations = 70
        self.refine_eval_budget = 120
        self._trial_cache = {}
        self._eval_budget_left = None
        self._fast_routing_mode = False

    def optimize(self, env: GridMap):
        print("\n[SequencePairSaAgentV4] Starting GA + detailed routing + LNS layout...")
        self._calculate_ratios_and_instances()
        self._build_instance_graph()
        self._build_production_cells(env)
        self._configure_budget()

        self.node_positions = self._optimize_v4_layout(env)

        for nid, state in self.node_positions.items():
            building = self.nodes[nid]
            if not env.place_building(building, state['x'], state['y'], state['dir']):
                print(f"[Warning] Building {building.name} could not be placed at ({state['x']},{state['y']}), legalizing...")
                if not self._legalize_placement(env, building, state['x'], state['y'], state['dir'], nid):
                    print(f"[Error] Failed to legalize placement for {building.name}.")

        print("[SequencePairSaAgentV4] Routing selected layout with beam K-shortest rip-up reroute...")
        self._reset_routing_state()
        success = self._route_connections_negotiated(env, self.node_positions)
        if not success:
            failed = ", ".join(t['mat'].name for t in self.failed_routes)
            print(f"[SequencePairSaAgentV4] Routed with unresolved tasks: {failed}")
        print("[SequencePairSaAgentV4] Blueprint generation complete.")

    def _configure_budget(self):
        n = len(self.nodes)
        if n >= 24:
            self.ga_population = 22
            self.ga_generations = 10
            self.ga_route_top_k = 4
            self.refine_eval_budget = 72
            self.lns_iterations = 40
            self.rotation_passes = 1
            self.extreme_compact_passes = 3
        self._trial_cache = {}

    def _optimize_v4_layout(self, env: GridMap) -> Dict:
        self._fast_routing_mode = True
        seed_state = self._fast_seed_search(env)
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, seed_state)
        print(f"[SequencePairSaAgentV4] Fast seed: failed={failed}, route_cells={routes}, area={area}")

        ga_state = self._ga_layout_search(env, seed_state)
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, ga_state)
        print(f"[SequencePairSaAgentV4] GA selected: failed={failed}, route_cells={routes}, area={area}")

        self._fast_routing_mode = False
        self._eval_budget_left = self.refine_eval_budget
        rotated = self._budgeted_rotation_search(ga_state, env)
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, rotated)
        print(f"[SequencePairSaAgentV4] Budgeted rotation search: failed={failed}, route_cells={routes}, area={area}")
        if not failed:
            ga_state = rotated

        compacted = self._lns_extreme_compact(ga_state, env)
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, compacted)
        print(f"[SequencePairSaAgentV4] LNS extreme compact: failed={failed}, route_cells={routes}, area={area}")
        if not failed:
            ga_state = compacted

        if not self._final_route_replay_ok(env, ga_state):
            print("[SequencePairSaAgentV4] Final replay validation failed; running detailed safety fallback...")
            self._trial_cache.clear()
            self._fast_routing_mode = True
            fallback = super(SequencePairSaAgentV3, self)._optimize_btree_layout(env)
            self._fast_routing_mode = False
            if self._final_route_replay_ok(env, fallback):
                ga_state = fallback

        self._eval_budget_left = None
        self._reset_routing_state()
        return ga_state

    def _final_route_replay_ok(self, env: GridMap, state: Dict) -> bool:
        result = self._negotiate_paths(env, state, keep_paths=True)
        if result['failed'] == 0 and not result['failed_tasks']:
            return True
        was_fast = self._fast_routing_mode
        self._fast_routing_mode = True
        fallback = self._negotiate_paths(env, state, keep_paths=True)
        self._fast_routing_mode = was_fast
        return fallback['failed'] == 0 and not fallback['failed_tasks']

    def _route_connections_negotiated(self, env: GridMap, state: Dict) -> bool:
        result = self._negotiate_paths(env, state, keep_paths=True)
        if result['failed_tasks']:
            was_fast = self._fast_routing_mode
            self._fast_routing_mode = True
            fallback = self._negotiate_paths(env, state, keep_paths=True)
            self._fast_routing_mode = was_fast
            if fallback['failed'] < result['failed']:
                result = fallback

        self.failed_routes = []
        self._reset_routing_state()
        if result['failed_tasks']:
            self.failed_routes = list(result['failed_tasks'])
        for task, path in result['paths']:
            self._lay_path(env, path, task)
        return not self.failed_routes

    def _fast_seed_search(self, env: GridMap) -> Dict:
        seeds = self._cell_variant_seed_states(env)
        if not seeds:
            return {}

        best_state = seeds[0]
        best_score = (float('inf'), float('inf'), float('inf'), float('inf'))
        indices = self._seed_probe_indices(len(seeds))
        first_full = None

        for idx in indices:
            score = self._cached_trial_score(env, seeds[idx])
            if self._route_score_better(score, best_score):
                best_score = score
                best_state = seeds[idx]
                print(f"[SequencePairSaAgentV4] Seed probe {idx + 1}: failed={score[0]}, route_cells={score[1]}, area={score[2]}")
            if score[0] == 0 and first_full is None:
                first_full = idx

        if first_full is not None:
            lo = max(0, first_full - 10)
            hi = min(len(seeds), first_full + 11)
            for idx in range(lo, hi):
                score = self._cached_trial_score(env, seeds[idx])
                if self._route_score_better(score, best_score):
                    best_score = score
                    best_state = seeds[idx]
                    print(f"[SequencePairSaAgentV4] Seed refine {idx + 1}: failed={score[0]}, route_cells={score[1]}, area={score[2]}")

        if best_score[0] == 0:
            was_fast = self._fast_routing_mode
            fast_compacted = self._route_preserving_compact_v2(best_state, env)
            fast_compacted_score = self._trial_negotiated_route_state(env, fast_compacted)
            if fast_compacted_score[0] == 0 and self._route_score_better(fast_compacted_score, best_score):
                best_state = fast_compacted
                best_score = fast_compacted_score
            self._fast_routing_mode = False
            detailed_score = self._trial_negotiated_route_state(env, best_state)
            if detailed_score[0] == 0:
                compacted = self._route_preserving_compact_v2(best_state, env)
                compacted_score = self._trial_negotiated_route_state(env, compacted)
                if compacted_score[0] == 0 and self._route_score_better(compacted_score, detailed_score):
                    best_state = compacted
            else:
                repaired = self._detailed_seed_repair(env, seeds, first_full)
                if repaired is not None:
                    best_state = repaired
            self._fast_routing_mode = was_fast
        return best_state

    def _detailed_seed_repair(self, env: GridMap, seeds: List[Dict], center_idx: int):
        if center_idx is None:
            return None
        best_state = None
        best_score = (float('inf'), float('inf'), float('inf'), float('inf'))
        probe = list(range(max(0, center_idx - 12), min(len(seeds), center_idx + 18)))
        probe.extend(idx for idx in self._seed_probe_indices(len(seeds)) if idx not in probe)
        for idx in probe[:42]:
            score = self._trial_negotiated_route_state(env, seeds[idx])
            if score[0] == 0 and self._route_score_better(score, best_score):
                best_state = seeds[idx]
                best_score = score
                print(f"[SequencePairSaAgentV4] Detailed seed repair {idx + 1}: failed={score[0]}, route_cells={score[1]}, area={score[2]}")
        if best_state is None:
            return None
        compacted = self._route_preserving_compact_v2(best_state, env)
        compacted_score = self._trial_negotiated_route_state(env, compacted)
        if compacted_score[0] == 0 and self._route_score_better(compacted_score, best_score):
            return compacted
        return best_state

    def _seed_probe_indices(self, count: int) -> List[int]:
        anchors = [0, 1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 80, count - 1]
        anchors.extend(int((count - 1) * ratio) for ratio in (0.35, 0.50, 0.65, 0.80, 0.90))
        return sorted({idx for idx in anchors if 0 <= idx < count})

    def _ga_layout_search(self, env: GridMap, fallback_state: Dict) -> Dict:
        if not self.cells:
            return fallback_state
        population = self._initial_ga_population(fallback_state)
        best_state = fallback_state
        best_score = self._cached_trial_score(env, fallback_state)

        for generation in range(self.ga_generations):
            cheap_ranked = []
            for genome in population:
                state = self._genome_to_state(genome, env)
                if state is None:
                    continue
                cheap_ranked.append((self._cheap_ga_cost(state, env), genome, state))
            cheap_ranked.sort(key=lambda item: item[0])

            selected = self._select_ga_route_candidates(cheap_ranked)
            evaluated = []
            for _cheap, genome, state in selected:
                score = self._cached_trial_score(env, state)
                evaluated.append((score, genome, state))
                if self._route_score_better(score, best_score):
                    best_score = score
                    best_state = state
            evaluated.sort(key=lambda item: item[0])
            if evaluated:
                print(
                    f"[SequencePairSaAgentV4] GA gen {generation + 1}: "
                    f"failed={evaluated[0][0][0]}, route_cells={evaluated[0][0][1]}, area={evaluated[0][0][2]}"
                )

            parents = [item[1] for item in evaluated[:self.ga_elites]]
            if not parents:
                parents = [item[1] for item in cheap_ranked[:self.ga_elites]]
            if not parents:
                print(f"[SequencePairSaAgentV4] GA gen {generation + 1}: no legal genomes; keeping fallback layout")
                break
            population = self._next_ga_population(parents)

        return best_state

    def _select_ga_route_candidates(self, cheap_ranked):
        if not cheap_ranked:
            return []
        selected = list(cheap_ranked[:self.ga_route_top_k])
        if len(cheap_ranked) > self.ga_route_top_k:
            selected.extend(cheap_ranked[-2:])
        middle = cheap_ranked[self.ga_route_top_k:-2]
        if middle:
            selected.extend(random.sample(middle, min(2, len(middle))))
        seen = set()
        unique = []
        for item in selected:
            key = tuple(item[1]['order']), tuple(sorted(item[1]['variants'].items())), tuple(sorted((nid, d.name) for nid, d in item[1]['rotations'].items()))
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def _initial_ga_population(self, fallback_state: Dict) -> List[Dict]:
        cell_ids = [cell.cell_id for cell in sorted(self.cells, key=lambda c: (-c.depth, c.cell_id))]
        base_rotations = {nid: fallback_state[nid]['dir'] for nid in fallback_state}
        population = []
        for i in range(self.ga_population):
            order = list(cell_ids)
            if i:
                random.shuffle(order)
            variants = {}
            for cid in cell_ids:
                max_idx = len(self.cell_variants[cid]) - 1
                if i < self.ga_population // 2:
                    variants[cid] = int(max_idx * (i / max(1, self.ga_population // 2 - 1)))
                else:
                    variants[cid] = random.randrange(len(self.cell_variants[cid]))
            rotations = dict(base_rotations)
            if i:
                for nid in rotations:
                    if random.random() < 0.18:
                        rotations[nid] = random.choice([Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT])
            population.append({'order': order, 'variants': variants, 'rotations': rotations})
        return population

    def _next_ga_population(self, parents: List[Dict]) -> List[Dict]:
        next_population = [self._copy_genome(parent) for parent in parents[:self.ga_elites]]
        while len(next_population) < self.ga_population:
            if len(parents) >= 2:
                a, b = random.sample(parents, 2)
                child = self._crossover_genomes(a, b)
            else:
                child = self._copy_genome(parents[0])
            self._mutate_genome(child)
            next_population.append(child)
        return next_population

    def _copy_genome(self, genome: Dict) -> Dict:
        return {
            'order': list(genome['order']),
            'variants': dict(genome['variants']),
            'rotations': dict(genome['rotations']),
        }

    def _crossover_genomes(self, a: Dict, b: Dict) -> Dict:
        split = random.randrange(1, len(a['order']) + 1) if a['order'] else 0
        prefix = a['order'][:split]
        order = prefix + [cid for cid in b['order'] if cid not in prefix]
        variants = {cid: (a['variants'][cid] if random.random() < 0.5 else b['variants'][cid]) for cid in a['variants']}
        rotations = {nid: (a['rotations'][nid] if random.random() < 0.5 else b['rotations'][nid]) for nid in a['rotations']}
        return {'order': order, 'variants': variants, 'rotations': rotations}

    def _mutate_genome(self, genome: Dict):
        if len(genome['order']) >= 2 and random.random() < 0.35:
            i, j = random.sample(range(len(genome['order'])), 2)
            genome['order'][i], genome['order'][j] = genome['order'][j], genome['order'][i]
        if random.random() < 0.55:
            cid = random.choice(list(genome['variants']))
            genome['variants'][cid] = random.randrange(len(self.cell_variants[cid]))
        for nid in list(genome['rotations']):
            if random.random() < 0.08:
                genome['rotations'][nid] = random.choice([Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT])

    def _genome_to_state(self, genome: Dict, env: GridMap) -> Optional[Dict]:
        state = {}
        x = self.map_margin
        for cid in genome['order']:
            variant = self.cell_variants[cid][genome['variants'][cid]]
            for nid, (ox, oy, direction) in variant.offsets.items():
                state[nid] = {
                    'x': x + ox,
                    'y': self.map_margin + oy,
                    'dir': genome['rotations'].get(nid, direction),
                    'size': self.nodes[nid].size,
                }
            x += variant.width + self.cell_gap
        if len(state) != len(self.nodes):
            return None
        state = self._recenter_rotated_state(state, env)
        if not self._is_state_legal(state, env, gap=0):
            return None
        if not self._port_supply_ok(state, env):
            return None
        return self._fit_state_to_map_v2(state, env)

    def _recenter_rotated_state(self, state: Dict, env: GridMap) -> Dict:
        adjusted = {nid: item.copy() for nid, item in state.items()}
        for nid, item in list(adjusted.items()):
            adjusted[nid] = self._rotated_state(item, item['dir'], env)
        return adjusted

    def _cheap_ga_cost(self, state: Dict, env: GridMap) -> float:
        cost = self._layout_feedback_cost(state, env)
        required_inputs, required_outputs = self._required_port_counts()
        for nid in self.nodes:
            cost += max(0, required_inputs[nid] - len(self._get_all_ports_of_node(nid, True))) * 5000
            cost += max(0, required_outputs[nid] - len(self._get_all_ports_of_node(nid, False))) * 5000
        return cost

    def _cached_trial_score(self, env: GridMap, state: Dict):
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, state)
        return failed, routes, area, congestion

    def _state_key(self, state: Dict):
        return tuple(sorted((nid, item['x'], item['y'], item['dir'].name) for nid, item in state.items()))

    def _trial_negotiated_route_state(self, env: GridMap, state: Dict) -> Tuple[int, int, int, int]:
        key = (self._fast_routing_mode, self._state_key(state))
        cached = self._trial_cache.get(key)
        if cached is not None:
            return cached
        result = self._negotiate_paths(env, state, keep_paths=False)
        _, _, _, _, _, area = self._bounding_metrics(state)
        score = (result['failed'], result['route_cells'], area, result['congestion'])
        if len(self._trial_cache) < 800:
            self._trial_cache[key] = score
        return score

    def _route_score_better(self, candidate, current) -> bool:
        return (candidate[0], candidate[2] + candidate[1] * 0.12 + candidate[3] * 0.08, candidate[1]) < (
            current[0], current[2] + current[1] * 0.12 + current[3] * 0.08, current[1]
        )

    def _budgeted_rotation_search(self, state: Dict, env: GridMap) -> Dict:
        current = {nid: item.copy() for nid, item in state.items()}
        best_score = self._full_route_score(current, env)
        if best_score[0]:
            return current
        directions = [Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT]
        for nid in self._rotation_order():
            if self._budget_exhausted():
                break
            original = current[nid]['dir']
            local_best = None
            for direction in directions:
                if direction == original or self._budget_exhausted():
                    continue
                trial = {k: v.copy() for k, v in current.items()}
                trial[nid] = self._rotated_state(trial[nid], direction, env)
                if not self._is_state_legal(trial, env, gap=0) or not self._port_supply_ok(trial, env):
                    continue
                score = self._budgeted_full_score(trial, env)
                if self._is_better_extreme_score(score, best_score):
                    local_best = (score, trial)
            if local_best:
                best_score, current = local_best
        return current

    def _lns_extreme_compact(self, state: Dict, env: GridMap) -> Dict:
        current = {nid: item.copy() for nid, item in state.items()}
        current_score = self._full_route_score(current, env)
        best_state = {nid: item.copy() for nid, item in current.items()}
        best_score = current_score
        if current_score[0]:
            return current

        moves = self._lns_moves(current)
        for _ in range(self.lns_iterations):
            if self._budget_exhausted():
                break
            nid, axis, direction, distance = random.choice(moves)
            trial = {k: v.copy() for k, v in current.items()}
            trial[nid][axis] += direction * distance
            if not self._is_state_legal(trial, env, gap=0) or not self._port_supply_ok(trial, env):
                continue
            score = self._budgeted_full_score(trial, env)
            accept = self._is_better_extreme_score(score, current_score)
            plateau = self._is_plateau_compaction_step(score, current_score) and random.random() < 0.35
            if accept or plateau:
                current, current_score = trial, score
                moves = self._lns_moves(current)
                if self._is_better_extreme_score(score, best_score):
                    best_state = {k: v.copy() for k, v in current.items()}
                    best_score = score
        return best_state

    def _lns_moves(self, state: Dict) -> List[Tuple[int, str, int, int]]:
        base = self._port_aware_move_order(state)
        moves = []
        for nid, axis, direction in base:
            for distance in (1, 2, 3):
                moves.append((nid, axis, direction, distance))
        return moves or [(nid, 'x', -1, 1) for nid in state]

    def _budgeted_full_score(self, state: Dict, env: GridMap):
        if self._eval_budget_left is not None:
            self._eval_budget_left -= 1
        return self._full_route_score(state, env)

    def _budget_exhausted(self) -> bool:
        return self._eval_budget_left is not None and self._eval_budget_left <= 0

    def _negotiate_paths(self, env: GridMap, state: Dict, keep_paths: bool) -> Dict:
        saved = self._save_routing_context()
        congestion = defaultdict(float)
        best = {'failed': float('inf'), 'route_cells': float('inf'), 'congestion': float('inf'), 'paths': [], 'failed_tasks': []}
        tasks = self._routing_tasks_for_state(state)
        rounds = self.fast_route_rounds if self._fast_routing_mode else self.ripup_rounds
        k_paths = 1 if self._fast_routing_mode else self.k_shortest

        for round_idx in range(rounds):
            trial_env = GridMap(env.width, env.height)
            self.node_positions = {k: v.copy() for k, v in state.items()}
            self._reset_routing_state()
            placement_failed = self._place_trial_buildings(trial_env)
            paths = []
            failed_tasks = []
            usage = defaultdict(int)
            path_costs = []

            if placement_failed == 0:
                routed_tasks = self._route_order_for_round(tasks, round_idx, best.get('failed_tasks', []))
                for task in routed_tasks:
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
                    path = self._k_shortest_beam_route(trial_env, starts, goals, forbidden, task, congestion, k_paths)
                    if path is None:
                        failed_tasks.append(task)
                        continue
                    paths.append((task, path))
                    p_cost = self._path_cost(path, task, congestion)
                    path_costs.append((p_cost, path))
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

            self._update_ripup_congestion(congestion, usage, path_costs, failed_tasks, state)

        self._restore_routing_context(saved)
        return best

    def _place_trial_buildings(self, trial_env: GridMap) -> int:
        placement_failed = 0
        for nid, s in self.node_positions.items():
            building = get_building_instance(self.nodes[nid].component_id)
            if not trial_env.place_building(building, s['x'], s['y'], s['dir']):
                placement_failed += 1
        return placement_failed

    def _route_order_for_round(self, tasks: List[Dict], round_idx: int, previous_failed: List[Dict]) -> List[Dict]:
        if round_idx == 0 or not previous_failed:
            return tasks
        failed_ids = {self._task_id(task) for task in previous_failed}
        return sorted(tasks, key=lambda task: (self._task_id(task) not in failed_ids, self._route_task_distance(task)))

    def _task_id(self, task: Dict):
        return task.get('src_type'), task.get('src'), task.get('dst_type'), task.get('dst'), task.get('mat')

    def _k_shortest_beam_route(
        self,
        env: GridMap,
        starts: List[Tuple[int, int]],
        goals: List[Tuple[int, int]],
        forbidden: Set[Tuple[int, int]],
        task: Dict,
        congestion: Dict[Tuple[int, int], float],
        k_paths: int,
    ) -> Optional[List[Tuple[int, int]]]:
        candidates = []
        avoid = defaultdict(float)
        for _ in range(k_paths):
            path = self._beam_a_star_route(env, starts, goals, forbidden, task, congestion, avoid)
            if path is None:
                break
            candidates.append(path)
            for cell in path:
                avoid[cell] += 6.0
        if not candidates:
            return None
        return min(candidates, key=lambda path: self._path_cost(path, task, congestion))

    def _beam_a_star_route(
        self,
        env: GridMap,
        starts: List[Tuple[int, int]],
        goals: List[Tuple[int, int]],
        forbidden: Set[Tuple[int, int]],
        task: Dict,
        congestion: Dict[Tuple[int, int], float],
        avoid: Dict[Tuple[int, int], float],
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
            if len(frontier) > self.beam_width * 4:
                frontier = heapq.nsmallest(self.beam_width, frontier)
                heapq.heapify(frontier)
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
                step_cost = (
                    1
                    + turn_penalty
                    + (10 if crossable else 0)
                    + congestion.get((nx, ny), 0)
                    + avoid.get((nx, ny), 0)
                    + self._route_corridor_penalty(task, nx, ny)
                )
                new_cost = g_score[current] + step_cost
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

    def _path_cost(self, path: List[Tuple[int, int]], task: Dict, congestion: Dict[Tuple[int, int], float]) -> float:
        turns = 0
        for i in range(2, len(path)):
            a, b, c = path[i - 2], path[i - 1], path[i]
            if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
                turns += 1
        return len(path) + turns * 1.5 + sum(congestion.get(p, 0) for p in path) + sum(self._route_corridor_penalty(task, *p) for p in path) * 0.25

    def _update_ripup_congestion(self, congestion, usage, path_costs, failed_tasks, state):
        for p, count in usage.items():
            congestion[p] += 0.1 + max(0, count - 1) * 9.0
        for _cost, path in sorted(path_costs, reverse=True)[:max(1, len(path_costs) // 5)]:
            for p in path:
                congestion[p] += 0.8
        for task in failed_tasks:
            for nid_key in ('src', 'dst'):
                if task.get(f'{nid_key}_type') == 'node':
                    sx, sy = self._state_center(state[task[nid_key]])
                    congestion[(int(sx), int(sy))] += 24.0
