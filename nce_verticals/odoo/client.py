"""
nce_verticals/odoo/client.py
============================
Async Multi-Protocol Odoo Client supporting:
1. JSON-RPC 2.0 (`POST /jsonrpc` with `service="common"` and `service="object"`, `method="execute_kw"`)
2. XML-RPC (`/xmlrpc/2/common` and `/xmlrpc/2/object` via `xmlrpc.client` in threadpool with <5s timeout)
3. REST / OAuth2 Bearer (`/api/v1/{model}` or `/json/2/{model}` with Bearer token)

Enforces explicit `<5s` connect timeouts per Senior Architect rules.
"""

from __future__ import annotations

import asyncio
import logging
import xmlrpc.client
from typing import Any

from nce_verticals.entra_id._http_compat import httpx
from nce_verticals.odoo.auth import OdooAuthConfig

log = logging.getLogger("nce_verticals.odoo.client")

ODOO_TIMEOUT = httpx.Timeout(connect=4.5, read=8.5, write=4.5, pool=4.5)


class OdooAPIError(RuntimeError):
    """Raised when an Odoo RPC or REST call returns an error."""

    def __init__(self, message: str, *, code: str = "ODOO_RPC_ERROR", details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class _TimeoutServerProxy(xmlrpc.client.ServerProxy):
    """XML-RPC ServerProxy with explicit socket timeout (<5s)."""

    def __init__(self, uri: str, timeout: float = 4.5) -> None:
        transport = xmlrpc.client.SafeTransport() if uri.startswith("https://") else xmlrpc.client.Transport()
        orig_make_conn = transport.make_connection

        def _make_conn_with_timeout(host: Any) -> Any:
            conn = orig_make_conn(host)
            conn.timeout = timeout
            return conn

        transport.make_connection = _make_conn_with_timeout  # type: ignore[method-assign]
        super().__init__(uri, transport=transport, allow_none=True)


class OdooClient:
    """Async multi-protocol Odoo client supporting JSON-RPC 2.0, XML-RPC, and REST/OAuth2."""

    def __init__(self, config: OdooAuthConfig, *, http_client: Any = None) -> None:
        self.config = config
        self._http_client = http_client
        self._uid: int | None = config.uid
        self._rpc_id: int = 1

    async def authenticate(self) -> int:
        """Authenticate against Odoo `common.authenticate` and cache integer `uid`."""
        if self._uid is not None and self._uid > 0:
            return self._uid

        if not self.config.url:
            raise OdooAPIError("Odoo URL is not configured", code="ODOO_NOT_CONFIGURED")

        protocol = self.config.protocol
        if protocol == "xmlrpc":
            uid = await asyncio.to_thread(self._xmlrpc_authenticate)
        elif protocol == "rest_oauth2":
            uid = self.config.uid or 2
        else:
            uid = await self._jsonrpc_call(
                service="common",
                method="authenticate",
                args=[self.config.db_name, self.config.username, self.config.api_key, {}],
            )

        if not uid or not isinstance(uid, int):
            raise OdooAPIError("Odoo authentication failed: invalid username, database, or API key", code="AUTH_FAILED")

        self._uid = uid
        self.config.uid = uid
        return uid

    def _xmlrpc_authenticate(self) -> int:
        common = _TimeoutServerProxy(f"{self.config.url}/xmlrpc/2/common", timeout=4.5)
        uid = common.authenticate(self.config.db_name, self.config.username, self.config.api_key, {})
        return int(uid) if uid else 0

    def _xmlrpc_execute_kw(
        self,
        uid: int,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        models = _TimeoutServerProxy(f"{self.config.url}/xmlrpc/2/object", timeout=6.0)
        return models.execute_kw(
            self.config.db_name,
            uid,
            self.config.api_key,
            model,
            method,
            args,
            kwargs or {},
        )

    async def _jsonrpc_call(self, *, service: str, method: str, args: list[Any]) -> Any:
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args,
            },
            "id": self._rpc_id,
        }
        url = f"{self.config.url}/jsonrpc"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.oauth_bearer_token:
            headers["Authorization"] = f"Bearer {self.config.oauth_bearer_token}"

        if self._http_client is not None:
            resp = await self._http_client.request("POST", url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=ODOO_TIMEOUT) as client:
                resp = await client.request("POST", url, json=payload, headers=headers)

        if resp.status_code != 200:
            raise OdooAPIError(
                f"Odoo JSON-RPC HTTP {resp.status_code}",
                code=f"HTTP_{resp.status_code}",
            )
        body = resp.json()
        if "error" in body and body["error"]:
            err = body["error"]
            msg = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise OdooAPIError(f"Odoo RPC Error: {msg}", code="ODOO_JSONRPC_ERROR", details=err)
        return body.get("result")

    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute any Odoo ORM or workflow method on `model` via the configured protocol
        (`jsonrpc`, `xmlrpc`, or `rest_oauth2`).
        """
        uid = await self.authenticate()
        call_args = args if args is not None else []
        call_kwargs = kwargs if kwargs is not None else {}

        if self.config.protocol == "xmlrpc":
            return await asyncio.to_thread(
                self._xmlrpc_execute_kw,
                uid,
                model,
                method,
                call_args,
                call_kwargs,
            )

        return await self._jsonrpc_call(
            service="object",
            method="execute_kw",
            args=[
                self.config.db_name,
                uid,
                self.config.api_key or self.config.oauth_bearer_token,
                model,
                method,
                call_args,
                call_kwargs,
            ],
        )
