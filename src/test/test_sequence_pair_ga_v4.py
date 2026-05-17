from report_test_runner import run_report_test
from agents.sequence_pair_ga_agent_v4 import SequencePairGaAgentV4


def run_test(argv=None):
    return run_report_test(
        agent_cls=SequencePairGaAgentV4,
        agent_name="SequenceGA V4",
        default_difficulty="low",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
