from report_test_runner import run_report_test
from agents.sa_agent_v1 import SABaselineAgent


def run_test(argv=None):
    return run_report_test(
        agent_cls=SABaselineAgent,
        agent_name="SA V1",
        default_difficulty="low",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
