"""
nce_verticals/admin_handlers/odoo.py
====================================
Admin HTTP handlers and Webhook receiver routes for the Standalone Super-Intelligent
Odoo Vertical Engine & Full LLM Cross-Talker.
"""

from __future__ import annotations

from typing import Any

from nce_verticals.odoo.auth import OdooAuthConfig
from nce_verticals.odoo.crosstalk import OdooLLMCrossTalker
from nce_verticals.odoo.intelligence import OdooSuperIntelligence
from nce_verticals.odoo.operations import get_global_odoo_ops
from nce_verticals.odoo.sync import OdooSyncEngine
from nce_verticals.odoo.webhooks import OdooWebhookReceiver

try:
    from starlette.responses import JSONResponse
except ImportError:
    import json as _json

    class JSONResponse:  # type: ignore[no-redef]
        def __init__(self, content: Any, status_code: int = 200) -> None:
            self.content = content
            self.status_code = status_code
            self.body = _json.dumps(content, default=str).encode("utf-8")


async def api_admin_odoo_config(request: Any) -> JSONResponse:
    """GET or POST /api/admin/odoo/config — return or update Odoo config, model record counts, and Cross-Talk stats."""
    if getattr(request, "method", "GET").upper() == "POST":
        return await api_admin_odoo_config_save(request)
    ops = get_global_odoo_ops()
    model_counts = {m: len(recs) for m, recs in ops._store.items()}
    return JSONResponse(
        {
            "config": ops.config.to_safe_dict(),
            "model_record_counts": model_counts,
            "crosstalk_count": len(ops._crosstalk_history),
            "webhook_count": len(ops._webhook_history),
            "last_sync": getattr(ops, "_last_sync_summary", None),
        }
    )


async def api_admin_odoo_config_save(request: Any) -> JSONResponse:
    """POST /api/admin/odoo/config — update Odoo protocol, URL, DB, Entra Gate & Cross-Talk settings."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    ops = get_global_odoo_ops()
    curr = ops.config

    protocol = str(body.get("protocol", curr.protocol)).strip().lower()
    if protocol not in ("jsonrpc", "xmlrpc", "rest_oauth2"):
        return JSONResponse({"error": "protocol must be jsonrpc, xmlrpc, or rest_oauth2"}, status_code=422)

    synced = body.get("synced_models", curr.synced_models)
    if isinstance(synced, str):
        synced = [s.strip() for s in synced.split(",") if s.strip()]

    updated = OdooAuthConfig(
        enabled=bool(body.get("enabled", curr.enabled)),
        url=str(body.get("url", curr.url)).strip().rstrip("/"),
        db_name=str(body.get("db_name", curr.db_name)).strip(),
        protocol=protocol,
        username=str(body.get("username", curr.username)).strip(),
        api_key=str(body["api_key"]).strip() if body.get("api_key") else curr.api_key,
        oauth_bearer_token=(
            str(body["oauth_bearer_token"]).strip()
            if body.get("oauth_bearer_token")
            else curr.oauth_bearer_token
        ),
        uid=curr.uid,
        webhook_secret=str(body["webhook_secret"]).strip() if body.get("webhook_secret") else curr.webhook_secret,
        require_entra_gate=bool(body.get("require_entra_gate", curr.require_entra_gate)),
        crosstalk_enabled=bool(body.get("crosstalk_enabled", curr.crosstalk_enabled)),
        standalone_passthrough=bool(body.get("standalone_passthrough", curr.standalone_passthrough)),
        bot_handle=str(body.get("bot_handle", curr.bot_handle)).strip() or "@nce",
        synced_models=list(synced),
    )
    ops.config = updated
    return JSONResponse({"status": "ok", "config": updated.to_safe_dict()})


async def api_admin_odoo_records(request: Any) -> JSONResponse:
    """GET /api/admin/odoo/records — list records for an Odoo model (`model=sale.order`)."""
    ops = get_global_odoo_ops()
    qp = request.query_params
    model = str(qp.get("model") or "sale.order").strip()
    limit = int(qp.get("limit", 50))
    try:
        items = await ops.execute_kw(model, "search_read", args=[[]], kwargs={"limit": limit})
        return JSONResponse({"model": model, "total": len(items), "items": items})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_odoo_execute(request: Any) -> JSONResponse:
    """POST /api/admin/odoo/execute — execute an ORM or workflow method on an Odoo model."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    model = str(body.get("model") or "sale.order").strip()
    method = str(body.get("method") or "search_read").strip()
    args = body.get("args") or []
    kwargs = body.get("kwargs") or {}

    ops = get_global_odoo_ops()
    try:
        res = await ops.execute_kw(model, method, args=args, kwargs=kwargs)
        return JSONResponse({"status": "ok", "model": model, "method": method, "result": res})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_odoo_intelligence(request: Any) -> JSONResponse:
    """GET /api/admin/odoo/intelligence — run 360° Super-Intelligent Odoo ERP analysis."""
    intel = OdooSuperIntelligence()
    try:
        pulse = await intel.executive_erp_pulse()
        return JSONResponse(pulse)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_odoo_crosstalk(request: Any) -> JSONResponse:
    """POST or GET /api/admin/odoo/crosstalk — run bidirectional LLM Cross-Talker or return history."""
    if getattr(request, "method", "POST").upper() == "GET":
        return await api_admin_odoo_crosstalk_history(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    action = str(body.get("action") or "prompt").strip().lower()
    ct = OdooLLMCrossTalker()
    try:
        if action == "bridge_salesforce":
            res = await ct.bridge_salesforce_to_odoo(
                sf_account_name=str(body.get("sf_account_name") or "Nordic Systems AS"),
                sf_opportunity_name=str(body.get("sf_opportunity_name") or "Enterprise Server Infrastructure"),
                expected_revenue=float(body.get("expected_revenue", 920000.0)),
            )
            return JSONResponse(res)

        res = await ct.handle_crosstalk_prompt(
            str(body.get("prompt") or "@nce Analyze sales margins, stockouts, and CRM pipeline"),
            model=str(body.get("model") or "sale.order"),
            record_id=int(body.get("record_id", 301)),
            author=str(body.get("author") or "admin_ui"),
            post_reply_to_chatter=True,
        )
        return JSONResponse(res)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_admin_odoo_crosstalk_history(request: Any) -> JSONResponse:
    """GET /api/admin/odoo/crosstalk — return recent LLM Cross-Talk & Chatter messages."""
    ops = get_global_odoo_ops()
    chatter_msgs = list(ops._store.get("mail.message", {}).values())
    return JSONResponse(
        {
            "total": len(ops._crosstalk_history),
            "items": ops._crosstalk_history[:100],
            "chatter_messages": chatter_msgs[-50:],
        }
    )


async def api_admin_odoo_sync_now(request: Any) -> JSONResponse:
    """POST /api/admin/odoo/sync — trigger immediate Odoo read-model sync."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    ops = get_global_odoo_ops()
    sync_engine = OdooSyncEngine(ops=ops)
    try:
        summary = await sync_engine.run_sync(
            models=body.get("models"),
            namespace_id=body.get("namespace_id"),
        )
        return JSONResponse({"status": "ok", "sync": summary})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_odoo_webhook_ingest(request: Any) -> JSONResponse:
    """POST /api/webhooks/odoo — receive real-time Odoo webhooks & Chatter @nce mentions."""
    ops = get_global_odoo_ops()
    receiver = OdooWebhookReceiver(ops=ops)
    raw_body = await request.body()
    sig = request.headers.get("X-Odoo-Signature") or request.headers.get("x-odoo-signature")

    if not receiver.verify_signature(raw_body, sig):
        return JSONResponse({"error": "Invalid X-Odoo-Signature"}, status_code=401)

    try:
        res = await receiver.process_webhook(raw_body)
        return JSONResponse(res)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
