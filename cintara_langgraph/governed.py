"""Additive fail-closed path. Resume values are never execution authority."""

from dataclasses import dataclass
from typing import Any, Mapping
from .client import CintaraClient
from .models import CintaraToolCall


@dataclass
class GovernedWorkflow:
    client: CintaraClient
    agent_id: str
    tool_name: str

    def checked_call(self, state: Mapping[str, Any]) -> CintaraToolCall:
        messages = state.get("messages") or []
        latest = messages[-1] if messages else {}
        calls = (
            latest.get("tool_calls", [])
            if isinstance(latest, Mapping)
            else getattr(latest, "tool_calls", [])
        )
        explicit = state.get("tool_call")
        if calls and (len(calls) != 1 or explicit):
            raise ValueError(
                "Exactly one configured tool call is supported; no unchecked additional calls."
            )
        if not explicit and len(calls) != 1:
            raise ValueError("Provide exactly one tool call.")
        call = CintaraToolCall.from_raw(explicit or calls[0])
        if call.name != self.tool_name:
            raise ValueError("Tool is outside this workflow's configured scope.")
        return call

    def submit(
        self, state: Mapping[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        if not 8 <= len(idempotency_key) <= 128:
            raise ValueError("Persist an idempotency key before submitting.")
        call = self.checked_call(state)
        return self.client.invoke(
            agent_id=self.agent_id, tool_call=call, idempotency_key=idempotency_key
        )

    def advance(self, state: Mapping[str, Any], *, request_id: str) -> dict[str, Any]:
        """Poll actual approval, then reauthorize and execute the showcase sandbox.

        Persist request_id in your LangGraph checkpoint. Repeated advance calls use
        the same server-side task identity. A local approved=True value is ignored.
        """
        call = self.checked_call(state)
        result = self.client.poll(request_id)
        if result.get("execution_outcome"):
            return {
                "status": "recorded",
                "request_id": request_id,
                "outcome": result["execution_outcome"],
            }
        if result.get("status") == "PENDING_APPROVAL":
            return {"status": "awaiting_reviewer", "request_id": request_id}
        if result.get("status") != "COMPLETED" or result.get("decision") not in (
            "ALLOW",
            "APPROVED",
        ):
            return {
                "status": "blocked",
                "request_id": request_id,
                "decision": result.get("decision"),
            }
        grant = self.client.authorize_execution(request_id, tool_call=call)
        if grant.get("authorized") is not True or grant.get("request_id") != request_id:
            raise RuntimeError("No valid server execution authorization.")
        receipt = self.client.execute_sandbox(request_id, tool_call=call)
        self.client.record_outcome(request_id, outcome="succeeded", result=receipt)
        return {"status": "executed", "request_id": request_id, "receipt": receipt}

    def node(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """A LangGraph node: checkpoint a stable key before entering this node.

        Resuming the interrupt only asks the server again. Its local value never
        grants permission. Route the result to END; do not append an unchecked
        ToolNode, since this node executes the single configured sandbox tool.
        """
        request_id = state.get("cintara_request_id")
        if not request_id:
            key = state.get("cintara_idempotency_key")
            if not isinstance(key, str):
                raise ValueError(
                    "Checkpoint cintara_idempotency_key before the governed node."
                )
            request_id = self.submit(state, idempotency_key=key)["request_id"]
        result = self.advance(state, request_id=str(request_id))
        if result["status"] == "awaiting_reviewer":
            from langgraph.types import interrupt

            interrupt({"type": "cintara_review_required", "request_id": request_id})
            result = self.advance(state, request_id=str(request_id))
        return {"cintara_request_id": str(request_id), "cintara": result}
