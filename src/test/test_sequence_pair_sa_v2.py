from report_test_runner import run_report_test
from agents.sequence_pair_sa_agent_v2 import SequencePairSaAgentV2


def run_test(argv=None):
    return run_report_test(
        agent_cls=SequencePairSaAgentV2,
        agent_name="SequenceSA V2",
        default_difficulty="medium",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
