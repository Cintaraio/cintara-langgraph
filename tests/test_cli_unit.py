from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cintara_langgraph.cli import (
    InitConfig,
    _clean_url,
    _is_placeholder,
    _ps_quote,
    _quote,
    build_env_file,
    build_powershell_env_file,
    load_env_file,
)


class CintaraCliUnitTests(unittest.TestCase):
    def test_clean_url_trims_whitespace_and_trailing_slashes(self):
        self.assertEqual(_clean_url(" https://platform.cintara.io/policy/// "), "https://platform.cintara.io/policy")

    def test_shell_quote_preserves_values_with_spaces(self):
        self.assertEqual(_quote("token with spaces"), "'token with spaces'")

    def test_powershell_quote_escapes_single_quotes(self):
        self.assertEqual(_ps_quote("token's value"), "'token''s value'")

    def test_placeholder_detection_catches_missing_setup_values(self):
        self.assertTrue(_is_placeholder(""))
        self.assertTrue(_is_placeholder("<tenant-id>"))
        self.assertTrue(_is_placeholder("tenant-id>"))
        self.assertFalse(_is_placeholder("tenant-123"))

    def test_build_env_file_uses_export_lines_that_can_be_loaded(self):
        config = InitConfig(
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_url="https://platform.cintara.io/policy",
            registry_url="https://platform.cintara.io/registry",
            gateway_url="https://gateway.cintara.io",
            api_token="token with spaces",
            tool_name="send email",
        )
        env_file = build_env_file(config)

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.cintara"
            path.write_text(env_file, encoding="utf-8")
            values = load_env_file(path)

        self.assertEqual(values["CINTARA_API_TOKEN"], "token with spaces")
        self.assertEqual(values["CINTARA_DEMO_TOOL_NAME"], "send email")

    def test_build_powershell_env_file_escapes_token_value(self):
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

    def test_load_env_file_ignores_comments_blank_lines_and_non_exports(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.cintara"
            path.write_text(
                "\n".join(
                    [
                        "# comment",
                        "",
                        "export CINTARA_AGENT_ID=agent-1",
                        "CINTARA_TENANT_ID=tenant-1",
                        "not-an-assignment",
                    ]
                ),
                encoding="utf-8",
            )

            values = load_env_file(path)

        self.assertEqual(values, {"CINTARA_AGENT_ID": "agent-1", "CINTARA_TENANT_ID": "tenant-1"})


if __name__ == "__main__":
    unittest.main()
