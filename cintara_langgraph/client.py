from __future__ import annotations

import os
import time
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
    """Small HTTP client for the Cintara Trust Control Plane API.

    Auth (unified): the client holds agent credentials (client_id +
    client_secret) and exchanges them at POST /auth/token for a short-lived
    JWT, which is cached and re-exchanged on expiry or a 401. A pre-minted
    `token` may be passed instead (mainly for tests); it is used as-is.
    """

    # Refresh the cached token this many seconds before its reported expiry.
    _TOKEN_SKEW_SECONDS = 30

    def __init__(
        self,
        base_url: str | None = None,
        policy_url: str | None = None,
        gateway_url: str | None = None,
        auth_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
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
        self.auth_url = (
            auth_url
            or os.getenv("CINTARA_AUTH_URL")
            or common_base_url
            or self.base_url
        ).rstrip("/")
        self.client_id = client_id or os.getenv("CINTARA_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("CINTARA_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.getenv("CINTARA_TENANT_ID")
        self.timeout = timeout

        # Pre-minted token (tests / advanced use): used as-is, never refreshed.
        self._static_token = token or os.getenv("CINTARA_API_TOKEN")
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

        if not self.base_url:
            raise ValueError("Cintara base URL is required. Set CINTARA_BASE_URL or pass base_url.")
        if not self._static_token and not (self.client_id and self.client_secret):
            raise ValueError(
                "Cintara credentials are required. Set CINTARA_CLIENT_ID and "
                "CINTARA_CLIENT_SECRET (or pass client_id/client_secret)."
            )
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
    def auth_api_base(self) -> str:
        return self._api_base(self.auth_url)

    # ── Token management ──────────────────────────────────────────────────

    def _exchange_credentials(self) -> str:
        """client_credentials grant → short-lived access token."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.auth_api_base}/auth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            response.raise_for_status()
            data = response.json()
        self._access_token = str(data["access_token"])
        expires_in = int(data.get("expires_in") or 300)
        self._token_expires_at = time.monotonic() + max(
            expires_in - self._TOKEN_SKEW_SECONDS, 30
        )
        return self._access_token

    def _get_token(self, *, force_refresh: bool = False) -> str:
        if self._static_token:
            return self._static_token
        if (
            force_refresh
            or self._access_token is None
            or time.monotonic() >= self._token_expires_at
        ):
            return self._exchange_credentials()
        return self._access_token

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @property
    def headers(self) -> dict[str, str]:
        return self._headers(self._get_token())

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Authenticated request; on 401 re-exchange credentials and retry once."""
        token = self._get_token()
        for attempt in (0, 1):
            headers = self._headers(token)
            if extra_headers:
                headers.update(extra_headers)
            with httpx.Client(timeout=self.timeout) as client:
                if method == "GET":
                    response = client.get(url, headers=headers)
                else:
                    response = client.post(url, headers=headers, json=json_body)
            # getattr: test doubles may not model status_code.
            if (
                getattr(response, "status_code", None) == 401
                and attempt == 0
                and not self._static_token
            ):
                token = self._get_token(force_refresh=True)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("unreachable")  # pragma: no cover

    # ── API surface ───────────────────────────────────────────────────────

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

        response = self._request(
            "POST", f"{self.policy_api_base}/policy/decide", json_body=payload
        )
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
        extra = {"Idempotency-Key": idempotency_key} if idempotency_key else None

        response = self._request(
            "POST",
            f"{self.gateway_api_base}/invoke/",
            json_body=payload,
            extra_headers=extra,
        )
        return response.json()

    def poll(self, request_id: str) -> dict[str, Any]:
        response = self._request(
            "GET", f"{self.gateway_api_base}/invoke/{request_id}/result"
        )
        return response.json()
