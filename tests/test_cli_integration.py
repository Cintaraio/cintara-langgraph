from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class CintaraCliIntegrationTests(unittest.TestCase):
    def test_init_command_writes_manual_onboarding_files(self):
        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cintara_langgraph",
                    "init",
                    "--project-dir",
                    str(project_dir),
                    "--agent-id",
                    "agent-1",
                    "--tenant-id",
                    "tenant-1",
                    "--policy-url",
                    "https://platform.cintara.io/policy",
                    "--registry-url",
                    "https://platform.cintara.io/registry",
                    "--gateway-url",
                    "https://gateway.cintara.io",
                    "--api-token",
                    "runtime-token-1",
                    "--tool-name",
                    "send_email",
                    "--skip-smoke-test",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Created:", result.stdout)
            self.assertIn("cintara-langgraph test", result.stdout)
            self.assertTrue((project_dir / ".env.cintara").exists())
            self.assertTrue((project_dir / ".env.cintara.ps1").exists())
            self.assertTrue((project_dir / "cintara_guard.py").exists())
            self.assertTrue((project_dir / "cintara_smoke_test.py").exists())

            env_text = (project_dir / ".env.cintara").read_text(encoding="utf-8")
            self.assertIn("export CINTARA_AGENT_ID=agent-1", env_text)
            self.assertIn("export CINTARA_API_TOKEN=runtime-token-1", env_text)


if __name__ == "__main__":
    unittest.main()
