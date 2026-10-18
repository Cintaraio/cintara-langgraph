from unittest.mock import Mock
import pytest
from cintara_langgraph import GovernedWorkflow


def setup():
    client = Mock()
    client.poll.return_value = {"status": "COMPLETED", "decision": "ALLOW"}
    client.authorize_execution.return_value = {
        "authorized": True,
        "request_id": "server-request",
    }
    client.execute_sandbox.return_value = {"task_id": "server-request"}
    return (
        GovernedWorkflow(client=client, agent_id="agent", tool_name="safe_tool"),
        client,
    )


def state():
    return {"tool_call": {"name": "safe_tool", "args": {"value": 1}}}


def test_local_approved_resume_cannot_bypass_review():
    workflow, client = setup()
    client.poll.return_value = {
        "status": "PENDING_APPROVAL",
        "decision": "APPROVAL_REQUIRED",
    }
    assert (
        workflow.advance({**state(), "approved": True}, request_id="server-request")[
            "status"
        ]
        == "awaiting_reviewer"
    )
    client.authorize_execution.assert_not_called()
    client.execute_sandbox.assert_not_called()


@pytest.mark.parametrize("decision", ["DENY", "REJECTED", "EXPIRED"])
def test_blocked_does_not_dispatch(decision):
    workflow, client = setup()
    client.poll.return_value = {"status": decision, "decision": decision}
    assert workflow.advance(state(), request_id="server-request")["status"] == "blocked"
    client.execute_sandbox.assert_not_called()


def test_authorization_failure_prevents_dispatch():
    workflow, client = setup()
    client.authorize_execution.side_effect = RuntimeError("stale arguments")
    with pytest.raises(RuntimeError):
        workflow.advance(state(), request_id="server-request")
    client.execute_sandbox.assert_not_called()


def test_exact_lifecycle_and_outcome():
    workflow, client = setup()
    assert (
        workflow.advance(state(), request_id="server-request")["status"] == "executed"
    )
    assert [c[0] for c in client.mock_calls] == [
        "poll",
        "authorize_execution",
        "execute_sandbox",
        "record_outcome",
    ]


@pytest.mark.parametrize(
    "s",
    [
        {
            "messages": [
                {
                    "tool_calls": [
                        {"name": "safe_tool", "args": {}},
                        {"name": "other", "args": {}},
                    ]
                }
            ]
        },
        {"tool_call": {"name": "other", "args": {}}},
        {**state(), "messages": [{"tool_calls": [{"name": "safe_tool", "args": {}}]}]},
    ],
)
def test_no_unchecked_calls(s):
    workflow, client = setup()
    with pytest.raises(ValueError):
        workflow.submit(s, idempotency_key="stable-key")
    client.invoke.assert_not_called()


def test_completed_outcome_is_not_executed_again():
    workflow, client = setup()
    client.poll.return_value = {
        "execution_outcome": "succeeded",
        "status": "COMPLETED",
        "decision": "ALLOW",
    }
    assert (
        workflow.advance(state(), request_id="server-request")["status"] == "recorded"
    )
    client.execute_sandbox.assert_not_called()


def test_langgraph_resume_true_still_waits_for_real_approval():
    from typing import TypedDict
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    class State(TypedDict, total=False):
        tool_call: dict
        cintara_idempotency_key: str
        cintara_request_id: str
        cintara: dict

    workflow, client = setup()
    client.invoke.return_value = {"request_id": "server-request"}
    client.poll.return_value = {
        "status": "PENDING_APPROVAL",
        "decision": "APPROVAL_REQUIRED",
    }
    graph = StateGraph(State)
    graph.add_node("govern", workflow.node)
    graph.add_edge(START, "govern")
    graph.add_edge("govern", END)
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "synthetic-approval-case"}}
    result = app.invoke(
        {**state(), "cintara_idempotency_key": "persisted-request-key"}, config
    )
    assert result["__interrupt__"]
    result = app.invoke(Command(resume={"approved": True}), config)
    assert result["cintara"]["status"] == "awaiting_reviewer"
    client.execute_sandbox.assert_not_called()
    assert all(
        c.kwargs["idempotency_key"] == "persisted-request-key"
        for c in client.invoke.call_args_list
    )
