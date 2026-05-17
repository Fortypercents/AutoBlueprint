from report_test_runner import run_report_test
from agents.fdp_sa_agent_v1 import FdpSaAgent


def run_test(argv=None):
    return run_report_test(
        agent_cls=FdpSaAgent,
        agent_name="FDP+SA V1",
        default_difficulty="medium",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
