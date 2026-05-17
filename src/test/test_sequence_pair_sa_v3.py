from report_test_runner import run_report_test
from agents.sequence_pair_sa_agent_v3 import SequencePairSaAgentV3


def run_test(argv=None):
    return run_report_test(
        agent_cls=SequencePairSaAgentV3,
        agent_name="SequenceSA V3",
        default_difficulty="high",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
