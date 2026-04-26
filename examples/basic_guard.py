from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from cintara_langgraph import CintaraGuard


class AgentState(TypedDict, total=False):
    tool_call: dict
    user_id: str
    session_context: dict
    cintara: dict


def execute_tool(state: AgentState) -> AgentState:
    tool_call = state["tool_call"]
    return {"tool_result": {"ok": True, "tool": tool_call["name"]}}


cintara = CintaraGuard(agent_id="agent-prod-001")

builder = StateGraph(AgentState)
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

graph = builder.compile()

result = graph.invoke(
    {
        "tool_call": {
            "name": "send_email",
            "args": {"to_email": "customer@example.com", "body": "Hello"},
        },
        "user_id": "user-123",
        "session_context": {"thread_id": "thread-123"},
    }
)

print(result)
