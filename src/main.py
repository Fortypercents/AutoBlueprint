from agents.sequence_pair_ga_agent_v4 import SequencePairGaAgentV4
from entities.material import MaterialType
from environment.grid_map import GridMap


def main():
    """Run a small default AutoBlueprint example."""
    grid = GridMap(width=40, height=34)
    target_outputs = {MaterialType.BLUE_IRON_BOTTLE: 2.0}
    available_inputs = [MaterialType.BLUE_IRON]

    agent = SequencePairGaAgentV4(
        target_outputs=target_outputs,
        available_inputs=available_inputs,
    )
    agent.optimize(grid)

    print("AutoBlueprint default example")
    print(f"Target outputs: {target_outputs}")
    print(f"Available inputs: {available_inputs}")
    print(f"Buildings placed: {len(grid.buildings)}")
    print(f"Transport components placed: {len(grid.transports)}")


if __name__ == "__main__":
    main()
