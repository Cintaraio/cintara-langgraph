from pathlib import Path
from cintara_langgraph.cli import InitConfig, write_init_files, build_parser


def test_generated_credentials_private_and_gitignored(tmp_path):
    config = InitConfig(
        agent_id="agent",
        tenant_id="tenant",
        policy_url="https://showcase.platform.cintara.io/policy",
        registry_url="https://showcase.platform.cintara.io/registry",
        gateway_url="https://showcase.platform.cintara.io",
        api_token="synthetic-test-token",
    )
    write_init_files(tmp_path, config)
    for name in (".env.cintara", ".env.cintara.ps1"):
        assert (tmp_path / name).stat().st_mode & 0o077 == 0
        assert name in (tmp_path / ".gitignore").read_text().splitlines()
    assert not (tmp_path / "package.json").exists()


def test_client_credential_flags_are_supported():
    args = build_parser().parse_args(
        [
            "init",
            "--client-id",
            "synthetic",
            "--client-secret",
            "synthetic-only",
            "--auth-url",
            "https://showcase.platform.cintara.io/auth",
        ]
    )
    assert args.client_id == "synthetic" and args.auth_url.endswith("/auth")
