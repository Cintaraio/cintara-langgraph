from __future__ import annotations

import shutil
import subprocess
import unittest
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def _skip_bash_on_windows() -> None:
    """Windows runners can expose a bash shim that requires unavailable WSL."""
    if sys.platform.startswith("win"):
        raise unittest.SkipTest("Bash installer is covered on Unix runners")


class InstallerSystemContractTests(unittest.TestCase):
    def test_bash_installer_has_valid_syntax_and_public_package_source(self):
        installer = ROOT / "scripts" / "install"
        self.assertTrue(installer.exists())

        _skip_bash_on_windows()
        if shutil.which("bash"):
            subprocess.run(["bash", "-n", str(installer)], check=True)

        text = installer.read_text(encoding="utf-8")
        self.assertIn("git+https://github.com/Cintaraio/cintara-langgraph.git", text)
        self.assertIn("python -m cintara_langgraph init", text)
        self.assertIn("Python 3.11+", text)
        self.assertIn("true < /dev/tty", text)

    def test_bash_installer_runs_with_args_without_controlling_tty(self):
        _skip_bash_on_windows()
        if not shutil.which("bash"):
            self.skipTest("bash is not available")

        installer = ROOT / "scripts" / "install"
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_python = tmp_path / "python"
            calls_file = tmp_path / "calls.txt"
            fake_python.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"printf '%s\\n' \"$*\" >> {calls_file}",
                        "if [ \"${1:-}\" = '-c' ]; then exit 0; fi",
                        "exit 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = {
                "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}",
                "PYTHON": "python",
                "VIRTUAL_ENV": str(tmp_path / ".venv"),
            }
            result = subprocess.run(
                [
                    "bash",
                    str(installer),
                    "--agent-id",
                    "agent-1",
                    "--tenant-id",
                    "tenant-1",
                    "--api-token",
                    "token-1",
                    "--skip-smoke-test",
                ],
                cwd=tmp_path,
                env=env,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_file.read_text(encoding="utf-8")
            self.assertIn("-m pip install", calls)
            self.assertIn("-m cintara_langgraph init --agent-id agent-1", calls)

    def test_powershell_installer_wires_self_service_and_manual_onboarding(self):
        installer = ROOT / "scripts" / "install.ps1"
        self.assertTrue(installer.exists())

        text = installer.read_text(encoding="utf-8")
        for expected in [
            "#Requires -Version 5.1",
            "$PackageSpec = \"cintara-langgraph[langgraph] @ git+https://github.com/Cintaraio/cintara-langgraph.git\"",
            "--onboarding-code",
            "--developer-email",
            "--verification-code",
            "--agent-id",
            "--tenant-id",
            "--policy-url",
            "--registry-url",
            "--gateway-url",
            "--api-token",
            "cintara-langgraph test",
        ]:
            self.assertIn(expected, text)

    def test_readme_public_install_urls_match_real_scripts(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "https://raw.githubusercontent.com/Cintaraio/cintara-langgraph/main/scripts/install",
            readme,
        )
        self.assertIn(
            "https://raw.githubusercontent.com/Cintaraio/cintara-langgraph/main/scripts/install.ps1",
            readme,
        )
        self.assertTrue((ROOT / "scripts" / "install").exists())
        self.assertTrue((ROOT / "scripts" / "install.ps1").exists())

    def test_ci_runs_tests_on_linux_and_windows(self):
        workflow = ROOT / ".github" / "workflows" / "test.yml"
        self.assertTrue(workflow.exists())

        text = workflow.read_text(encoding="utf-8")
        self.assertIn("ubuntu-latest", text)
        self.assertIn("windows-latest", text)
        self.assertIn('"3.11"', text)
        self.assertIn('"3.12"', text)
        self.assertIn("python -m unittest discover -s tests -v", text)


if __name__ == "__main__":
    unittest.main()
