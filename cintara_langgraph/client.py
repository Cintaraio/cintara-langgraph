from __future__ import annotations

import os
from typing import Any

import httpx

from .models import CintaraDecision, CintaraToolCall


def _list_from_context(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, (tuple, set)):
        return [str(item) for item in value]
    return []


class CintaraClient:
    """Small HTTP client for the Cintara Trust Control Plane API."""

    def __init__(
        self,
        base_url: str | None = None,
        policy_url: str | None = None,
        gateway_url: str | None = None,
        token: str | None = None,
        tenant_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        common_base_url = base_url or os.getenv("CINTARA_BASE_URL") or ""
        self.base_url = (
            policy_url
            or os.getenv("CINTARA_POLICY_URL")
            or common_base_url
        ).rstrip("/")
        self.gateway_url = (
            gateway_url
            or os.getenv("CINTARA_GATEWAY_URL")
            or common_base_url
            or self.base_url
        ).rstrip("/")
        self.token = token or os.getenv("CINTARA_API_TOKEN")
        self.tenant_id = tenant_id or os.getenv("CINTARA_TENANT_ID")
        self.timeout = timeout

        if not self.base_url:
            raise ValueError("Cintara base URL is required. Set CINTARA_BASE_URL or pass base_url.")
        if not self.token:
            raise ValueError("Cintara API token is required. Set CINTARA_API_TOKEN or pass token.")
        if not self.tenant_id:
            raise ValueError("Cintara tenant ID is required. Set CINTARA_TENANT_ID or pass tenant_id.")

    @staticmethod
    def _api_base(url: str) -> str:
        if url.endswith("/api/v1"):
            return url
        return f"{url}/api/v1"

    @property
    def api_base(self) -> str:
        return self.policy_api_base

    @property
    def policy_api_base(self) -> str:
        return self._api_base(self.base_url)

    @property
    def gateway_api_base(self) -> str:
        return self._api_base(self.gateway_url)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def build_request_context(
        self,
        *,
        user_id: str,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = session_context or {}
        return {
            "user": {
                "id": user_id,
                "email": str(context.get("user_email") or context.get("email") or ""),
                "roles": _list_from_context(context.get("user_roles") or context.get("roles")),
                "privileges": _list_from_context(
                    context.get("user_privileges") or context.get("privileges")
                ),
            },
            "tenant": {
                "id": self.tenant_id,
            },
            "request": {
                "ip_address": str(context.get("request_ip") or context.get("ip_address") or ""),
                "user_agent": str(context.get("user_agent") or ""),
            },
            "context_version": "v1",
        }

    def decide(
        self,
        *,
        agent_id: str,
        tool_call: CintaraToolCall,
        user_id: str = "langgraph-user",
        operation_type: str = "WRITE",
        tool_risk_tier: str = "WRITE",
        agent_group: str | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> CintaraDecision:
        payload = {
            "agent_id": agent_id,
            "tenant_id": self.tenant_id,
            "user_id": user_id,
            "user_email": str((session_context or {}).get("user_email") or ""),
            "user_roles": _list_from_context((session_context or {}).get("user_roles")),
            "request_ip": str((session_context or {}).get("request_ip") or ""),
            "operation_type": operation_type,
            "agent_group": agent_group,
            "tool_name": tool_call.name,
            "tool_risk_tier": tool_risk_tier,
            "parameters": tool_call.args,
            "context": self.build_request_context(
                user_id=user_id,
                session_context=session_context,
            ),
            "session_context": session_context or {},
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.policy_api_base}/policy/decide",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()

        return CintaraDecision.from_api(response.json())

    def invoke(
        self,
        *,
        agent_id: str,
        tool_call: CintaraToolCall,
        user_id: str = "langgraph-user",
        operation_type: str = "WRITE",
        agent_group: str | None = None,
        session_context: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "agent_id": agent_id,
            "user_id": user_id,
            "operation_type": operation_type,
            "tool_name": tool_call.name,
            "parameters": tool_call.args,
            "agent_group": agent_group,
            "session_context": session_context or {},
        }
        headers = dict(self.headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.gateway_api_base}/invoke/",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def poll(self, request_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.gateway_api_base}/invoke/{request_id}/result",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
