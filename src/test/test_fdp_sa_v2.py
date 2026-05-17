from report_test_runner import run_report_test
from agents.fdp_sa_agent_v2 import FdpSaAgentV2


def run_test(argv=None):
    return run_report_test(
        agent_cls=FdpSaAgentV2,
        agent_name="FDP+SA V2",
        default_difficulty="medium",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
