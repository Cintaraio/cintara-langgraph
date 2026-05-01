# Cintara LangGraph Integration

Tiny LangGraph integration for placing Cintara as one trust-control step before a tool executes.

The goal is deliberately simple:

```python
from cintara_langgraph import CintaraGuard

cintara = CintaraGuard(agent_id="agent-prod-001")
builder.add_node("cintara", cintara.node)
builder.add_conditional_edges(
    "cintara",
    cintara.route,
    {
        "allow": "tools",
        "approval": "human_review",
        "deny": "__end__",
        "error": "__end__",
    },
)
```

The node reads a pending tool call from graph state, sends it to Cintara, and writes a compact decision back into state.

## Install Locally

Python 3.11 or newer is recommended. If your default `python3` is older, use
`PYTHON=python3.11` before running the installer. The installer creates a local
`.venv` and the generated `.env.cintara` files add that `.venv` to your shell
path when loaded from the project directory.

```bash
cd cintara-langgraph
python3 -m pip install -e .
```

## Zero-Doc Onboarding

For developers who want the fastest path, run the installer script from a
LangGraph project directory:

macOS, Linux, WSL, or Git Bash:

```bash
curl -fsSL https://raw.githubusercontent.com/Cintaraio/cintara-langgraph/main/scripts/install | bash -s -- \
  --onboarding-code "<onboarding-code>" \
  --registry-url "https://platform.cintara.io/registry"
```

Windows PowerShell:

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/Cintaraio/cintara-langgraph/main/scripts/install.ps1 -OutFile .\install-cintara-langgraph.ps1
powershell -ExecutionPolicy Bypass -File .\install-cintara-langgraph.ps1 `
  -OnboardingCode "<onboarding-code>" `
  -RegistryUrl "https://platform.cintara.io/registry"
```

The self-service flow asks for your developer email, sends a verification code,
then writes a short-lived agent runtime token into `.env.cintara`.

If your Cintara admin gave you explicit values instead of an onboarding code,
run:

macOS, Linux, WSL, or Git Bash:

```bash
curl -fsSL https://raw.githubusercontent.com/Cintaraio/cintara-langgraph/main/scripts/install | bash -s -- \
  --agent-id "<agent-id>" \
  --tenant-id "<tenant-id>" \
  --policy-url "https://platform.cintara.io/policy" \
  --registry-url "https://platform.cintara.io/registry" \
  --gateway-url "https://gateway.cintara.io" \
  --api-token "<cintara-runtime-token>"
```

Windows PowerShell:

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/Cintaraio/cintara-langgraph/main/scripts/install.ps1 -OutFile .\install-cintara-langgraph.ps1
powershell -ExecutionPolicy Bypass -File .\install-cintara-langgraph.ps1 `
  -AgentId "<agent-id>" `
  -TenantId "<tenant-id>" `
  -PolicyUrl "https://platform.cintara.io/policy" `
  -RegistryUrl "https://platform.cintara.io/registry" `
  -GatewayUrl "https://gateway.cintara.io" `
  -ApiToken "<cintara-runtime-token>"
```

The script installs the package, prompts locally for any missing values, creates
`.env.cintara`, creates `.env.cintara.ps1` for Windows PowerShell, creates
`cintara_guard.py`, and creates `cintara_smoke_test.py`. The preferred path is
self-service onboarding. You should not copy a token from browser DevTools.

After installation:

```bash
source .env.cintara
python -m cintara_langgraph test
```

On Windows PowerShell:

```powershell
. .\.env.cintara.ps1
python -m cintara_langgraph test
```

If your own LangGraph app calls an LLM provider, set that provider's key as
well, for example `OPENAI_API_KEY`. The Cintara smoke test itself does not need
an OpenAI key.

You can also run the initializer directly:

```bash
python3 -m cintara_langgraph init --agent-id "<agent-id>" --tenant-id "<tenant-id>"
cintara-langgraph init --help
```

Install from GitHub:

```bash
python3 -m pip install "git+https://github.com/Cintaraio/cintara-langgraph.git"
```

Install from GitHub with LangGraph example dependencies:

```bash
python3 -m pip install "cintara-langgraph[langgraph] @ git+https://github.com/Cintaraio/cintara-langgraph.git"
```

For LangGraph interrupt support:

```bash
python3 -m pip install -e ".[langgraph]"
```

## Environment

```bash
export CINTARA_BASE_URL="https://api.cintara.io"
export CINTARA_API_TOKEN="<cintara-runtime-token>"
export CINTARA_TENANT_ID="..."
```

`agent_id` is the only value application code normally needs to pass directly. Base URL, token, and tenant can come from environment configuration.

For split-service deployments, point the guard at the public Policy service:

```bash
export CINTARA_POLICY_URL="https://policy.example.com"
export CINTARA_GATEWAY_URL="https://gateway.example.com"
export CINTARA_REGISTRY_URL="https://registry.example.com"
```

`CINTARA_POLICY_URL` takes precedence over `CINTARA_BASE_URL` for policy decisions. `CINTARA_GATEWAY_URL` is used by the optional invoke pipeline helpers (`invoke()` and `poll()`). `CINTARA_REGISTRY_URL` is used only by the real API quickstart to create demo agents and tools.

## 5-Minute Real API Quickstart

Install with LangGraph support:

```bash
python3 -m pip install -e ".[langgraph]"
```

Set your Cintara API configuration:

```bash
export CINTARA_BASE_URL="http://localhost:8000"
export CINTARA_POLICY_URL="http://localhost:8003"
export CINTARA_GATEWAY_URL="http://localhost:8002"
export CINTARA_REGISTRY_URL="http://localhost:8004"
export CINTARA_API_TOKEN="..."
export CINTARA_TENANT_ID="..."
```

Run the real API quickstart:

```bash
python3 examples/real_api_quickstart.py
```

The script uses the Cintara API to:

- create or reuse `agent-demo-langgraph`
- create or reuse a mock `send_email` governed tool
- add a policy requiring approval for external or high-value sends
- run a LangGraph workflow with Cintara as the pre-tool guard step

For a customer demo, the important line is still just:

```python
cintara = CintaraGuard(agent_id="agent-demo-langgraph")
```

## Local Smoke Test

To verify LangGraph wiring without Cintara API credentials:

```bash
python3 examples/offline_smoke.py
```

This compiles a real LangGraph graph, calls `CintaraGuard`, routes through `allow`, and executes the mock tool node.

## Local Browser Demo

To see the LangGraph integration in a small browser app:

```bash
python3 examples/local_demo_app.py
```

Then open `http://127.0.0.1:8090`.

This demo uses a local fake Cintara decision client, but still runs a real LangGraph workflow with `CintaraGuard` as the pre-tool guard step.

## Expected State Shape

The simplest explicit state shape is:

```python
state = {
    "tool_call": {
        "name": "send_email",
        "args": {"to_email": "customer@example.com", "body": "Hello"},
        "id": "call_123",
    },
    "user_id": "user_123",
    "session_context": {"thread_id": "thread_123"},
}
```

The node also understands the common LangChain message format where the latest AI message has `tool_calls`.

## Output State

The node returns a partial state update:

```python
{
    "cintara": {
        "allowed": True,
        "route": "allow",
        "action": "ALLOW",
        "reason": "No conditions matched - ALLOW",
        "request_id": "req_...",
        "decision": {...},
        "tool_call": {...},
    }
}
```

Routes:

- `allow`: continue to tool execution
- `approval`: route to a human review node or use LangGraph interrupt mode
- `deny`: stop execution
- `error`: fail closed by default

## Approval Interrupts

If you want LangGraph-native human approval, enable interrupts:

```python
cintara = CintaraGuard(
    agent_id="agent-prod-001",
    interrupt_on_approval=True,
)
```

When Cintara returns `APPROVAL_REQUIRED`, the node pauses with `langgraph.types.interrupt`. Resuming with `{"approved": true}` lets the graph continue; any other resume payload denies the tool call.

## Why This Shape

The current Cintara gateway already has the right production surface:

- `POST /api/v1/policy/decide`
- `POST /api/v1/invoke/`
- `GET /api/v1/invoke/{request_id}/result`
- approvals and audit services behind the gateway

This integration starts with `policy/decide` because it is the smallest, easiest insertion point in a LangGraph workflow: one pre-tool guard node.
