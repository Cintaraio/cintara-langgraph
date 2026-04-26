from __future__ import annotations

import unittest

from cintara_langgraph import CintaraDecision, CintaraGuard, CintaraToolCall, extract_tool_call


class FakeClient:
    def __init__(self, decision: CintaraDecision):
        self.decision = decision
        self.calls = []

    def decide(self, **kwargs):
        self.calls.append(kwargs)
        return self.decision


class Message:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class CintaraGuardTests(unittest.TestCase):
    def test_extracts_explicit_tool_call(self):
        tool_call = extract_tool_call(
            {"tool_call": {"name": "send_email", "args": {"to": "a@example.com"}, "id": "call_1"}}
        )

        self.assertEqual(tool_call.name, "send_email")
        self.assertEqual(tool_call.args["to"], "a@example.com")
        self.assertEqual(tool_call.id, "call_1")

    def test_extracts_langchain_style_message_tool_call(self):
        tool_call = extract_tool_call(
            {
                "messages": [
                    Message(
                        [
                            {
                                "name": "create_invoice",
                                "args": {"amount": 1200},
                                "id": "call_2",
                            }
                        ]
                    )
                ]
            }
        )

        self.assertEqual(tool_call.name, "create_invoice")
        self.assertEqual(tool_call.args["amount"], 1200)

    def test_extracts_raw_openai_style_tool_call(self):
        tool_call = extract_tool_call(
            {
                "tool_call": {
                    "id": "call_3",
                    "function": {
                        "name": "send_slack",
                        "arguments": '{"channel": "#alerts", "text": "check"}',
                    },
                }
            }
        )

        self.assertEqual(tool_call.name, "send_slack")
        self.assertEqual(tool_call.args["channel"], "#alerts")

    def test_guard_allows_tool_call(self):
        client = FakeClient(CintaraDecision.allow(reason="ok"))
        guard = CintaraGuard(agent_id="agent-1", client=client)

        update = guard.node(
            {
                "tool_call": {"name": "send_email", "args": {"body": "hello"}},
                "user_id": "user-1",
            }
        )

        self.assertTrue(update["cintara"]["allowed"])
        self.assertEqual(update["cintara"]["route"], "allow")
        self.assertEqual(client.calls[0]["agent_id"], "agent-1")
        self.assertEqual(client.calls[0]["tool_call"], CintaraToolCall(name="send_email", args={"body": "hello"}))

    def test_guard_is_callable_as_node(self):
        client = FakeClient(CintaraDecision.allow(reason="ok"))
        guard = CintaraGuard(agent_id="agent-1", client=client)

        update = guard({"tool_call": {"name": "send_email", "args": {"body": "hello"}}})

        self.assertEqual(update["cintara"]["route"], "allow")

    def test_guard_routes_approval(self):
        client = FakeClient(
            CintaraDecision.from_api(
                {
                    "request_id": "req_1",
                    "action": "APPROVAL_REQUIRED",
                    "reason": "needs review",
                    "obligations": [{"type": "human_approval", "timeout_seconds": 300}],
                }
            )
        )
        guard = CintaraGuard(agent_id="agent-1", client=client)

        update = guard.node({"tool_call": {"name": "wire_money", "args": {"amount": 5000}}})

        self.assertFalse(update["cintara"]["allowed"])
        self.assertEqual(update["cintara"]["route"], "approval")
        self.assertEqual(guard.route(update), "approval")

    def test_guard_fails_closed_on_client_error(self):
        class BrokenClient:
            def decide(self, **kwargs):
                raise RuntimeError("offline")

        guard = CintaraGuard(agent_id="agent-1", client=BrokenClient())
        update = guard.node({"tool_call": {"name": "delete_user", "args": {"id": "u1"}}})

        self.assertFalse(update["cintara"]["allowed"])
        self.assertEqual(update["cintara"]["route"], "error")
        self.assertIn("offline", update["cintara"]["error"])


if __name__ == "__main__":
    unittest.main()
