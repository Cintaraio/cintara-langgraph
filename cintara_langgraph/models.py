from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class CintaraToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    @classmethod
    def from_raw(cls, value: Any) -> "CintaraToolCall":
        if not isinstance(value, Mapping):
            raise ValueError("Tool call must be a mapping.")

        function = value.get("function") or {}
        name = value.get("name") or value.get("tool_name") or function.get("name")
        args = value.get("args") or value.get("arguments") or value.get("parameters") or function.get("arguments") or {}
        call_id = value.get("id") or value.get("tool_call_id")

        if isinstance(args, str):
            import json

            args = json.loads(args)

        if not name:
            raise ValueError("Tool call is missing a name.")
        if not isinstance(args, dict):
            raise ValueError("Tool call args must be a dictionary.")

        return cls(name=str(name), args=args, id=str(call_id) if call_id else None)

    def to_dict(self) -> dict[str, Any]:
        payload = {"name": self.name, "args": self.args}
        if self.id:
            payload["id"] = self.id
        return payload


@dataclass(frozen=True)
class CintaraDecision:
    action: str
    reason: str
    request_id: str | None = None
    violations: list[dict[str, Any]] = field(default_factory=list)
    obligations: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> "CintaraDecision":
        return cls(
            action=str(payload.get("action") or "DENY"),
            reason=str(payload.get("reason") or ""),
            request_id=str(payload.get("request_id")) if payload.get("request_id") else None,
            violations=list(payload.get("violations") or []),
            obligations=list(payload.get("obligations") or []),
            raw=dict(payload),
        )

    @classmethod
    def allow(cls, reason: str = "Allowed by Cintara.", raw: dict[str, Any] | None = None) -> "CintaraDecision":
        payload = raw or {"action": "ALLOW", "reason": reason}
        return cls(action="ALLOW", reason=reason, raw=payload)

    @classmethod
    def deny(cls, reason: str = "Denied by Cintara.", raw: dict[str, Any] | None = None) -> "CintaraDecision":
        payload = raw or {"action": "DENY", "reason": reason}
        return cls(action="DENY", reason=reason, raw=payload)

    @property
    def allowed(self) -> bool:
        return self.action == "ALLOW"

    @property
    def route(self) -> str:
        if self.action == "ALLOW":
            return "allow"
        if self.action == "APPROVAL_REQUIRED":
            return "approval"
        return "deny"
