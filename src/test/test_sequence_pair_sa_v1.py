from report_test_runner import run_report_test
from agents.sequence_pair_sa_agent_v1 import SequencePairSaAgentV1


def run_test(argv=None):
    return run_report_test(
        agent_cls=SequencePairSaAgentV1,
        agent_name="SequenceSA V1",
        default_difficulty="medium",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
