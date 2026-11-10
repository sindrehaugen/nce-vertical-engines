"""
nce_verticals/odoo/mcp_handlers.py
==================================
MCP tool handlers for the Standalone Super-Intelligent Odoo Vertical Engine & LLM Cross-Talker.

All tools enforce the Microsoft Entra ID Identification & Allowlist Gate when
`require_entra_gate` is enabled.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from nce_verticals.entra_id.auth import EntraVerificationError
from nce_verticals.entra_id.guard import get_global_entra_gate
from nce_verticals.odoo.crosstalk import OdooLLMCrossTalker
from nce_verticals.odoo.intelligence import OdooSuperIntelligence
from nce_verticals.odoo.operations import get_global_odoo_ops
from nce_verticals.odoo.sync import OdooSyncEngine

log = logging.getLogger("nce_verticals.odoo.mcp_handlers")


async def _enforce_entra_if_configured(
    tool_name: str,
    engine: Any,
    arguments: dict[str, Any],
) -> str | None:
    ops = get_global_odoo_ops()
    if not ops.config.require_entra_gate:
        return None
    gate = get_global_entra_gate()
    try:
        await gate.verify_request(tool_name, arguments, engine=engine)
        return None
    except EntraVerificationError as exc:
        return json.dumps(
            {
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
                "remediation": (
                    "Authenticate with Microsoft Entra ID via 'entra_login_device_code' "
                    "or verify membership in the authorized company Entra Security Group."
                ),
            }
        )


async def handle_odoo_execute_kw(engine: Any, arguments: dict[str, Any]) -> str:
    """
    Execute any Odoo ORM method (`search_read`, `read`, `create`, `write`, `unlink`, `fields_get`)
    across any Odoo model (`res.partner`, `crm.lead`, `sale.order`, `purchase.order`,
    `stock.quant`, `mrp.production`, `account.move`, `project.project`, `helpdesk.ticket`).
    """
    err = await _enforce_entra_if_configured("odoo_execute_kw", engine, arguments)
    if err:
        return err

    model = str(arguments.get("model") or "res.partner").strip()
    method = str(arguments.get("method") or "search_read").strip()
    args = arguments.get("args") or []
    kwargs = arguments.get("kwargs") or {}

    ops = get_global_odoo_ops()
    try:
        res = await ops.execute_kw(model, method, args=args, kwargs=kwargs)
        return json.dumps({"status": "ok", "model": model, "method": method, "result": res}, default=str)
    except Exception as exc:
        log.exception("handle_odoo_execute_kw failed")
        return json.dumps({"error": str(exc)})


async def handle_odoo_workflow_action(engine: Any, arguments: dict[str, Any]) -> str:
    """
    Trigger an Odoo workflow method (`action_confirm`, `action_post`, `button_validate`,
    `button_confirm`, `action_set_won`, `message_post`) on one or more record IDs.
    """
    err = await _enforce_entra_if_configured("odoo_workflow_action", engine, arguments)
    if err:
        return err

    model = str(arguments.get("model") or "sale.order").strip()
    action = str(arguments.get("action") or "action_confirm").strip()
    record_ids = arguments.get("record_ids") or arguments.get("record_id") or []
    if isinstance(record_ids, int):
        record_ids = [record_ids]

    ops = get_global_odoo_ops()
    try:
        res = await ops.execute_kw(model, action, args=[record_ids], kwargs=arguments.get("kwargs") or {})
        return json.dumps(
            {"status": "ok", "model": model, "action": action, "record_ids": record_ids, "result": res},
            default=str,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_odoo_super_intelligence(engine: Any, arguments: dict[str, Any]) -> str:
    """
    Run the Super-Intelligent Odoo Cognitive Analyser:
    - `mode="pulse"`: Full 360° Executive ERP Pulse
    - `mode="margins_invoices"`: Sales margin anomalies + overdue AR/AP cashflow analysis
    - `mode="inventory_mrp"`: Stockout & MRP replenishment forecaster
    - `mode="crm_pipeline"`: AI lead scoring & Next-Best-Action generator
    """
    err = await _enforce_entra_if_configured("odoo_super_intelligence", engine, arguments)
    if err:
        return err

    mode = str(arguments.get("mode") or "pulse").strip().lower()
    intel = OdooSuperIntelligence()
    try:
        if mode in ("margins", "margins_invoices", "finance"):
            res = await intel.analyze_margins_and_invoices(
                min_acceptable_margin_pct=float(arguments.get("min_acceptable_margin_pct", 0.15))
            )
        elif mode in ("inventory", "inventory_mrp", "mrp"):
            res = await intel.forecast_inventory_and_mrp()
        elif mode in ("crm", "crm_pipeline", "leads"):
            res = await intel.score_leads_and_pipeline()
        else:
            res = await intel.executive_erp_pulse()
        return json.dumps(res, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_odoo_llm_crosstalk(engine: Any, arguments: dict[str, Any]) -> str:
    """
    Full Bidirectional LLM Cross-Talker for Odoo:
    - `action="prompt"`: Send a natural-language `@nce` prompt for an Odoo record/channel,
      cross-analyzing Odoo and Salesforce, and post the response to Odoo Chatter.
    - `action="bridge_salesforce"`: Synchronize a Salesforce Account & Opportunity into Odoo
      `res.partner` and `crm.lead`.
    """
    err = await _enforce_entra_if_configured("odoo_llm_crosstalk", engine, arguments)
    if err:
        return err

    action = str(arguments.get("action") or "prompt").strip().lower()
    ct = OdooLLMCrossTalker()
    try:
        if action == "bridge_salesforce":
            res = await ct.bridge_salesforce_to_odoo(
                sf_account_name=str(arguments.get("sf_account_name") or "Nordic Systems AS"),
                sf_opportunity_name=str(arguments.get("sf_opportunity_name") or "Enterprise Server Infrastructure"),
                expected_revenue=float(arguments.get("expected_revenue", 850000.0)),
            )
            return json.dumps(res, default=str)

        prompt = str(arguments.get("prompt") or "@nce Run full ERP margin, stock and CRM intelligence check")
        model = str(arguments.get("model") or "sale.order")
        record_id = int(arguments.get("record_id", 301))
        res = await ct.handle_crosstalk_prompt(
            prompt,
            model=model,
            record_id=record_id,
            author=str(arguments.get("author") or "claude_mcp"),
            post_reply_to_chatter=bool(arguments.get("post_reply_to_chatter", True)),
        )
        return json.dumps(res, default=str)
    except Exception as exc:
        log.exception("handle_odoo_llm_crosstalk failed")
        return json.dumps({"error": str(exc)})


async def handle_odoo_sync_now(engine: Any, arguments: dict[str, Any]) -> str:
    """Synchronize Odoo ERP models into the local read-model cache and PostgreSQL `odoo_read_model`."""
    err = await _enforce_entra_if_configured("odoo_sync_now", engine, arguments)
    if err:
        return err

    ops = get_global_odoo_ops()
    pg_pool = getattr(engine, "_pg_pool", None) if engine is not None else None
    sync_engine = OdooSyncEngine(ops=ops, pg_pool=pg_pool)
    models = arguments.get("models")
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",") if m.strip()]
    summary = await sync_engine.run_sync(
        models=models,
        namespace_id=arguments.get("namespace_id"),
        limit_per_model=int(arguments.get("limit_per_model", 200)),
    )
    return json.dumps(summary, default=str)


async def handle_odoo_status(engine: Any, arguments: dict[str, Any]) -> str:
    """Return current Odoo Vertical Engine configuration, model counts, and Cross-Talk history."""
    ops = get_global_odoo_ops()
    model_counts = {m: len(recs) for m, recs in ops._store.items()}
    return json.dumps(
        {
            "config": ops.config.to_safe_dict(),
            "model_record_counts": model_counts,
            "crosstalk_messages_count": len(ops._crosstalk_history),
            "last_sync": getattr(ops, "_last_sync_summary", None),
            "recent_crosstalk": ops._crosstalk_history[:10],
        },
        default=str,
    )
