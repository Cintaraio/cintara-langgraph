from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .client import CintaraClient
from .models import CintaraDecision, CintaraToolCall


def _mapping_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def extract_tool_call(state: Mapping[str, Any]) -> CintaraToolCall:
    """Extract a tool call from explicit state or LangChain-style messages."""

    explicit = state.get("tool_call") or state.get("cintara_tool_call")
    if explicit:
        return CintaraToolCall.from_raw(explicit)

    messages = state.get("messages") or []
    if not messages:
        raise ValueError("No tool call found. Provide state['tool_call'] or a message with tool_calls.")

    latest_message = messages[-1]
    tool_calls = _mapping_get(latest_message, "tool_calls", []) or []
    if not tool_calls:
        raise ValueError("Latest message does not contain tool_calls.")

    return CintaraToolCall.from_raw(tool_calls[0])


@dataclass
class CintaraGuard:
    """Callable LangGraph node that gates the next tool call through Cintara."""

    agent_id: str
    client: CintaraClient | None = None
    base_url: str | None = None
    token: str | None = None
    tenant_id: str | None = None
    user_id: str = "langgraph-user"
    operation_type: str = "WRITE"
    tool_risk_tier: str = "WRITE"
    agent_group: str | None = None
    interrupt_on_approval: bool = False
    fail_closed: bool = True
    tool_call_extractor: Callable[[Mapping[str, Any]], CintaraToolCall] = extract_tool_call
    _client: CintaraClient = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = self.client or CintaraClient(
            base_url=self.base_url,
            token=self.token,
            tenant_id=self.tenant_id,
        )

    def node(self, state: Mapping[str, Any]) -> dict[str, Any]:
        tool_call = self.tool_call_extractor(state)
        session_context = dict(state.get("session_context") or {})
        user_id = str(state.get("user_id") or self.user_id)

        try:
            decision = self._client.decide(
                agent_id=self.agent_id,
                tool_call=tool_call,
                user_id=user_id,
                operation_type=str(state.get("operation_type") or self.operation_type),
                tool_risk_tier=str(state.get("tool_risk_tier") or self.tool_risk_tier),
                agent_group=state.get("agent_group") or self.agent_group,
                session_context=session_context,
            )
        except Exception as error:
            if not self.fail_closed:
                return self._state_update(
                    tool_call,
                    CintaraDecision.allow(reason=f"Cintara unavailable: {error}"),
                    route="allow",
                    error=str(error),
                )
            return self._state_update(
                tool_call,
                CintaraDecision.deny(reason=f"Cintara unavailable: {error}"),
                route="error",
                error=str(error),
            )

        if decision.action == "APPROVAL_REQUIRED" and self.interrupt_on_approval:
            decision = self._interrupt_for_approval(tool_call, decision)

        return self._state_update(tool_call, decision)

    __call__ = node

    def route(self, state: Mapping[str, Any]) -> str:
        cintara_state = state.get("cintara") or {}
        return str(cintara_state.get("route") or "error")

    def _interrupt_for_approval(
        self,
        tool_call: CintaraToolCall,
        decision: CintaraDecision,
    ) -> CintaraDecision:
        try:
            from langgraph.types import interrupt
        except ImportError as exc:
            raise RuntimeError(
                "Install cintara-langgraph[langgraph] to use interrupt_on_approval."
            ) from exc

        resume_value = interrupt(
            {
                "type": "cintara_approval_required",
                "tool_call": tool_call.to_dict(),
                "decision": decision.raw,
                "reason": decision.reason,
                "obligations": decision.obligations,
            }
        )

        approved = bool(
            resume_value is True
            or (
                isinstance(resume_value, Mapping)
                and resume_value.get("approved") is True
            )
        )
        if approved:
            return CintaraDecision.allow(
                reason="Approved through LangGraph interrupt.",
                raw={**decision.raw, "langgraph_resume": dict(resume_value) if isinstance(resume_value, Mapping) else resume_value},
            )
        return CintaraDecision.deny(
            reason="Rejected through LangGraph interrupt.",
            raw={**decision.raw, "langgraph_resume": dict(resume_value) if isinstance(resume_value, Mapping) else resume_value},
        )

    def _state_update(
        self,
        tool_call: CintaraToolCall,
        decision: CintaraDecision,
        route: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        selected_route = route or decision.route
        payload = {
            "allowed": decision.allowed,
            "route": selected_route,
            "action": decision.action,
            "reason": decision.reason,
            "request_id": decision.request_id,
            "decision": decision.raw,
            "tool_call": tool_call.to_dict(),
        }
        if error:
            payload["error"] = error
        return {"cintara": payload}
