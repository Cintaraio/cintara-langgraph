from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from cintara_langgraph import CintaraDecision, CintaraGuard


class DemoState(TypedDict, total=False):
    tool_call: dict[str, Any]
    user_id: str
    cintara: dict[str, Any]
    tool_result: dict[str, Any]


class FakeCintaraClient:
    def decide(self, **kwargs):
        return CintaraDecision.from_api(
            {
                "request_id": "req_local_smoke",
                "action": "ALLOW",
                "reason": "Offline smoke decision allowed this tool call.",
                "violations": [],
                "obligations": [],
                "evaluation_trace": {"mode": "offline_smoke"},
                "latency_ms": 0,
            }
        )


def execute_tool(state: DemoState) -> DemoState:
    return {
        "tool_result": {
            "executed": True,
            "tool": state["tool_call"]["name"],
            "args": state["tool_call"]["args"],
        }
    }


def build_graph():
    cintara = CintaraGuard(agent_id="agent-local-smoke", client=FakeCintaraClient())
    builder = StateGraph(DemoState)
    builder.add_node("cintara", cintara)
    builder.add_node("tools", execute_tool)
    builder.set_entry_point("cintara")
    builder.add_conditional_edges(
        "cintara",
        cintara.route,
        {
            "allow": "tools",
            "approval": END,
            "deny": END,
            "error": END,
        },
    )
    builder.add_edge("tools", END)
    return builder.compile()


if __name__ == "__main__":
    graph = build_graph()
    result = graph.invoke(
        {
            "tool_call": {
                "name": "send_email",
                "args": {
                    "to_email": "customer@example.com",
                    "body": "Hello from Cintara LangGraph.",
                },
            },
            "user_id": "local-user",
        }
    )
    print(result)
