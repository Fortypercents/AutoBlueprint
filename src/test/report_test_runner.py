import argparse
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple, Type

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from entities.material import MaterialType
from entities.transport import TransportComponent
from environment.grid_map import GridMap
from utils.test_utils import render_system_b_blueprint


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    target_outputs: Dict[MaterialType, float]
    available_inputs: Iterable[MaterialType]
    grid_size: Tuple[int, int]
    feed_ticks: int
    ticks: int


BENCHMARKS = {
    "low": BenchmarkScenario(
        name="low",
        target_outputs={MaterialType.BLUE_IRON_BOTTLE: 2.0},
        available_inputs=[MaterialType.BLUE_IRON],
        grid_size=(45, 45),
        feed_ticks=60,
        ticks=200,
    ),
    "medium": BenchmarkScenario(
        name="medium",
        target_outputs={MaterialType.MID_CAP_BATTERY: 1.0},
        available_inputs=[MaterialType.BLUE_IRON, MaterialType.ORIGINIUM],
        grid_size=(45, 45),
        feed_ticks=80,
        ticks=220,
    ),
    "high": BenchmarkScenario(
        name="high",
        target_outputs={MaterialType.MID_CAP_BATTERY: 3.0},
        available_inputs=[MaterialType.BLUE_IRON, MaterialType.ORIGINIUM],
        grid_size=(60, 60),
        feed_ticks=120,
        ticks=260,
    ),
    "extreme": BenchmarkScenario(
        name="extreme",
        target_outputs={MaterialType.HIGH_CAP_BATTERY: 1.0},
        available_inputs=[MaterialType.BLUE_IRON, MaterialType.ORIGINIUM, MaterialType.SANDLEAF_SEED],
        grid_size=(120, 90),
        feed_ticks=150,
        ticks=320,
    ),
}


def material_summary(materials: Dict[MaterialType, float]) -> str:
    return ";".join(f"{mat.name}={amount:g}" for mat, amount in materials.items())


def external_io_only_cells(agent) -> set:
    external_cells = set()
    internal_cells = set()

    for path in getattr(agent, "external_io_paths", []):
        external_cells.update(path)
    for path in getattr(agent, "internal_route_paths", []):
        internal_cells.update(path)

    return external_cells - internal_cells


def blueprint_cells(env: GridMap, agent) -> list:
    excluded_external = external_io_only_cells(agent)
    occupied = []
    for y in range(env.height):
        for x in range(env.width):
            cell = env._get_cell(x, y)
            if cell is None:
                continue
            if isinstance(cell, TransportComponent) and (x, y) in excluded_external:
                continue
            occupied.append((x, y))
    return occupied


def occupied_area(env: GridMap, agent) -> int:
    occupied = blueprint_cells(env, agent)
    if not occupied:
        return 0
    min_x = min(x for x, _ in occupied)
    max_x = max(x for x, _ in occupied)
    min_y = min(y for _, y in occupied)
    max_y = max(y for _, y in occupied)
    return (max_x - min_x + 1) * (max_y - min_y + 1)


def blueprint_belt_length(env: GridMap, agent) -> int:
    excluded_external = external_io_only_cells(agent)
    return sum(
        1
        for transport in env.transports
        if getattr(transport, "pos", None) not in excluded_external
    )


def route_success(agent) -> bool:
    failed_routes = getattr(agent, "failed_routes", [])
    if failed_routes:
        return False
    generated_outputs = getattr(agent, "generated_outputs", {})
    return bool(generated_outputs)


def inject_inputs(env: GridMap, agent) -> None:
    for mat, in_ports in getattr(agent, "generated_inputs", {}).items():
        for ix, iy in in_ports:
            cell = env._get_cell(ix, iy)
            if cell is not None and getattr(cell, "current_item", None) is None:
                cell.current_item = (mat, 1.0)


def consume_building_inputs(env: GridMap) -> None:
    for building in env.buildings:
        if not hasattr(building, "inventory"):
            building.inventory = {}
        for px, py in building.active_input_ports:
            port_cell = env._get_cell(px, py)
            if port_cell is None or getattr(port_cell, "current_item", None) is None:
                continue

            item = port_cell.current_item
            mat = item[0] if isinstance(item, tuple) else item
            amt = item[1] if isinstance(item, tuple) else 1.0
            allowed = getattr(building, "allowed_input_materials", building.input_materials.keys())
            if mat not in allowed:
                continue

            max_inv = getattr(building, "max_inventory", 10.0)
            current_inv = building.inventory.get(mat, 0)
            if current_inv >= max_inv:
                continue

            take_amt = min(amt, max_inv - current_inv)
            building.inventory[mat] = current_inv + take_amt
            port_cell.current_item = (mat, amt - take_amt) if amt - take_amt > 0 else None


def collect_outputs(env: GridMap, agent, target_outputs: Dict[MaterialType, float], yields: Dict[MaterialType, float]) -> None:
    target_materials = set(target_outputs)
    for _mat, out_ports in getattr(agent, "generated_outputs", {}).items():
        for ox, oy in out_ports:
            cell = env._get_cell(ox, oy)
            if cell is None:
                continue
            item = getattr(cell, "current_item", None)
            if item is None:
                continue

            item_mat = item[0] if isinstance(item, tuple) else item
            item_amt = item[1] if isinstance(item, tuple) else 1.0
            if item_mat in target_materials:
                yields[item_mat] = yields.get(item_mat, 0.0) + item_amt
                cell.current_item = None


def production_success(target_outputs: Dict[MaterialType, float], yields: Dict[MaterialType, float]) -> bool:
    return all(yields.get(mat, 0.0) >= amount for mat, amount in target_outputs.items())


def run_report_test(
    agent_cls: Type,
    agent_name: str,
    default_difficulty: str,
    argv=None,
) -> Dict[str, object]:
    parser = argparse.ArgumentParser(description=f"Run one report benchmark for {agent_name}.")
    parser.add_argument("--difficulty", choices=sorted(BENCHMARKS), default=default_difficulty)
    parser.add_argument("--seed", type=int, default=16)
    parser.add_argument("--ticks", type=int, default=None)
    parser.add_argument("--feed-ticks", type=int, default=None)
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args(argv)

    random.seed(args.seed)
    scenario = BENCHMARKS[args.difficulty]
    ticks_to_simulate = args.ticks if args.ticks is not None else scenario.ticks
    feed_ticks = args.feed_ticks if args.feed_ticks is not None else scenario.feed_ticks
    render = not args.no_render

    env = GridMap(*scenario.grid_size)
    agent = agent_cls(
        target_outputs=dict(scenario.target_outputs),
        available_inputs=list(scenario.available_inputs),
    )

    print("\n" + "=" * 72)
    print(f"Running report benchmark: {agent_name}")
    print(f"Difficulty: {scenario.name} | Seed: {args.seed}")
    print(f"Target: {material_summary(scenario.target_outputs)}")
    print("=" * 72)

    agent.optimize(env)

    for building in env.buildings:
        env.update_connections(building)

    yields: Dict[MaterialType, float] = {}
    for tick in range(1, ticks_to_simulate + 1):
        if tick <= feed_ticks:
            inject_inputs(env, agent)

        consume_building_inputs(env)
        env.tick()
        collect_outputs(env, agent, scenario.target_outputs, yields)

        if render and tick % 2 == 0:
            yield_text = material_summary(yields) if yields else "no_output=0"
            status = f"{agent_name} | {scenario.name} | Area {occupied_area(env, agent)} | Belts {blueprint_belt_length(env, agent)} | Yield {yield_text}"
            render_system_b_blueprint(env, tick=tick, status_text=status)
            time.sleep(0.05)

    area = occupied_area(env, agent)
    belt_length = blueprint_belt_length(env, agent)
    routing_ok = route_success(agent)
    production_ok = production_success(scenario.target_outputs, yields)
    failed_count = len(getattr(agent, "failed_routes", []))

    result = {
        "agent": agent_name,
        "difficulty": scenario.name,
        "seed": args.seed,
        "target": material_summary(scenario.target_outputs),
        "best_area": area,
        "best_belt_length": belt_length,
        "routing_success": int(routing_ok),
        "production_success": int(production_ok),
        "final_yield": material_summary(yields) if yields else "none=0",
        "failed_routes": failed_count,
    }

    print("\n=== REPORT_RESULT_BEGIN ===")
    print(f"Agent: {result['agent']}")
    print(f"Difficulty: {result['difficulty']}")
    print(f"Seed: {result['seed']}")
    print(f"Target: {result['target']}")
    print(f"Best Area: {result['best_area']}")
    print(f"Best Belt Length: {result['best_belt_length']}")
    print(f"Routing Success: {result['routing_success']}")
    print(f"Production Success: {result['production_success']}")
    print(f"Final Yield: {result['final_yield']}")
    print(f"Failed Routes: {result['failed_routes']}")
    print("=== REPORT_RESULT_END ===")
    print(
        "REPORT_CSV,"
        f"{result['agent']},"
        f"{result['difficulty']},"
        f"{result['seed']},"
        f"{result['best_area']},"
        f"{result['best_belt_length']},"
        f"{result['routing_success']},"
        f"{result['production_success']},"
        f"{result['final_yield']},"
        f"{result['failed_routes']}"
    )

    return result
