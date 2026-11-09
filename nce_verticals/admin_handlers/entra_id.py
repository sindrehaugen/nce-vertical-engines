"""
nce_verticals/admin_handlers/entra_id.py
========================================
Admin HTTP handlers for the Microsoft Entra ID Identification Point & Allowlist Gate.
"""

from __future__ import annotations

from typing import Any

try:
    from starlette.responses import JSONResponse
except ImportError:
    import json as _json

    class JSONResponse:  # type: ignore[no-redef]
        def __init__(self, content: Any, status_code: int = 200) -> None:
            self.content = content
            self.status_code = status_code
            self.body = _json.dumps(content, default=str).encode("utf-8")


from nce_verticals.entra_id.auth import EntraConfig, EntraVerificationError
from nce_verticals.entra_id.guard import get_global_entra_gate


def _parse_str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


async def api_admin_entra_config(request: Any) -> JSONResponse:
    """GET or POST /api/admin/entra/config — return or update Entra ID gate config & PC context."""
    if getattr(request, "method", "GET").upper() == "POST":
        return await api_admin_entra_config_save(request)
    gate = get_global_entra_gate()
    return JSONResponse(
        {
            "config": gate.config.to_safe_dict(),
            "pc_context": gate.authenticator.get_local_pc_context(),
            "active_sessions_count": len(gate.authenticator.list_active_sessions()),
        }
    )


async def api_admin_entra_config_save(request: Any) -> JSONResponse:
    """POST /api/admin/entra/config — update Entra ID gate configuration & company allowlists."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    gate = get_global_entra_gate()
    curr = gate.config

    enforce_mode = str(body.get("enforce_mode", curr.enforce_mode)).strip().lower()
    if enforce_mode not in ("strict", "audit_only", "disabled"):
        return JSONResponse(
            {"error": "enforce_mode must be strict, audit_only, or disabled"},
            status_code=422,
        )

    new_secret = body.get("client_secret")
    client_secret = str(new_secret).strip() if new_secret else curr.client_secret

    updated = EntraConfig(
        entra_tenant_id=str(body.get("entra_tenant_id", curr.entra_tenant_id)).strip(),
        client_id=str(body.get("client_id", curr.client_id)).strip(),
        client_secret=client_secret,
        enforce_mode=enforce_mode,
        allowed_group_ids=_parse_str_list(
            body.get("allowed_group_ids", curr.allowed_group_ids)
        ),
        allowed_app_roles=_parse_str_list(
            body.get("allowed_app_roles", curr.allowed_app_roles)
        ),
        allowed_upns=[
            u.lower()
            for u in _parse_str_list(body.get("allowed_upns", curr.allowed_upns))
        ],
        blocked_upns=[
            u.lower()
            for u in _parse_str_list(body.get("blocked_upns", curr.blocked_upns))
        ],
        require_graph_check=bool(
            body.get("require_graph_check", curr.require_graph_check)
        ),
        allow_os_silent_auth=bool(
            body.get("allow_os_silent_auth", curr.allow_os_silent_auth)
        ),
        allow_device_code_flow=bool(
            body.get("allow_device_code_flow", curr.allow_device_code_flow)
        ),
        session_ttl_seconds=max(
            300,
            min(86400, int(body.get("session_ttl_seconds", curr.session_ttl_seconds))),
        ),
    )
    gate.authenticator.update_config(updated)
    gate.record_audit(
        tool_or_route="api_admin_entra_config_save",
        decision="ALLOW",
        reason=f"Admin updated Entra ID config (enforce_mode={updated.enforce_mode})",
    )
    return JSONResponse({"status": "ok", "config": updated.to_safe_dict()})


async def api_admin_entra_sessions(request: Any) -> JSONResponse:
    """GET /api/admin/entra/sessions — list active verified PC / LLM user sessions."""
    gate = get_global_entra_gate()
    sessions = gate.authenticator.list_active_sessions()
    return JSONResponse({"total": len(sessions), "items": sessions})


async def api_admin_entra_revoke_session(request: Any) -> JSONResponse:
    """POST /api/admin/entra/sessions/revoke — revoke a cached Entra ID session by oid."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    oid = str(body.get("oid") or "").strip()
    if not oid:
        return JSONResponse({"error": "oid is required"}, status_code=422)

    gate = get_global_entra_gate()
    removed = gate.authenticator.revoke_session(oid)
    gate.record_audit(
        tool_or_route="api_admin_entra_revoke_session",
        decision="ALLOW",
        reason=f"Admin revoked session for oid={oid} (removed={removed})",
    )
    return JSONResponse({"status": "ok", "oid": oid, "removed": removed})


async def api_admin_entra_verify_user(request: Any) -> JSONResponse:
    """POST /api/admin/entra/verify-user — test token or silent PC identity against company allowlist."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    gate = get_global_entra_gate()
    try:
        principal = await gate.verify_request("api_admin_entra_verify_user", body)
        return JSONResponse(
            {
                "allowed": True,
                "enforce_mode": gate.config.enforce_mode,
                "principal": principal.to_dict() if principal else None,
                "pc_context": gate.authenticator.get_local_pc_context(),
            }
        )
    except EntraVerificationError as exc:
        return JSONResponse(
            {
                "allowed": False,
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
                "pc_context": gate.authenticator.get_local_pc_context(),
            },
            status_code=403,
        )


async def api_admin_entra_audit(request: Any) -> JSONResponse:
    """GET /api/admin/entra/audit — return recent Entra ID gate allow/deny audit entries."""
    gate = get_global_entra_gate()
    limit = 100
    try:
        limit = int(request.query_params.get("limit", 100))
    except Exception:
        pass
    items = gate.get_recent_audit_log(limit=limit)
    return JSONResponse({"total": len(items), "items": items})
