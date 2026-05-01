from __future__ import annotations

import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from cintara_langgraph import CintaraClient, CintaraDecision, CintaraGuard, CintaraToolCall, extract_tool_call
from cintara_langgraph.cli import (
    InitConfig,
    _collect_self_service_config,
    _run_smoke_test,
    _response_error_message,
    build_powershell_env_file,
    load_env_file,
    run_init,
    write_init_files,
)


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


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "request_id": "req_1",
            "action": "ALLOW",
            "reason": "ok",
        }


class FakeHTTPClient:
    def __init__(self, timeout):
        self.timeout = timeout
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse()

    def get(self, url, headers):
        self.calls.append({"url": url, "headers": headers})
        return FakeResponse()


class FakeOnboardingResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeOnboardingHTTPClient:
    def __init__(self, timeout):
        self.timeout = timeout
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self.calls.append({"url": url, "json": json})
        if url.endswith("/start"):
            return FakeOnboardingResponse(200, {"developer_email": json["developer_email"]})
        return FakeOnboardingResponse(
            200,
            {
                "agent_id": "agent-1",
                "tenant_id": "tenant-1",
                "access_token": "runtime-token-1",
                "policy_url": "https://platform.cintara.io/policy",
                "registry_url": "https://platform.cintara.io/registry",
                "gateway_url": "https://gateway.cintara.io",
                "scope": ["policy:decide"],
            },
        )


class FailingOnboardingHTTPClient:
    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        return FakeOnboardingResponse(500, {"detail": "Internal Server Error"})


class FakeConnectivityHTTPClient:
    def __init__(self, timeout):
        self.timeout = timeout
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers):
        self.calls.append({"url": url, "headers": headers})
        return FakeOnboardingResponse(
            200,
            {
                "status": "connected",
                "message": "Cintara LangGraph runtime token is valid.",
                "tenant_id": "tenant-1",
                "agent_id": "agent-1",
                "scope": ["policy:decide"],
            },
        )


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

    def test_client_sends_production_request_context(self):
        fake_http = FakeHTTPClient(timeout=10.0)

        with patch("cintara_langgraph.client.httpx.Client", return_value=fake_http):
            client = CintaraClient(
                base_url="https://policy.example.com",
                token="token-1",
                tenant_id="00000000-0000-0000-0000-000000000001",
            )
            decision = client.decide(
                agent_id="agent-1",
                tool_call=CintaraToolCall(name="send_email", args={"body": "hello"}),
                user_id="user-1",
                session_context={
                    "user_email": "user@example.com",
                    "user_roles": ["tenant_admin"],
                    "user_privileges": ["PAGE_POLICIES_VIEW"],
                    "request_ip": "203.0.113.10",
                    "user_agent": "pytest",
                },
            )

        self.assertEqual(decision.action, "ALLOW")
        payload = fake_http.calls[0]["json"]
        self.assertEqual(fake_http.calls[0]["url"], "https://policy.example.com/api/v1/policy/decide")
        self.assertEqual(payload["context"]["tenant"]["id"], "00000000-0000-0000-0000-000000000001")
        self.assertEqual(payload["context"]["user"]["id"], "user-1")
        self.assertEqual(payload["context"]["user"]["email"], "user@example.com")
        self.assertEqual(payload["context"]["user"]["roles"], ["tenant_admin"])
        self.assertEqual(payload["context"]["request"]["ip_address"], "203.0.113.10")

    def test_client_uses_gateway_url_for_invoke_pipeline(self):
        fake_http = FakeHTTPClient(timeout=10.0)

        with patch("cintara_langgraph.client.httpx.Client", return_value=fake_http):
            client = CintaraClient(
                policy_url="https://policy.example.com",
                gateway_url="https://gateway.example.com",
                token="token-1",
                tenant_id="00000000-0000-0000-0000-000000000001",
            )
            client.invoke(
                agent_id="agent-1",
                tool_call=CintaraToolCall(name="send_email", args={"body": "hello"}),
                user_id="user-1",
            )
            client.poll("req_1")

        self.assertEqual(fake_http.calls[0]["url"], "https://gateway.example.com/api/v1/invoke/")
        self.assertEqual(fake_http.calls[1]["url"], "https://gateway.example.com/api/v1/invoke/req_1/result")

    def test_cli_writes_onboarding_files(self):
        config = InitConfig(
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_url="https://platform.cintara.io/policy",
            registry_url="https://platform.cintara.io/registry",
            gateway_url="https://gateway.cintara.io",
            api_token="token with spaces",
            tool_name="send_email",
        )

        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            written = write_init_files(project_dir, config)

            self.assertEqual(
                {path.name for path in written},
                {".env.cintara", ".env.cintara.ps1", "cintara_guard.py", "cintara_smoke_test.py"},
            )
            env_values = load_env_file(project_dir / ".env.cintara")
            shell_env = (project_dir / ".env.cintara").read_text(encoding="utf-8")
            powershell_env = (project_dir / ".env.cintara.ps1").read_text(encoding="utf-8")
            smoke_test = (project_dir / "cintara_smoke_test.py").read_text(encoding="utf-8")
            self.assertIn('.venv/bin', shell_env)
            self.assertIn("export PATH", shell_env)
            self.assertIn(".venv\\Scripts", powershell_env)
            self.assertIn("$env:PATH", powershell_env)
            self.assertIn("Connected to Cintara.", smoke_test)
            self.assertIn("LangGraph guard is ready.", smoke_test)

        self.assertEqual(env_values["CINTARA_AGENT_ID"], "agent-1")
        self.assertEqual(env_values["CINTARA_TENANT_ID"], "tenant-1")
        self.assertEqual(env_values["CINTARA_API_TOKEN"], "token with spaces")
        self.assertIn("$env:CINTARA_API_TOKEN = 'token with spaces'", powershell_env)

    def test_cli_writes_powershell_env_file_with_escaped_values(self):
        config = InitConfig(
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_url="https://platform.cintara.io/policy",
            registry_url="https://platform.cintara.io/registry",
            gateway_url="https://gateway.cintara.io",
            api_token="token's value",
        )

        powershell_env = build_powershell_env_file(config)

        self.assertIn("$env:CINTARA_API_TOKEN = 'token''s value'", powershell_env)

    def test_cli_does_not_overwrite_existing_files_by_default(self):
        config = InitConfig(
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_url="https://platform.cintara.io/policy",
            registry_url="https://platform.cintara.io/registry",
            gateway_url="https://gateway.cintara.io",
            api_token="token-1",
        )

        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            env_file = project_dir / ".env.cintara"
            env_file.write_text("custom", encoding="utf-8")
            write_init_files(project_dir, config)

            self.assertEqual(env_file.read_text(encoding="utf-8"), "custom")

    def test_cli_self_service_onboarding_exchanges_verification_code(self):
        fake_http = FakeOnboardingHTTPClient(timeout=15.0)
        args = SimpleNamespace(
            onboarding_code="onboard_123",
            developer_email="dev@example.com",
            verification_code="123456",
            tool_name="send_email",
        )

        with patch("cintara_langgraph.cli.httpx.Client", return_value=fake_http):
            config = _collect_self_service_config(args, "https://registry.example.com")

        self.assertEqual(config.agent_id, "agent-1")
        self.assertEqual(config.tenant_id, "tenant-1")
        self.assertEqual(config.api_token, "runtime-token-1")
        self.assertEqual(
            fake_http.calls[0]["url"],
            "https://registry.example.com/api/v1/langgraph/onboarding/onboard_123/start",
        )
        self.assertEqual(
            fake_http.calls[1]["url"],
            "https://registry.example.com/api/v1/langgraph/onboarding/onboard_123/complete",
        )

    def test_cli_self_service_onboarding_hides_raw_internal_server_error(self):
        args = SimpleNamespace(
            onboarding_code="onboard_123",
            developer_email="dev@example.com",
            verification_code="123456",
            tool_name="send_email",
        )
        stderr = StringIO()

        with patch(
            "cintara_langgraph.cli.httpx.Client",
            return_value=FailingOnboardingHTTPClient(timeout=15.0),
        ):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit):
                    _collect_self_service_config(args, "https://registry.example.com")

        output = stderr.getvalue()
        self.assertIn("temporarily unavailable", output)
        self.assertIn("LangGraph onboarding service", output)
        self.assertNotIn("Internal Server Error", output)

    def test_init_next_steps_use_module_command_after_loading_env(self):
        args = SimpleNamespace(
            project_dir=".",
            overwrite=False,
            skip_smoke_test=True,
            onboarding_code=None,
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_url="https://platform.cintara.io/policy",
            registry_url="https://platform.cintara.io/registry",
            gateway_url="https://gateway.cintara.io",
            api_token="runtime-token-1",
            tool_name="send_email",
        )
        stdout = StringIO()

        with TemporaryDirectory() as tmp:
            args.project_dir = tmp
            with redirect_stdout(stdout):
                run_init(args)

        output = stdout.getvalue()
        self.assertIn("source .env.cintara", output)
        self.assertIn(". .\\.env.cintara.ps1", output)
        self.assertIn("python -m cintara_langgraph test", output)
        self.assertNotIn("  cintara-langgraph test", output)

    def test_init_smoke_test_explains_expected_missing_tool_deny(self):
        class MissingToolGuard:
            def __init__(self, *_args, **_kwargs):
                pass

            def __call__(self, _state):
                return {
                    "cintara": {
                        "route": "deny",
                        "action": "DENY",
                        "reason": "Tool not found — denied (fail closed)",
                    }
                }

        args = SimpleNamespace(
            project_dir=".",
            overwrite=False,
            skip_smoke_test=False,
            onboarding_code=None,
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_url="https://platform.cintara.io/policy",
            registry_url="https://platform.cintara.io/registry",
            gateway_url="https://gateway.cintara.io",
            api_token="runtime-token-1",
            tool_name="send_email",
        )
        stdout = StringIO()

        with TemporaryDirectory() as tmp:
            args.project_dir = tmp
            with patch("cintara_langgraph.cli.CintaraGuard", MissingToolGuard):
                with redirect_stdout(stdout):
                    run_init(args)

        output = stdout.getvalue()
        self.assertIn("Connected to Cintara.", output)
        self.assertIn("LangGraph guard is ready.", output)
        self.assertIn("Control Plane reached successfully.", output)

    def test_smoke_test_prefers_connectivity_endpoint_success_message(self):
        config = InitConfig(
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_url="https://policy.example.com",
            registry_url="https://registry.example.com",
            gateway_url="https://gateway.example.com",
            api_token="runtime-token-1",
            tool_name="send_email",
        )
        stdout = StringIO()
        fake_http = FakeConnectivityHTTPClient(timeout=10.0)

        with patch("cintara_langgraph.cli.httpx.Client", return_value=fake_http):
            with patch("cintara_langgraph.cli.CintaraGuard") as guard:
                with redirect_stdout(stdout):
                    result = _run_smoke_test(config)

        self.assertEqual(result, 0)
        self.assertIn("Connected to Cintara.", stdout.getvalue())
        self.assertIn("LangGraph guard is ready.", stdout.getvalue())
        self.assertFalse(guard.called)
        self.assertEqual(
            fake_http.calls[0]["url"],
            "https://registry.example.com/api/v1/langgraph/connectivity-check",
        )

    def test_response_error_message_uses_backend_detail_for_503(self):
        response = FakeOnboardingResponse(
            503,
            {"detail": "Verification email could not be sent"},
        )

        self.assertEqual(
            _response_error_message(response),
            "Verification email could not be sent (HTTP 503)",
        )


if __name__ == "__main__":
    unittest.main()
