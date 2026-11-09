"""
nce_verticals/admin_handlers/salesforce.py
==========================================
Admin HTTP handlers and Webhook receiver routes for the Standalone Salesforce Vertical Engine.
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


from nce_verticals.salesforce.auth import SalesforceAuthConfig
from nce_verticals.salesforce.operations import get_global_salesforce_ops
from nce_verticals.salesforce.sync import SalesforceSyncEngine
from nce_verticals.salesforce.webhooks import SalesforceWebhookReceiver


async def api_admin_salesforce_config(request: Any) -> JSONResponse:
    """GET or POST /api/admin/salesforce/config — return or update current Salesforce configuration & status."""
    if getattr(request, "method", "GET").upper() == "POST":
        return await api_admin_salesforce_config_save(request)
    ops = get_global_salesforce_ops()
    return JSONResponse(
        {
            "config": ops.config.to_safe_dict(),
            "cached_records_count": len(ops._standalone_store),
            "recent_webhooks_count": len(ops._webhook_history),
            "last_sync": ops._last_sync_summary,
        }
    )


async def api_admin_salesforce_config_save(request: Any) -> JSONResponse:
    """POST /api/admin/salesforce/config — update Salesforce auth mode, URLs, and sync settings."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    ops = get_global_salesforce_ops()
    curr = ops.config

    auth_mode = str(body.get("auth_mode", curr.auth_mode)).strip().lower()
    if auth_mode not in (
        "client_credentials",
        "refresh_token",
        "jwt_bearer",
        "entra_delegated",
    ):
        return JSONResponse(
            {
                "error": "auth_mode must be client_credentials, refresh_token, jwt_bearer, or entra_delegated"
            },
            status_code=422,
        )

    sync_objs = body.get("sync_objects", curr.sync_objects)
    if isinstance(sync_objs, str):
        sync_objs = [s.strip() for s in sync_objs.split(",") if s.strip()]

    updated = SalesforceAuthConfig(
        enabled=bool(body.get("enabled", curr.enabled)),
        instance_url=str(body.get("instance_url", curr.instance_url))
        .strip()
        .rstrip("/"),
        login_url=str(body.get("login_url", curr.login_url)).strip().rstrip("/"),
        api_version=str(body.get("api_version", curr.api_version)).strip(),
        auth_mode=auth_mode,
        client_id=str(body.get("client_id", curr.client_id)).strip(),
        client_secret=str(body["client_secret"]).strip()
        if body.get("client_secret")
        else curr.client_secret,
        refresh_token=str(body["refresh_token"]).strip()
        if body.get("refresh_token")
        else curr.refresh_token,
        jwt_subject=str(body.get("jwt_subject", curr.jwt_subject)).strip(),
        jwt_private_key=str(body["jwt_private_key"]).strip()
        if body.get("jwt_private_key")
        else curr.jwt_private_key,
        static_access_token=(
            str(body["static_access_token"]).strip()
            if body.get("static_access_token")
            else curr.static_access_token
        ),
        webhook_secret=str(body["webhook_secret"]).strip()
        if body.get("webhook_secret")
        else curr.webhook_secret,
        standalone_passthrough=bool(
            body.get("standalone_passthrough", curr.standalone_passthrough)
        ),
        sync_enabled=bool(body.get("sync_enabled", curr.sync_enabled)),
        require_entra_gate=bool(
            body.get("require_entra_gate", curr.require_entra_gate)
        ),
        sync_objects=list(sync_objs),
    )
    ops.token_manager.config = updated
    ops.token_manager.invalidate()
    return JSONResponse({"status": "ok", "config": updated.to_safe_dict()})


async def api_admin_salesforce_records(request: Any) -> JSONResponse:
    """GET or POST /api/admin/salesforce/records — list cached/SOQL records or mutate a record."""
    if getattr(request, "method", "GET").upper() == "POST":
        return await api_admin_salesforce_mutate(request)
    ops = get_global_salesforce_ops()
    qp = request.query_params
    sobject = qp.get("sobject")
    soql = qp.get("soql")
    limit = int(qp.get("limit", 50))

    try:
        if soql:
            res = await ops.query_soql(soql, max_records=limit)
            return JSONResponse(res)
        items = ops.list_cached_records(sobject=sobject, limit=limit)
        return JSONResponse({"total": len(items), "items": items})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_salesforce_mutate(request: Any) -> JSONResponse:
    """POST /api/admin/salesforce/records — create, update, or delete a Salesforce SObject record."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    sobject = str(body.get("sobject") or "Account").strip()
    action = str(body.get("action") or "create").strip().lower()
    record_id = body.get("record_id") or body.get("id")
    payload = body.get("payload") or body.get("data") or {}

    ops = get_global_salesforce_ops()
    try:
        res = await ops.manage_crm_entity(
            sobject,
            action,
            record_id=record_id,
            payload=payload,
        )
        return JSONResponse(res)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_salesforce_sync_now(request: Any) -> JSONResponse:
    """POST /api/admin/salesforce/sync — trigger immediate sync."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    ops = get_global_salesforce_ops()
    sync_engine = SalesforceSyncEngine(ops=ops)
    try:
        summary = await sync_engine.run_sync(
            sobject_types=body.get("sobject_types"),
            since_iso=body.get("since_iso"),
        )
        return JSONResponse({"status": "ok", "sync": summary})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_salesforce_webhook_ingest(request: Any) -> JSONResponse:
    """POST /api/webhooks/salesforce — receive Salesforce Outbound Messages / Platform Events."""
    ops = get_global_salesforce_ops()
    receiver = SalesforceWebhookReceiver(ops=ops)
    raw_body = await request.body()
    sig = request.headers.get("X-Salesforce-Signature") or request.headers.get(
        "x-salesforce-signature"
    )

    if not receiver.verify_signature(raw_body, sig):
        return JSONResponse(
            {"error": "Invalid X-Salesforce-Signature"}, status_code=401
        )

    content_type = request.headers.get("Content-Type", "application/json")
    try:
        events = receiver.parse_payload(raw_body, content_type=content_type)
        stats = receiver.process_events(events)
        return JSONResponse({"status": "ok", **stats})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_salesforce_webhooks(request: Any) -> JSONResponse:
    """GET /api/admin/salesforce/webhooks — list recent received Salesforce webhook events."""
    ops = get_global_salesforce_ops()
    return JSONResponse(
        {"total": len(ops._webhook_history), "items": ops._webhook_history[:100]}
    )
