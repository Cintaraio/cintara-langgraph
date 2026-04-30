# Cintara LangGraph Package Ops Readiness Scan

Date: 2026-04-29
Scope: public installer, Windows support, CLI onboarding, package tests, and open-source readiness.

## Current State

- The package has Linux/macOS and Windows installers:
  - `scripts/install`
  - `scripts/install.ps1`
- The README uses raw GitHub installer URLs from `main`.
- Unit tests cover guard extraction, policy request payload, gateway invoke URL, generated env files, PowerShell env escaping, and self-service onboarding exchange.
- `LICENSE` exists.

## Fix Now

1. There is no GitHub Actions CI in this repo.
   Evidence: no `.github/workflows` directory.
   Risk: installer or package changes can merge without running tests.
   Recommended fix: add CI for Python 3.11 and 3.12 running `python -m unittest` or `pytest`.

2. Installers pull from the `main` branch.
   Evidence: README and scripts use `git+https://github.com/Cintaraio/cintara-langgraph.git` and raw `main` script URLs.
   Risk: external developers can receive unreviewed breaking changes.
   Recommended fix: publish tagged releases and update installer docs to use a stable tag, even if `main` remains available for early testers.

3. External onboarding still depends on backend email delivery.
   Risk: SES sandbox or backend IAM mistakes surface to developers as onboarding failures.
   Recommended fix: CLI should show a short troubleshooting message when `/start` fails, including "ask Cintara to verify your recipient email or use manual setup while SES is in sandbox."

4. Open-source repo readiness is incomplete.
   Evidence: `LICENSE` exists, but no `SECURITY.md`, `CONTRIBUTING.md`, release process, or public support expectations were found.
   Recommended fix: add minimal open-source housekeeping before broad developer sharing.

## Test Gaps To Add

- CI test matrix:
  - Python 3.11
  - Python 3.12
  - Linux runner
  - Windows runner for PowerShell installer sanity

- Installer tests:
  - `bash -n scripts/install`
  - PowerShell parser check for `scripts/install.ps1`
  - smoke test that installer writes `.env.cintara`, `.env.cintara.ps1`, `cintara_guard.py`, and `cintara_smoke_test.py` in a temp project.

- CLI error tests:
  - onboarding `/start` returns `403` for disallowed domain.
  - onboarding `/start` returns `503` for email failure.
  - CLI output tells the user what to do without mentioning internal AWS details.

- Live integration test, opt-in only:
  - guarded by env vars such as `CINTARA_TEST_ONBOARDING_CODE` and `CINTARA_TEST_DEVELOPER_EMAIL`.
  - runs only manually or nightly.

## Later Hardening

- Publish the package to PyPI once API stabilizes.
- Add signed release tags or GitHub release assets for installer integrity.
- Add minimal examples for LangChain, LangGraph, and raw Python.
- Add a compatibility table for Python, LangGraph, and supported operating systems.

## Suggested Immediate PR

- Add GitHub Actions CI.
- Add `SECURITY.md` and `CONTRIBUTING.md`.
- Add installer syntax tests.
- Improve CLI error copy for SES sandbox/email verification failures.
