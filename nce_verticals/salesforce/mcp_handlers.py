"""
nce_verticals/salesforce/mcp_handlers.py
========================================
MCP tool handlers for the Standalone Salesforce Vertical Engine.

All tools enforce the Microsoft Entra ID Identification & Allowlist Gate when
`require_entra_gate` is enabled, ensuring zero-trust security even when NCE is
only used by connecting an LLM (such as Claude Desktop) on a PC.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from nce_verticals.entra_id.auth import EntraVerificationError
from nce_verticals.entra_id.guard import get_global_entra_gate
from nce_verticals.salesforce.operations import get_global_salesforce_ops
from nce_verticals.salesforce.sync import SalesforceSyncEngine

log = logging.getLogger("nce_verticals.salesforce.mcp_handlers")


async def _enforce_entra_if_configured(
    tool_name: str,
    engine: Any,
    arguments: dict[str, Any],
) -> tuple[str | None, str | None]:
    """
    Returns `(entra_access_token, error_json)`.
    If `require_entra_gate` is True on Salesforce config, verifies the caller via
    the Entra ID gate before allowing any Salesforce read or write.
    """
    ops = get_global_salesforce_ops()
    if not ops.config.require_entra_gate:
        return arguments.get("entra_token"), None

    gate = get_global_entra_gate()
    try:
        principal = await gate.verify_request(tool_name, arguments, engine=engine)
        token = (
            principal.raw_access_token if principal else arguments.get("entra_token")
        )
        return token, None
    except EntraVerificationError as exc:
        return None, json.dumps(
            {
                "error": str(exc),
                "error_code": exc.code,
                "details": exc.details,
                "remediation": (
                    "Authenticate with Microsoft Entra ID via 'entra_login_device_code' "
                    "or ensure your account is in the authorized Entra Security Group."
                ),
            }
        )


async def handle_sf_query_soql(engine: Any, arguments: dict[str, Any]) -> str:
    """Execute a SOQL query against Salesforce (or standalone read-model)."""
    entra_token, err = await _enforce_entra_if_configured(
        "sf_query_soql", engine, arguments
    )
    if err:
        return err

    soql = str(arguments.get("soql") or "").strip()
    if not soql:
        return json.dumps({"error": "soql is required"})

    max_records = int(arguments.get("max_records", 100))
    ops = get_global_salesforce_ops()
    try:
        res = await ops.query_soql(
            soql, entra_token=entra_token, max_records=max_records
        )
        return json.dumps(res, default=str)
    except Exception as exc:
        log.exception("handle_sf_query_soql failed")
        return json.dumps({"error": str(exc)})


async def handle_sf_get_record(engine: Any, arguments: dict[str, Any]) -> str:
    """Fetch a single Salesforce SObject record by ID."""
    entra_token, err = await _enforce_entra_if_configured(
        "sf_get_record", engine, arguments
    )
    if err:
        return err

    sobject = str(arguments.get("sobject") or "").strip()
    record_id = str(arguments.get("record_id") or "").strip()
    fields = arguments.get("fields")
    if not sobject or not record_id:
        return json.dumps({"error": "sobject and record_id are required"})

    ops = get_global_salesforce_ops()
    try:
        res = await ops.get_record(
            sobject, record_id, fields=fields, entra_token=entra_token
        )
        return json.dumps(res, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_sf_create_record(engine: Any, arguments: dict[str, Any]) -> str:
    """Create a new record in Salesforce for any standard or custom SObject."""
    entra_token, err = await _enforce_entra_if_configured(
        "sf_create_record", engine, arguments
    )
    if err:
        return err

    sobject = str(arguments.get("sobject") or "").strip()
    payload = arguments.get("payload") or arguments.get("data") or {}
    if not sobject or not isinstance(payload, dict) or not payload:
        return json.dumps({"error": "sobject and non-empty payload dict are required"})

    ops = get_global_salesforce_ops()
    try:
        res = await ops.create_record(sobject, payload, entra_token=entra_token)
        return json.dumps(res, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_sf_update_record(engine: Any, arguments: dict[str, Any]) -> str:
    """Update an existing Salesforce SObject record by ID."""
    entra_token, err = await _enforce_entra_if_configured(
        "sf_update_record", engine, arguments
    )
    if err:
        return err

    sobject = str(arguments.get("sobject") or "").strip()
    record_id = str(arguments.get("record_id") or "").strip()
    payload = arguments.get("payload") or arguments.get("data") or {}
    if not sobject or not record_id or not isinstance(payload, dict) or not payload:
        return json.dumps(
            {"error": "sobject, record_id, and non-empty payload dict are required"}
        )

    ops = get_global_salesforce_ops()
    try:
        res = await ops.update_record(
            sobject, record_id, payload, entra_token=entra_token
        )
        return json.dumps(res, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_sf_delete_record(engine: Any, arguments: dict[str, Any]) -> str:
    """Delete a Salesforce SObject record by ID."""
    entra_token, err = await _enforce_entra_if_configured(
        "sf_delete_record", engine, arguments
    )
    if err:
        return err

    sobject = str(arguments.get("sobject") or "").strip()
    record_id = str(arguments.get("record_id") or "").strip()
    if not sobject or not record_id:
        return json.dumps({"error": "sobject and record_id are required"})

    ops = get_global_salesforce_ops()
    try:
        res = await ops.delete_record(sobject, record_id, entra_token=entra_token)
        return json.dumps(res, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def _handle_crm_entity_tool(
    sobject: str,
    tool_name: str,
    engine: Any,
    arguments: dict[str, Any],
) -> str:
    entra_token, err = await _enforce_entra_if_configured(tool_name, engine, arguments)
    if err:
        return err

    action = str(arguments.get("action") or "list").strip().lower()
    record_id = arguments.get("record_id") or arguments.get("id")
    payload = arguments.get("payload") or arguments.get("data")
    filters = arguments.get("filters")
    limit = int(arguments.get("limit", 50))

    ops = get_global_salesforce_ops()
    try:
        res = await ops.manage_crm_entity(
            sobject,
            action,
            record_id=record_id,
            payload=payload,
            filters=filters,
            limit=limit,
            entra_token=entra_token,
        )
        return json.dumps(res, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def handle_sf_manage_account(engine: Any, arguments: dict[str, Any]) -> str:
    """Read or write Salesforce Account records (`action`: list, get, create, update, delete)."""
    return await _handle_crm_entity_tool(
        "Account", "sf_manage_account", engine, arguments
    )


async def handle_sf_manage_contact(engine: Any, arguments: dict[str, Any]) -> str:
    """Read or write Salesforce Contact records (`action`: list, get, create, update, delete)."""
    return await _handle_crm_entity_tool(
        "Contact", "sf_manage_contact", engine, arguments
    )


async def handle_sf_manage_lead(engine: Any, arguments: dict[str, Any]) -> str:
    """Read or write Salesforce Lead records (`action`: list, get, create, update, delete)."""
    return await _handle_crm_entity_tool("Lead", "sf_manage_lead", engine, arguments)


async def handle_sf_manage_opportunity(engine: Any, arguments: dict[str, Any]) -> str:
    """Read or write Salesforce Opportunity records (`action`: list, get, create, update, delete)."""
    return await _handle_crm_entity_tool(
        "Opportunity", "sf_manage_opportunity", engine, arguments
    )


async def handle_sf_manage_case(engine: Any, arguments: dict[str, Any]) -> str:
    """Read or write Salesforce Case records (`action`: list, get, create, update, delete)."""
    return await _handle_crm_entity_tool("Case", "sf_manage_case", engine, arguments)


async def handle_sf_log_activity(engine: Any, arguments: dict[str, Any]) -> str:
    """Create or query Salesforce Task / Activity records linked to Contacts, Leads, or Accounts."""
    return await _handle_crm_entity_tool("Task", "sf_log_activity", engine, arguments)


async def handle_sf_sync_now(engine: Any, arguments: dict[str, Any]) -> str:
    """Trigger an immediate bidirectional sync between Salesforce and the local read-model."""
    entra_token, err = await _enforce_entra_if_configured(
        "sf_sync_now", engine, arguments
    )
    if err:
        return err

    ops = get_global_salesforce_ops()
    sobject_types = arguments.get("sobject_types")
    since_iso = arguments.get("since_iso")
    namespace_id = str(arguments.get("namespace_id") or "")

    try:
        conn = None
        if engine and getattr(engine, "pg_pool", None) and namespace_id:
            from nce.db_utils import scoped_pg_session

            async with scoped_pg_session(engine.pg_pool, namespace_id) as db_conn:
                sync_eng = SalesforceSyncEngine(
                    ops=ops, conn=db_conn, namespace_id=namespace_id
                )
                summary = await sync_eng.run_sync(
                    sobject_types=sobject_types,
                    since_iso=since_iso,
                    entra_token=entra_token,
                )
                return json.dumps({"status": "ok", "sync": summary}, default=str)

        sync_eng = SalesforceSyncEngine(
            ops=ops, conn=conn, namespace_id=namespace_id or None
        )
        summary = await sync_eng.run_sync(
            sobject_types=sobject_types,
            since_iso=since_iso,
            entra_token=entra_token,
        )
        return json.dumps({"status": "ok", "sync": summary}, default=str)
    except Exception as exc:
        log.exception("handle_sf_sync_now failed")
        return json.dumps({"error": str(exc)})


async def handle_sf_sync_status(engine: Any, arguments: dict[str, Any]) -> str:
    """Return current Salesforce vertical engine configuration, auth mode, and sync statistics."""
    ops = get_global_salesforce_ops()
    return json.dumps(
        {
            "config": ops.config.to_safe_dict(),
            "cached_records_count": len(ops._standalone_store),
            "recent_webhooks_count": len(ops._webhook_history),
            "last_sync": ops._last_sync_summary,
        },
        default=str,
    )
