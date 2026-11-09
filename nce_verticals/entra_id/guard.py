"""
nce_verticals/entra_id/guard.py
===============================
Execution Gate & Audit Logger for enforcing Microsoft Entra ID identification
and company Security Group / App Role allowlists on MCP tool calls and standalone APIs.
"""

from __future__ import annotations

import collections
import functools
import json
import logging
import time
from typing import Any, Callable

from nce_verticals.entra_id.auth import (
    EntraConfig,
    EntraIDAuthenticator,
    EntraPrincipal,
    EntraVerificationError,
)

log = logging.getLogger("nce_verticals.entra_id.guard")


class EntraSecurityGate:
    """
    Central Entra ID Identification & Allowlist Gate.
    Maintains an in-memory ring buffer of recent audit events and persists to
    PostgreSQL `entra_id_audit_log` / `entra_id_sessions` when a DB pool is attached.
    """

    def __init__(self, authenticator: EntraIDAuthenticator | None = None) -> None:
        self.authenticator = authenticator or EntraIDAuthenticator()
        self._audit_ring: collections.deque[dict[str, Any]] = collections.deque(maxlen=500)

    @property
    def config(self) -> EntraConfig:
        return self.authenticator.config

    def record_audit(
        self,
        *,
        tool_or_route: str,
        decision: str,
        reason: str,
        principal: EntraPrincipal | None = None,
        namespace_id: str | None = None,
    ) -> dict[str, Any]:
        pc = self.authenticator.get_local_pc_context()
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "namespace_id": namespace_id or "default",
            "tool_or_route": tool_or_route,
            "decision": decision,
            "reason": reason,
            "entra_oid": principal.oid if principal else None,
            "upn": principal.upn if principal else None,
            "display_name": principal.display_name if principal else None,
            "pc_hostname": principal.pc_hostname if principal else pc["pc_hostname"],
            "os_username": principal.os_username if principal else pc["os_username"],
            "matched_groups": principal.matched_groups if principal else [],
            "matched_roles": principal.matched_roles if principal else [],
        }
        self._audit_ring.appendleft(entry)
        return entry

    def get_recent_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._audit_ring)[: max(1, min(500, limit))]

    async def verify_request(
        self,
        tool_or_route: str,
        arguments: dict[str, Any] | None = None,
        *,
        required_role: str | None = None,
        engine: Any = None,
    ) -> EntraPrincipal | None:
        """
        Verify that the caller is authenticated with Microsoft Entra ID and belongs
        to the company's allowed Security Groups / App Roles.
        """
        args = arguments or {}
        ns_id = str(args.get("namespace_id") or "")

        try:
            principal = await self.authenticator.resolve_and_verify_caller(args)
            if principal is not None and required_role:
                role_match = any(r.lower() == required_role.lower() for r in principal.matched_roles)
                if not role_match and self.config.enforce_mode == "strict":
                    raise EntraVerificationError(
                        f"Caller '{principal.upn}' lacks required Entra App Role '{required_role}'",
                        code="MISSING_REQUIRED_ROLE",
                    )

            decision = "ALLOW" if principal is not None or self.config.enforce_mode == "disabled" else "AUDIT_WARN"
            reason = (
                f"Verified Entra principal {principal.upn} ({principal.auth_method})"
                if principal
                else f"Allowed under enforce_mode={self.config.enforce_mode}"
            )
            audit_entry = self.record_audit(
                tool_or_route=tool_or_route,
                decision=decision,
                reason=reason,
                principal=principal,
                namespace_id=ns_id,
            )
            await self._persist_audit_if_db(engine, ns_id, audit_entry, principal)
            return principal

        except EntraVerificationError as exc:
            audit_entry = self.record_audit(
                tool_or_route=tool_or_route,
                decision="DENY",
                reason=f"[{exc.code}] {exc}",
                principal=None,
                namespace_id=ns_id,
            )
            await self._persist_audit_if_db(engine, ns_id, audit_entry, None)
            raise

    async def _persist_audit_if_db(
        self,
        engine: Any,
        namespace_id: str,
        audit_entry: dict[str, Any],
        principal: EntraPrincipal | None,
    ) -> None:
        """Best-effort persistence to `entra_id_audit_log` when `engine.pg_pool` is available."""
        if not engine or not getattr(engine, "pg_pool", None) or not namespace_id:
            return
        try:
            from nce.db_utils import scoped_pg_session

            async with scoped_pg_session(engine.pg_pool, namespace_id) as conn:
                await conn.execute(
                    """
                    INSERT INTO entra_id_audit_log (
                        namespace_id, entra_oid, upn, pc_hostname,
                        tool_or_route, decision, reason, matched_groups, matched_roles
                    ) VALUES (
                        $1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb
                    )
                    """,
                    namespace_id,
                    audit_entry.get("entra_oid"),
                    audit_entry.get("upn"),
                    audit_entry.get("pc_hostname"),
                    audit_entry["tool_or_route"],
                    audit_entry["decision"],
                    audit_entry["reason"],
                    json.dumps(audit_entry.get("matched_groups", [])),
                    json.dumps(audit_entry.get("matched_roles", [])),
                )
        except Exception as exc:
            log.debug("Skipping DB audit persistence: %s", exc)


_GLOBAL_GATE: EntraSecurityGate | None = None


def get_global_entra_gate() -> EntraSecurityGate:
    global _GLOBAL_GATE
    if _GLOBAL_GATE is None:
        _GLOBAL_GATE = EntraSecurityGate()
    return _GLOBAL_GATE


def require_entra_identity(required_role: str | None = None) -> Callable:
    """
    Decorator for MCP tool handlers `async (engine, arguments) -> str` that enforces
    the Microsoft Entra ID identification & company allowlist gate before running the tool.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(engine: Any, arguments: dict[str, Any]) -> str:
            gate = get_global_entra_gate()
            try:
                principal = await gate.verify_request(
                    func.__name__,
                    arguments,
                    required_role=required_role,
                    engine=engine,
                )
                if principal is not None and isinstance(arguments, dict):
                    arguments = dict(arguments)
                    arguments["_entra_principal"] = principal
            except EntraVerificationError as exc:
                return json.dumps(
                    {
                        "error": str(exc),
                        "error_code": exc.code,
                        "details": exc.details,
                        "remediation": (
                            "Call 'entra_login_device_code' to sign in with your corporate Microsoft "
                            "Entra ID account, or verify your user is in the authorized Entra Security Group."
                        ),
                    }
                )
            return await func(engine, arguments)

        return wrapper

    return decorator
