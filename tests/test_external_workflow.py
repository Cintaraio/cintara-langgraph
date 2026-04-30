from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from cintara_langgraph.cli import InitConfig, write_init_files


class FakePolicyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "request_id": "req_external_generated_helper",
            "action": "ALLOW",
            "reason": "External mock allowed this tool call.",
            "violations": [],
            "obligations": [],
            "evaluation_trace": {"mode": "external_generated_helper"},
            "latency_ms": 0,
        }


class FakePolicyHTTPClient:
    def __init__(self, timeout):
        self.timeout = timeout
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakePolicyResponse()


class ExternalState(TypedDict, total=False):
    tool_call: dict[str, Any]
    user_id: str
    session_context: dict[str, Any]
    cintara: dict[str, Any]
    tool_result: dict[str, Any]


def execute_tool(state: ExternalState) -> ExternalState:
    return {
        "tool_result": {
            "executed": True,
            "tool": state["tool_call"]["name"],
        }
    }


def load_generated_module(project_dir: Path):
    module_path = project_dir / "cintara_guard.py"
    spec = importlib.util.spec_from_file_location("external_cintara_guard", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.pop("external_cintara_guard", None)
    spec.loader.exec_module(module)
    return module


class ExternalGeneratedWorkflowTests(unittest.TestCase):
    def test_generated_helper_gates_a_real_langgraph_workflow(self):
        config = InitConfig(
            agent_id="agent-external-1",
            tenant_id="tenant-external-1",
            policy_url="https://policy.example.test",
            registry_url="https://registry.example.test",
            gateway_url="https://gateway.example.test",
            api_token="runtime-token-1",
            tool_name="send_email",
        )

        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            write_init_files(project_dir, config)
            generated = load_generated_module(project_dir)
            fake_http = FakePolicyHTTPClient(timeout=10.0)

            previous_env = dict(os.environ)
            os.environ.update(
                {
                    "CINTARA_POLICY_URL": config.policy_url,
                    "CINTARA_GATEWAY_URL": config.gateway_url,
                    "CINTARA_API_TOKEN": config.api_token,
                    "CINTARA_TENANT_ID": config.tenant_id,
                    "CINTARA_AGENT_ID": config.agent_id,
                }
            )
            try:
                with patch("cintara_langgraph.client.httpx.Client", return_value=fake_http):
                    builder = StateGraph(ExternalState)
                    builder.add_node("tools", execute_tool)
                    generated.add_cintara_guard(builder, tools_node="tools", approval_node=END)
                    builder.set_entry_point("cintara")
                    builder.add_edge("tools", END)
                    graph = builder.compile()
                    result = graph.invoke(
                        {
                            "tool_call": {
                                "name": "send_email",
                                "args": {
                                    "to_email": "customer@example.com",
                                    "body": "Hello from a clean external app.",
                                },
                            },
                            "user_id": "external-user-1",
                            "session_context": {
                                "user_email": "external@example.com",
                                "user_roles": ["developer"],
                            },
                        }
                    )
            finally:
                os.environ.clear()
                os.environ.update(previous_env)

        self.assertEqual(result["cintara"]["route"], "allow")
        self.assertTrue(result["tool_result"]["executed"])
        self.assertEqual(fake_http.calls[0]["url"], "https://policy.example.test/api/v1/policy/decide")
        self.assertEqual(fake_http.calls[0]["json"]["agent_id"], "agent-external-1")
        self.assertEqual(fake_http.calls[0]["json"]["context"]["user"]["email"], "external@example.com")


if __name__ == "__main__":
    unittest.main()
