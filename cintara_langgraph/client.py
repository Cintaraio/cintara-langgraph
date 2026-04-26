from __future__ import annotations

import os
from typing import Any

import httpx

from .models import CintaraDecision, CintaraToolCall


class CintaraClient:
    """Small HTTP client for the Cintara Trust Control Plane API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        tenant_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("CINTARA_BASE_URL") or "").rstrip("/")
        self.token = token or os.getenv("CINTARA_API_TOKEN")
        self.tenant_id = tenant_id or os.getenv("CINTARA_TENANT_ID")
        self.timeout = timeout

        if not self.base_url:
            raise ValueError("Cintara base URL is required. Set CINTARA_BASE_URL or pass base_url.")
        if not self.token:
            raise ValueError("Cintara API token is required. Set CINTARA_API_TOKEN or pass token.")
        if not self.tenant_id:
            raise ValueError("Cintara tenant ID is required. Set CINTARA_TENANT_ID or pass tenant_id.")

    @property
    def api_base(self) -> str:
        if self.base_url.endswith("/api/v1"):
            return self.base_url
        return f"{self.base_url}/api/v1"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
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
            "operation_type": operation_type,
            "agent_group": agent_group,
            "tool_name": tool_call.name,
            "tool_risk_tier": tool_risk_tier,
            "parameters": tool_call.args,
            "session_context": session_context or {},
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.api_base}/policy/decide",
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
                f"{self.api_base}/invoke/",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def poll(self, request_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.api_base}/invoke/{request_id}/result",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
