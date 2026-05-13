from collections import defaultdict
from typing import Dict, List, Tuple

from agents.sequence_pair_sa_agent_v2 import SequencePairSaAgentV2
from entities.material import MaterialType
from entities.registry import get_building_instance
from entities.transport import Direction
from environment.grid_map import GridMap


class SequencePairSaAgentV3(SequencePairSaAgentV2):
    """
    V3 adds port-aware building rotation and extreme compaction on top of V2.

    The important distinction from simple rectangle packing is that adjacent
    buildings are allowed when their blocked sides are not needed; connection
    sides only need open belt cells where the actual graph needs ports.
    """

    def __init__(self, target_outputs: Dict[MaterialType, float], available_inputs: List[MaterialType]):
        super().__init__(target_outputs, available_inputs)
        self.rotation_passes = 2
        self.extreme_compact_passes = 6

    def optimize(self, env: GridMap):
        print("\n[SequencePairSaAgentV3] Starting rotation-aware cell + B*-tree layout...")
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

        print("[SequencePairSaAgentV3] Routing selected layout with negotiated congestion...")
        self._reset_routing_state()
        success = self._route_connections_negotiated(env, self.node_positions)
        if not success:
            failed = ", ".join(t['mat'].name for t in self.failed_routes)
            print(f"[SequencePairSaAgentV3] Routed with unresolved tasks: {failed}")
        print("[SequencePairSaAgentV3] Blueprint generation complete.")

    def _optimize_btree_layout(self, env: GridMap) -> Dict:
        state = super()._optimize_btree_layout(env)

        rotated = self._rotation_local_search(state, env)
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, rotated)
        print(f"[SequencePairSaAgentV3] Rotation search: failed={failed}, route_cells={routes}, area={area}")
        if not failed:
            state = rotated

        compacted = self._port_aware_extreme_compact(state, env)
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, compacted)
        print(f"[SequencePairSaAgentV3] Port-aware extreme compact: failed={failed}, route_cells={routes}, area={area}")
        if not failed:
            state = compacted

        self._reset_routing_state()
        return state

    def _rotation_local_search(self, state: Dict, env: GridMap) -> Dict:
        current = {nid: item.copy() for nid, item in state.items()}
        best_score = self._full_route_score(current, env)
        if best_score[0]:
            return current

        order = self._rotation_order()
        directions = [Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT]
        for _ in range(self.rotation_passes):
            changed = False
            for nid in order:
                original = current[nid]['dir']
                for direction in directions:
                    if direction == original:
                        continue
                    trial = {k: v.copy() for k, v in current.items()}
                    trial[nid] = self._rotated_state(trial[nid], direction, env)
                    if not self._is_state_legal(trial, env, gap=0):
                        continue
                    if not self._port_supply_ok(trial, env):
                        continue
                    score = self._full_route_score(trial, env)
                    if self._is_better_extreme_score(score, best_score):
                        current = trial
                        best_score = score
                        changed = True
                        break
            if not changed:
                break
        return current

    def _port_aware_extreme_compact(self, state: Dict, env: GridMap) -> Dict:
        current = {nid: item.copy() for nid, item in state.items()}
        current_score = self._full_route_score(current, env)
        if current_score[0]:
            return current
        best_state = {nid: item.copy() for nid, item in current.items()}
        best_score = current_score

        for _ in range(self.extreme_compact_passes):
            changed = False
            for nid, axis, direction in self._port_aware_move_order(current):
                while True:
                    trial = {k: v.copy() for k, v in current.items()}
                    trial[nid][axis] += direction
                    if not self._is_state_legal(trial, env, gap=0):
                        break
                    if not self._port_supply_ok(trial, env):
                        break
                    score = self._full_route_score(trial, env)
                    if self._is_better_extreme_score(score, current_score) or self._is_plateau_compaction_step(score, current_score):
                        current = trial
                        current_score = score
                        if self._is_better_extreme_score(score, best_score):
                            best_state = {k: v.copy() for k, v in current.items()}
                            best_score = score
                        changed = True
                    else:
                        break
            if not changed:
                break
        return best_state

    def _rotation_order(self) -> List[int]:
        degree = defaultdict(int)
        for edge in self.edges:
            degree[edge['src']] += 1
            degree[edge['dst']] += 1
        return sorted(self.nodes, key=lambda nid: (-degree[nid], nid))

    def _rotated_state(self, state: Dict, direction: Direction, env: GridMap) -> Dict:
        old_w, old_h = self._real_size(state)
        cx = state['x'] + old_w / 2
        cy = state['y'] + old_h / 2
        new_state = state.copy()
        new_state['dir'] = direction
        new_w, new_h = self._real_size(new_state)
        new_state['x'] = round(cx - new_w / 2)
        new_state['y'] = round(cy - new_h / 2)
        new_state['x'] = max(self.map_margin, min(env.width - new_w - self.map_margin, new_state['x']))
        new_state['y'] = max(self.map_margin, min(env.height - new_h - self.map_margin, new_state['y']))
        return new_state

    def _port_aware_move_order(self, state: Dict) -> List[Tuple[int, str, int]]:
        min_x, min_y, max_x, max_y, _, _ = self._bounding_metrics(state)
        degree = defaultdict(int)
        for edge in self.edges:
            degree[edge['src']] += 1
            degree[edge['dst']] += 1

        moves = []
        for nid, item in state.items():
            w, h = self._real_size(item)
            edge_priority = 0
            if item['x'] == min_x:
                moves.append((edge_priority, -degree[nid], nid, 'x', 1))
            if item['x'] + w == max_x:
                moves.append((edge_priority, -degree[nid], nid, 'x', -1))
            if item['y'] == min_y:
                moves.append((edge_priority, -degree[nid], nid, 'y', 1))
            if item['y'] + h == max_y:
                moves.append((edge_priority, -degree[nid], nid, 'y', -1))

        for nid in state:
            moves.extend([
                (1, -degree[nid], nid, 'x', -1),
                (1, -degree[nid], nid, 'x', 1),
                (1, -degree[nid], nid, 'y', -1),
                (1, -degree[nid], nid, 'y', 1),
            ])
        return [(nid, axis, direction) for _, _, nid, axis, direction in sorted(moves)]

    def _port_supply_ok(self, state: Dict, env: GridMap) -> bool:
        trial_env = GridMap(env.width, env.height)
        saved_positions = self.node_positions
        self.node_positions = state
        try:
            for nid, item in state.items():
                building = get_building_instance(self.nodes[nid].component_id)
                if not trial_env.place_building(building, item['x'], item['y'], item['dir']):
                    return False

            required_inputs, required_outputs = self._required_port_counts()
            for nid in self.nodes:
                input_ports = [p for p in self._get_all_ports_of_node(nid, True) if trial_env._get_cell(*p) is None]
                output_ports = [p for p in self._get_all_ports_of_node(nid, False) if trial_env._get_cell(*p) is None]
                if len(input_ports) < required_inputs[nid]:
                    return False
                if len(output_ports) < required_outputs[nid]:
                    return False
            return True
        finally:
            self.node_positions = saved_positions

    def _required_port_counts(self):
        required_inputs = defaultdict(int)
        required_outputs = defaultdict(int)
        for edge in self.edges:
            required_outputs[edge['src']] += 1
            required_inputs[edge['dst']] += 1
        for nid, building in self.nodes.items():
            for mat in building.input_materials:
                if mat in self.available_inputs:
                    required_inputs[nid] += 1
            for mat in building.output_materials:
                if mat in self.target_outputs_dict:
                    required_outputs[nid] += 1
        return required_inputs, required_outputs

    def _full_route_score(self, state: Dict, env: GridMap):
        failed, routes, area, congestion = self._trial_negotiated_route_state(env, state)
        cost = self._layout_feedback_cost(state, env)
        return failed, area, routes, congestion, cost

    def _is_better_extreme_score(self, candidate, current) -> bool:
        c_failed, c_area, c_routes, c_congestion, c_cost = candidate
        b_failed, b_area, b_routes, b_congestion, b_cost = current
        if c_failed != b_failed:
            return c_failed < b_failed
        if c_failed:
            return (c_area, c_routes + c_congestion, c_cost) < (b_area, b_routes + b_congestion, b_cost)
        if c_area != b_area:
            return c_area < b_area
        if c_routes + c_congestion != b_routes + b_congestion:
            return c_routes + c_congestion < b_routes + b_congestion
        return c_cost < b_cost

    def _is_plateau_compaction_step(self, candidate, current) -> bool:
        c_failed, c_area, c_routes, c_congestion, _c_cost = candidate
        b_failed, b_area, b_routes, b_congestion, _b_cost = current
        if c_failed or b_failed:
            return False
        if c_area != b_area:
            return False
        return c_routes + c_congestion <= b_routes + b_congestion + 24
