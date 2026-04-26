from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from cintara_langgraph import CintaraDecision, CintaraGuard


class DemoState(TypedDict, total=False):
    tool_call: dict[str, Any]
    user_id: str
    cintara: dict[str, Any]
    tool_result: dict[str, Any]
    approval_request: dict[str, Any]


class DemoCintaraClient:
    def __init__(self, action: str) -> None:
        self.action = action

    def decide(self, **kwargs: Any) -> CintaraDecision:
        tool_call = kwargs["tool_call"]
        agent_id = kwargs["agent_id"]
        action = self.action
        if action == "APPROVAL_REQUIRED":
            reason = "Cintara requires human approval before this tool executes."
        elif action == "DENY":
            reason = "Cintara denied this tool call based on the selected demo policy."
        else:
            reason = "Cintara allowed this tool call to continue."

        return CintaraDecision.from_api(
            {
                "request_id": f"req_demo_{datetime.now(timezone.utc).strftime('%H%M%S')}",
                "action": action,
                "reason": reason,
                "violations": [],
                "obligations": [],
                "evaluation_trace": {
                    "mode": "local_demo",
                    "agent_id": agent_id,
                    "tool": tool_call.name,
                },
                "latency_ms": 0,
            }
        )


def execute_tool(state: DemoState) -> DemoState:
    tool_call = state["tool_call"]
    return {
        "tool_result": {
            "executed": True,
            "tool": tool_call["name"],
            "args": tool_call["args"],
            "message": "Tool execution happened only after the Cintara guard returned allow.",
        }
    }


def request_approval(state: DemoState) -> DemoState:
    return {
        "approval_request": {
            "created": True,
            "message": "Workflow paused for human approval instead of executing the tool.",
            "cintara": state.get("cintara", {}),
        }
    }


def build_demo_graph(agent_id: str, action: str):
    cintara = CintaraGuard(
        agent_id=agent_id,
        client=DemoCintaraClient(action=action),
    )
    builder = StateGraph(DemoState)
    builder.add_node("cintara", cintara)
    builder.add_node("tools", execute_tool)
    builder.add_node("human_review", request_approval)
    builder.set_entry_point("cintara")
    builder.add_conditional_edges(
        "cintara",
        cintara.route,
        {
            "allow": "tools",
            "approval": "human_review",
            "deny": END,
            "error": END,
        },
    )
    builder.add_edge("tools", END)
    builder.add_edge("human_review", END)
    return builder.compile()


def run_demo(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "ALLOW").upper()
    if action not in {"ALLOW", "APPROVAL_REQUIRED", "DENY"}:
        action = "ALLOW"

    agent_id = str(payload.get("agent_id") or "agent-demo-langgraph")
    tool_name = str(payload.get("tool_name") or "send_email")
    to_email = str(payload.get("to_email") or "customer@example.com")
    body = str(payload.get("body") or "Hello from Cintara LangGraph.")

    graph = build_demo_graph(agent_id=agent_id, action=action)
    result = graph.invoke(
        {
            "tool_call": {
                "name": tool_name,
                "args": {
                    "to_email": to_email,
                    "body": body,
                },
            },
            "user_id": str(payload.get("user_id") or "local-demo-user"),
            "session_context": {
                "source": "local_demo_app",
            },
        }
    )

    route = (result.get("cintara") or {}).get("route", "error")
    return {
        "workflow": [
            {"step": "agent", "status": "prepared tool call"},
            {"step": "cintara", "status": f"routed: {route}"},
            {
                "step": "tool",
                "status": "executed" if result.get("tool_result") else "not executed",
            },
        ],
        "result": result,
    }


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Cintara LangGraph Demo</title>
    <style>
      :root {
        color-scheme: light;
        --ink: #182018;
        --muted: #667064;
        --line: #dce5d8;
        --panel: rgba(255, 255, 247, 0.92);
        --leaf: #1f7a4d;
        --leaf-dark: #145b39;
        --sand: #f5f0df;
        --cream: #fffdf4;
        --amber: #b96f18;
        --red: #b4352f;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        min-height: 100vh;
        color: var(--ink);
        background:
          radial-gradient(circle at 15% 10%, rgba(62, 143, 91, 0.18), transparent 30rem),
          radial-gradient(circle at 80% 0%, rgba(185, 111, 24, 0.14), transparent 28rem),
          linear-gradient(135deg, #fbf8ea 0%, #eef4e8 52%, #f9f3dc 100%);
        font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      .shell {
        width: min(1120px, calc(100% - 32px));
        margin: 0 auto;
        padding: 36px 0;
      }

      .hero {
        display: grid;
        grid-template-columns: minmax(0, 1.1fr) minmax(300px, 0.9fr);
        gap: 20px;
        align-items: stretch;
      }

      .card {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 28px;
        box-shadow: 0 24px 70px rgba(31, 52, 28, 0.10);
      }

      .intro { padding: 34px; }

      .eyebrow {
        margin: 0 0 12px;
        color: var(--leaf-dark);
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      h1 {
        max-width: 760px;
        margin: 0;
        font-size: clamp(2.4rem, 7vw, 5.4rem);
        line-height: 0.94;
        letter-spacing: -0.07em;
      }

      .lead {
        max-width: 720px;
        margin: 20px 0 0;
        color: var(--muted);
        font-size: 1.04rem;
        line-height: 1.65;
      }

      .diagram {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
        margin-top: 28px;
      }

      .node {
        min-height: 88px;
        padding: 16px;
        border: 1px solid var(--line);
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.62);
      }

      .node strong { display: block; margin-bottom: 8px; }
      .node span { color: var(--muted); font-size: 0.9rem; line-height: 1.4; }

      form {
        display: grid;
        gap: 14px;
        padding: 24px;
      }

      label {
        display: grid;
        gap: 7px;
        color: var(--muted);
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }

      input, select, textarea {
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 15px;
        background: var(--cream);
        color: var(--ink);
        font: inherit;
        padding: 12px 13px;
        outline: none;
      }

      textarea { min-height: 94px; resize: vertical; }
      input:focus, select:focus, textarea:focus { border-color: var(--leaf); box-shadow: 0 0 0 4px rgba(31, 122, 77, 0.13); }

      button {
        border: 0;
        border-radius: 16px;
        background: var(--leaf);
        color: white;
        cursor: pointer;
        font: inherit;
        font-weight: 850;
        padding: 13px 16px;
      }

      button:hover { background: var(--leaf-dark); }

      .output {
        display: grid;
        grid-template-columns: 360px minmax(0, 1fr);
        gap: 20px;
        margin-top: 20px;
      }

      .panel { padding: 24px; }

      .step-list {
        display: grid;
        gap: 12px;
        margin-top: 14px;
      }

      .step {
        padding: 14px;
        border: 1px solid var(--line);
        border-radius: 17px;
        background: rgba(255, 255, 255, 0.55);
      }

      .step strong { display: block; text-transform: capitalize; }
      .step span { color: var(--muted); font-size: 0.92rem; }

      pre {
        overflow: auto;
        min-height: 360px;
        max-height: 560px;
        margin: 14px 0 0;
        padding: 18px;
        border-radius: 18px;
        background: #172017;
        color: #edf6e8;
        font-size: 0.86rem;
        line-height: 1.5;
      }

      .pill {
        display: inline-flex;
        width: fit-content;
        margin-top: 14px;
        padding: 8px 11px;
        border-radius: 999px;
        background: rgba(31, 122, 77, 0.10);
        color: var(--leaf-dark);
        font-size: 0.82rem;
        font-weight: 850;
      }

      .powered-by {
        position: fixed;
        right: 18px;
        bottom: 18px;
        z-index: 20;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border: 1px solid rgba(24, 32, 24, 0.08);
        border-radius: 999px;
        background: rgba(255, 253, 244, 0.94);
        box-shadow: 0 10px 24px rgba(31, 52, 28, 0.12);
        color: #526052;
        font-size: 12px;
        font-weight: 850;
        line-height: 1;
        padding: 8px 12px;
        text-decoration: none;
        backdrop-filter: blur(12px);
      }

      .powered-by img {
        width: 18px;
        height: 18px;
        object-fit: contain;
      }

      @media (max-width: 820px) {
        .hero, .output, .diagram { grid-template-columns: 1fr; }
        .intro { padding: 24px; }
      }
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <article class="card intro">
          <p class="eyebrow">Local LangGraph demo</p>
          <h1>Cintara as one guard step before tools run.</h1>
          <p class="lead">
            This page runs a real LangGraph workflow locally. The agent prepares a tool call,
            Cintara decides the route, and the tool only executes when the guard returns allow.
          </p>
          <div class="diagram" aria-label="Workflow diagram">
            <div class="node"><strong>1. Agent</strong><span>Creates a pending tool call with an agent id.</span></div>
            <div class="node"><strong>2. Cintara</strong><span>Evaluates the action as allow, approval, or deny.</span></div>
            <div class="node"><strong>3. Tool</strong><span>Runs only when Cintara routes the graph to tools.</span></div>
          </div>
        </article>

        <form class="card" id="demo-form">
          <label>Agent ID
            <input name="agent_id" value="agent-demo-langgraph" />
          </label>
          <label>Cintara Decision
            <select name="action">
              <option value="ALLOW">Allow</option>
              <option value="APPROVAL_REQUIRED">Approval required</option>
              <option value="DENY">Deny</option>
            </select>
          </label>
          <label>Tool Name
            <input name="tool_name" value="send_email" />
          </label>
          <label>To Email
            <input name="to_email" value="customer@example.com" />
          </label>
          <label>Body
            <textarea name="body">Hello from Cintara LangGraph.</textarea>
          </label>
          <button type="submit">Run Guarded Workflow</button>
        </form>
      </section>

      <section class="output">
        <article class="card panel">
          <p class="eyebrow">Graph route</p>
          <h2>Workflow steps</h2>
          <div id="steps" class="step-list"></div>
        </article>
        <article class="card panel">
          <p class="eyebrow">State output</p>
          <h2>LangGraph result</h2>
          <pre id="result">{}</pre>
        </article>
      </section>

      <a class="powered-by" href="https://cintara.io" target="_blank" rel="noreferrer" aria-label="Powered by Cintara">
        <span>Powered by Cintara</span>
        <img src="https://apps.cintara.io/govexec-pilot/cintara-logo.png" alt="Cintara logo">
      </a>
    </main>

    <script>
      const form = document.getElementById("demo-form");
      const steps = document.getElementById("steps");
      const result = document.getElementById("result");

      function render(payload) {
        steps.innerHTML = payload.workflow.map((item) => `
          <div class="step">
            <strong>${item.step}</strong>
            <span>${item.status}</span>
          </div>
        `).join("");
        result.textContent = JSON.stringify(payload.result, null, 2);
      }

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        result.textContent = "Running...";
        steps.innerHTML = "";
        const body = Object.fromEntries(new FormData(form).entries());
        const response = await fetch("api/run", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body),
        });
        render(await response.json());
      });

      form.requestSubmit();
    </script>
  </body>
</html>
"""


class DemoHandler(BaseHTTPRequestHandler):
    def _send_index_headers(self) -> bytes:
        encoded = INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return encoded

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_HEAD(self) -> None:
        if self.path not in {"/", "/index.html"}:
            self.send_error(404, "Not found")
            return
        self._send_index_headers()

    def do_GET(self) -> None:
        if self.path not in {"/", "/index.html"}:
            self.send_error(404, "Not found")
            return
        encoded = self._send_index_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        if self.path != "/api/run":
            self.send_error(404, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send_json(200, run_demo(payload))
        except Exception as error:
            self._send_json(500, {"error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[langgraph-demo] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Cintara LangGraph demo app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"Serving Cintara LangGraph demo at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Cintara LangGraph demo.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
