from report_test_runner import run_report_test
from agents.generic_baseline_agent import GenericBaselineAgent


def run_test(argv=None):
    return run_report_test(
        agent_cls=GenericBaselineAgent,
        agent_name="Baseline",
        default_difficulty="high",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
