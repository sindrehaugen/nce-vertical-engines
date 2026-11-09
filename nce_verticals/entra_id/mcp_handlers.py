"""
nce_verticals/entra_id/mcp_handlers.py
======================================
MCP tool handlers for the Microsoft Entra ID Identification Point & Allowlist Gate.

Enables an LLM user (e.g. Claude Desktop on a corporate PC) to:
- Check their current verified Microsoft Entra ID identity & PC context (`entra_whoami`)
- Start an interactive OAuth 2.0 Device Code login (`entra_login_device_code`)
- Complete Device Code login and cache their session (`entra_complete_device_login`)
- Verify a bearer token against the company's Entra Security Groups & App Roles (`entra_verify_access`)
- Log out / revoke their cached PC session (`entra_logout`)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from nce_verticals.entra_id.auth import EntraVerificationError
from nce_verticals.entra_id.guard import get_global_entra_gate

log = logging.getLogger("nce_verticals.entra_id.mcp_handlers")


async def handle_entra_whoami(engine: Any, arguments: dict[str, Any]) -> str:
    """Return the active Microsoft Entra ID session and local PC identity context."""
    gate = get_global_entra_gate()
    auth = gate.authenticator
    pc_ctx = auth.get_local_pc_context()

    try:
        principal = await auth.resolve_and_verify_caller(arguments)
        return json.dumps(
            {
                "authenticated": principal is not None,
                "enforce_mode": auth.config.enforce_mode,
                "pc_context": pc_ctx,
                "principal": principal.to_dict() if principal else None,
                "config_summary": auth.config.to_safe_dict(),
            },
            default=str,
        )
    except EntraVerificationError as exc:
        return json.dumps(
            {
                "authenticated": False,
                "enforce_mode": auth.config.enforce_mode,
                "pc_context": pc_ctx,
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
            },
            default=str,
        )


async def handle_entra_login_device_code(engine: Any, arguments: dict[str, Any]) -> str:
    """Start Microsoft Entra ID OAuth 2.0 Device Code flow for interactive LLM/PC sign-in."""
    gate = get_global_entra_gate()
    scopes = arguments.get("scopes")
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.split() if s.strip()]
    try:
        flow_info = await gate.authenticator.start_device_code_flow(scopes=scopes)
        return json.dumps({"status": "pending_user_login", **flow_info}, default=str)
    except EntraVerificationError as exc:
        return json.dumps({"error": str(exc), "error_code": exc.code}, default=str)
    except Exception as exc:
        log.exception("handle_entra_login_device_code failed")
        return json.dumps({"error": str(exc)})


async def handle_entra_complete_device_login(engine: Any, arguments: dict[str, Any]) -> str:
    """Complete a Microsoft Entra ID Device Code flow and verify company group/role membership."""
    device_code = str(arguments.get("device_code") or "").strip()
    if not device_code:
        return json.dumps({"error": "device_code is required"})

    gate = get_global_entra_gate()
    try:
        principal = await gate.authenticator.complete_device_code_flow(device_code)
        gate.record_audit(
            tool_or_route="entra_complete_device_login",
            decision="ALLOW",
            reason=f"Interactive device code login succeeded for {principal.upn}",
            principal=principal,
            namespace_id=str(arguments.get("namespace_id") or ""),
        )
        return json.dumps(
            {
                "status": "authenticated",
                "principal": principal.to_dict(),
            },
            default=str,
        )
    except EntraVerificationError as exc:
        gate.record_audit(
            tool_or_route="entra_complete_device_login",
            decision="DENY",
            reason=f"[{exc.code}] {exc}",
            principal=None,
            namespace_id=str(arguments.get("namespace_id") or ""),
        )
        return json.dumps({"error": str(exc), "error_code": exc.code, "details": exc.details}, default=str)


async def handle_entra_verify_access(engine: Any, arguments: dict[str, Any]) -> str:
    """Explicitly verify an Entra ID token or current PC session against company allowlists."""
    gate = get_global_entra_gate()
    required_role = arguments.get("required_role")
    try:
        principal = await gate.verify_request(
            "entra_verify_access",
            arguments,
            required_role=required_role,
            engine=engine,
        )
        return json.dumps(
            {
                "allowed": True,
                "enforce_mode": gate.config.enforce_mode,
                "principal": principal.to_dict() if principal else None,
            },
            default=str,
        )
    except EntraVerificationError as exc:
        return json.dumps(
            {
                "allowed": False,
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
            },
            default=str,
        )


async def handle_entra_logout(engine: Any, arguments: dict[str, Any]) -> str:
    """Revoke cached Entra ID session for the specified `oid` or active local PC user."""
    gate = get_global_entra_gate()
    oid = str(arguments.get("oid") or "").strip()
    if not oid:
        cached = await gate.authenticator.get_cached_session()
        if cached:
            oid = cached.oid
    if not oid:
        return json.dumps({"status": "no_active_session"})
    removed = gate.authenticator.revoke_session(oid)
    return json.dumps({"status": "revoked" if removed else "not_found", "oid": oid})
