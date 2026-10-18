"""Run in your server environment after loading .env.cintara. Never in a browser.

CINTARA_CASE: allow | review | block. Persist CINTARA_RUN_KEY per logical action.
CINTARA_REQUEST_ID resumes a submitted request after the authorized reviewer acts.
"""
import os
import json
from cintara_langgraph import CintaraClient, GovernedWorkflow

case = os.getenv("CINTARA_CASE", "allow")
if case not in ("allow", "review", "block"):
    raise ValueError("CINTARA_CASE must be allow, review or block")
workflow = GovernedWorkflow(client=CintaraClient(), agent_id=os.environ["CINTARA_AGENT_ID"], tool_name="showcase_obligation_task")
state = {"tool_call": {"name": "showcase_obligation_task", "args": {
    "classification": "restricted" if case == "block" else "public",
    "destination": "external" if case == "block" else "private",
    "action": "approve_payment" if case == "review" else "create_task",
    "obligation": {"requirement": "Synthetic pilot obligation"},
}}}
request_id = os.getenv("CINTARA_REQUEST_ID")
if not request_id:
    submitted = workflow.submit(state, idempotency_key=os.environ["CINTARA_RUN_KEY"])
    request_id = submitted["request_id"]
    print("Persist CINTARA_REQUEST_ID:", request_id)
print(json.dumps(workflow.advance(state, request_id=request_id), indent=2))
