from __future__ import annotations

import os
import shutil
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
            self.assertIn("python -m cintara_langgraph test", result.stdout)
            self.assertTrue((project_dir / ".env.cintara").exists())
            self.assertTrue((project_dir / ".env.cintara.ps1").exists())
            self.assertTrue((project_dir / "cintara_guard.py").exists())
            self.assertTrue((project_dir / "cintara_smoke_test.py").exists())

            env_text = (project_dir / ".env.cintara").read_text(encoding="utf-8")
            ps_env_text = (project_dir / ".env.cintara.ps1").read_text(encoding="utf-8")
            self.assertIn('.venv/bin', env_text)
            self.assertIn(".venv\\Scripts", ps_env_text)
            self.assertIn("export CINTARA_AGENT_ID=agent-1", env_text)
            self.assertIn("export CINTARA_API_TOKEN=runtime-token-1", env_text)

    def test_generated_shell_env_adds_local_venv_to_path(self):
        if sys.platform.startswith("win") or not shutil.which("bash"):
            raise unittest.SkipTest("Bash env sourcing is covered on Unix runners")

        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            venv_bin = project_dir / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            fake_python = venv_bin / "python"
            fake_python.write_text("#!/usr/bin/env bash\nprintf 'fake-venv-python\\n'\n", encoding="utf-8")
            fake_python.chmod(0o755)

            subprocess.run(
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
                    "--api-token",
                    "runtime-token-1",
                    "--skip-smoke-test",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
                text=True,
                capture_output=True,
                check=True,
            )

            result = subprocess.run(
                ["bash", "-lc", "source .env.cintara && command -v python && python"],
                cwd=project_dir,
                text=True,
                capture_output=True,
                check=True,
            )

        self.assertIn(f"{venv_bin}/python", result.stdout)
        self.assertIn("fake-venv-python", result.stdout)

    def test_generated_powershell_env_adds_local_venv_to_path(self):
        if not sys.platform.startswith("win"):
            raise unittest.SkipTest("PowerShell env sourcing is covered on Windows runners")

        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            (project_dir / ".venv" / "Scripts").mkdir(parents=True)

            subprocess.run(
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
                    "--api-token",
                    "runtime-token-1",
                    "--skip-smoke-test",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
                text=True,
                capture_output=True,
                check=True,
            )

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    (
                        ". .\\.env.cintara.ps1; "
                        "$expected = (Join-Path (Get-Location) '.venv\\Scripts') + ';'; "
                        "if (-not $env:PATH.StartsWith($expected)) { "
                        "  Write-Error \"PATH did not start with $expected\"; exit 3 "
                        "}; "
                        "Write-Output $env:PATH"
                    ),
                ],
                cwd=project_dir,
                text=True,
                capture_output=True,
                check=True,
            )

        self.assertIn(".venv\\Scripts", result.stdout)


if __name__ == "__main__":
    unittest.main()
