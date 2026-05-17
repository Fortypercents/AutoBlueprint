from report_test_runner import run_report_test
from agents.sa_agent_v2 import SAAgentV2


def run_test(argv=None):
    return run_report_test(
        agent_cls=SAAgentV2,
        agent_name="SA V2",
        default_difficulty="high",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
