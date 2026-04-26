from __future__ import annotations

import os
from typing import Any

import httpx
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from cintara_langgraph import CintaraGuard


BASE_URL = os.environ["CINTARA_BASE_URL"].rstrip("/")
TOKEN = os.environ["CINTARA_API_TOKEN"]
AGENT_ID = os.getenv("CINTARA_DEMO_AGENT_ID", "agent-demo-langgraph")
TOOL_NAME = os.getenv("CINTARA_DEMO_TOOL_NAME", "send_email")


class DemoState(TypedDict, total=False):
    tool_call: dict[str, Any]
    user_id: str
    tool_risk_tier: str
    session_context: dict[str, Any]
    cintara: dict[str, Any]
    tool_result: dict[str, Any]


def api_base() -> str:
    if BASE_URL.endswith("/api/v1"):
        return BASE_URL
    return f"{BASE_URL}/api/v1"


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_or_reuse_agent(client: httpx.Client) -> None:
    response = client.get(f"{api_base()}/agents/", params={"search": AGENT_ID}, headers=headers())
    response.raise_for_status()
    for agent in response.json():
        if agent["name"] == AGENT_ID and agent.get("is_active", True):
            print(f"Using existing agent: {AGENT_ID}")
            return

    response = client.post(
        f"{api_base()}/agents/",
        headers=headers(),
        json={
            "name": AGENT_ID,
            "description": "LangGraph quickstart demo agent",
            "config": {"source": "cintara-langgraph"},
        },
    )
    response.raise_for_status()
    print(f"Created agent: {AGENT_ID}")


def create_or_reuse_tool(client: httpx.Client) -> str:
    response = client.get(f"{api_base()}/tools/", params={"search": TOOL_NAME}, headers=headers())
    response.raise_for_status()
    for tool in response.json():
        if tool["name"] == TOOL_NAME and tool.get("enabled", True):
            print(f"Using existing tool: {TOOL_NAME}")
            return tool["tool_id"]

    response = client.post(
        f"{api_base()}/tools/",
        headers=headers(),
        json={
            "name": TOOL_NAME,
            "description": "LangGraph quickstart mock email sender",
            "version": "1.0.0",
            "risk_tier": "WRITE",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string"},
                    "body": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["to_email", "body"],
            },
            "driver_type": "MOCK",
            "driver_config": {
                "mock_response": {
                    "sent": True,
                    "provider": "mock",
                }
            },
        },
    )
    response.raise_for_status()
    tool_id = response.json()["tool_id"]
    print(f"Created tool: {TOOL_NAME}")
    return tool_id


def create_or_update_policy(client: httpx.Client, tool_id: str) -> None:
    response = client.put(
        f"{api_base()}/policies/tool/{tool_id}",
        headers=headers(),
        json={
            "name": "LangGraph demo approval gate",
            "description": "Require approval for external or high-value email sends.",
            "priority": 20,
            "action": "APPROVAL_REQUIRED",
            "conditions": {
                "operator": "OR",
                "children": [
                    {"operator": "EQ", "field": "recipient_type", "value": "external"},
                    {"operator": "GT", "field": "amount", "value": 5000},
                ],
            },
            "obligations": [
                {
                    "type": "human_approval",
                    "timeout_seconds": 300,
                    "approver_role": "admin",
                    "notification_channels": [],
                }
            ],
        },
    )
    response.raise_for_status()
    print("Policy ready: external or high-value sends require approval")


def execute_tool(state: DemoState) -> DemoState:
    return {
        "tool_result": {
            "executed": True,
            "tool": state["tool_call"]["name"],
        }
    }


def build_graph():
    cintara = CintaraGuard(agent_id=AGENT_ID)
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


def main() -> None:
    with httpx.Client(timeout=15.0) as client:
        create_or_reuse_agent(client)
        tool_id = create_or_reuse_tool(client)
        create_or_update_policy(client, tool_id)

    graph = build_graph()
    result = graph.invoke(
        {
            "tool_call": {
                "name": TOOL_NAME,
                "args": {
                    "to_email": "customer@example.com",
                    "body": "Hello from LangGraph.",
                    "amount": 7000,
                },
            },
            "user_id": "langgraph-quickstart-user",
            "tool_risk_tier": "WRITE",
            "session_context": {
                "demo": "real_api_quickstart",
            },
        }
    )

    print("\nCintara decision:")
    print(result["cintara"])


if __name__ == "__main__":
    main()
