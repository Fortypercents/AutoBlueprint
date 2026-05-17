from report_test_runner import run_report_test
from agents.flow_cp_agent_v1 import FlowCpAgentV1


def run_test(argv=None):
    return run_report_test(
        agent_cls=FlowCpAgentV1,
        agent_name="Flow/CP V1",
        default_difficulty="high",
        argv=argv,
    )


if __name__ == "__main__":
    run_test()
