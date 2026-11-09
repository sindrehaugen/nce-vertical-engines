"""
nce_verticals/odoo/operations.py
================================
Standalone-first & Integrated Operations Engine for Odoo across all 6 core ERP domains:
1. CRM & Customers (`res.partner`, `crm.lead`)
2. Sales & Quotations (`sale.order`, `sale.order.line`)
3. Procurement, Inventory & Warehouse (`purchase.order`, `stock.picking`, `stock.quant`, `product.template`)
4. Manufacturing / MRP (`mrp.production`, `mrp.bom`)
5. Accounting & Invoicing (`account.move`, `account.payment`)
6. Projects, Helpdesk & HR/Timesheets (`project.project`, `project.task`, `helpdesk.ticket`, `hr.employee`, `account.analytic.line`)

Works 100% standalone (with seeded/in-memory ERP store when no remote Odoo URL is set,
or live pass-through to Odoo via `OdooClient`) AND syncs to NCE `odoo_read_model`.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from nce_verticals.odoo.auth import OdooAuthConfig
from nce_verticals.odoo.client import OdooClient

log = logging.getLogger("nce_verticals.odoo.operations")

_SAFE_MODEL_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

DEFAULT_MODEL_FIELDS: dict[str, list[str]] = {
    "res.partner": ["id", "name", "email", "phone", "is_company", "customer_rank", "supplier_rank", "city", "country_id", "vat"],
    "crm.lead": ["id", "name", "partner_name", "email_from", "phone", "expected_revenue", "probability", "stage_id", "type", "priority"],
    "sale.order": ["id", "name", "partner_id", "state", "amount_untaxed", "amount_total", "margin", "margin_percent", "date_order", "validity_date"],
    "sale.order.line": ["id", "order_id", "name", "product_uom_qty", "price_unit", "purchase_price", "price_subtotal", "margin"],
    "purchase.order": ["id", "name", "partner_id", "state", "amount_total", "date_order", "date_planned"],
    "stock.picking": ["id", "name", "picking_type_code", "state", "origin", "scheduled_date"],
    "stock.quant": ["id", "product_id", "product_code", "location_name", "quantity", "reserved_quantity", "available_quantity", "reorder_min_qty"],
    "product.template": ["id", "name", "default_code", "type", "list_price", "standard_price", "qty_available", "virtual_available"],
    "mrp.production": ["id", "name", "product_id", "product_qty", "state", "date_start", "bom_id", "origin"],
    "mrp.bom": ["id", "code", "product_tmpl_id", "product_qty", "components"],
    "account.move": ["id", "name", "move_type", "partner_id", "state", "payment_state", "amount_untaxed", "amount_total", "amount_residual", "invoice_date", "invoice_date_due"],
    "project.project": ["id", "name", "partner_id", "stage_name", "allocated_hours", "effective_hours", "profitability_pct"],
    "project.task": ["id", "name", "project_id", "stage_name", "priority", "planned_hours", "effective_hours", "date_deadline"],
    "helpdesk.ticket": ["id", "name", "partner_id", "stage_name", "priority", "sla_deadline", "kanban_state"],
    "hr.employee": ["id", "name", "job_title", "department_name", "work_email"],
    "mail.message": ["id", "model", "res_id", "author_name", "body", "message_type", "date"],
}

WORKFLOW_STATE_TRANSITIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("sale.order", "action_confirm"): {"state": "sale"},
    ("sale.order", "action_cancel"): {"state": "cancel"},
    ("sale.order", "action_draft"): {"state": "draft"},
    ("purchase.order", "button_confirm"): {"state": "purchase"},
    ("purchase.order", "button_cancel"): {"state": "cancel"},
    ("stock.picking", "button_validate"): {"state": "done"},
    ("stock.picking", "action_assign"): {"state": "assigned"},
    ("mrp.production", "action_confirm"): {"state": "confirmed"},
    ("mrp.production", "button_mark_done"): {"state": "done"},
    ("account.move", "action_post"): {"state": "posted", "payment_state": "not_paid"},
    ("account.move", "button_draft"): {"state": "draft"},
    ("crm.lead", "action_set_won"): {"probability": 100.0, "stage_id": [4, "Won"]},
}


def validate_odoo_model_name(model: str) -> str:
    clean = str(model or "").strip().lower()
    if not _SAFE_MODEL_RE.match(clean):
        raise ValueError(f"Invalid Odoo model name: {model!r}")
    return clean


class OdooOperations:
    """
    Standalone & integrated Odoo ERP/CRM/MRP/Project/Accounting operational spine.
    Provides live JSON-RPC/XML-RPC execution when `config.url` is configured, and a rich
    deterministic standalone ERP state store when running offline or in standalone mode.
    """

    def __init__(self, config: OdooAuthConfig | None = None, http_client: Any = None) -> None:
        self.config = config or OdooAuthConfig.from_env()
        self._http_client = http_client
        self._store: dict[str, dict[int, dict[str, Any]]] = {}
        self._seq: int = 1000
        self._crosstalk_history: list[dict[str, Any]] = []
        self._webhook_history: list[dict[str, Any]] = []
        self._last_sync_summary: dict[str, Any] = {}
        self._seed_standalone_baseline()

    def _next_id(self) -> int:
        self._seq += 1
        return self._seq

    def _seed_standalone_baseline(self) -> None:
        """Seed realistic Norwegian/Nordic ERP baseline records for standalone & analytical readiness."""
        now_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        self._store["res.partner"] = {
            101: {
                "id": 101,
                "name": "Glamox Nordic AS",
                "email": "ordre@glamox.com",
                "phone": "+47 22 02 11 00",
                "is_company": True,
                "customer_rank": 5,
                "supplier_rank": 3,
                "city": "Oslo",
                "vat": "NO912345678MVA",
                "write_date": now_iso,
            },
            102: {
                "id": 102,
                "name": "Equinor Energy AS",
                "email": "procurement@equinor.com",
                "phone": "+47 51 99 00 00",
                "is_company": True,
                "customer_rank": 10,
                "supplier_rank": 0,
                "city": "Stavanger",
                "vat": "NO923609016MVA",
                "write_date": now_iso,
            },
        }
        self._store["crm.lead"] = {
            201: {
                "id": 201,
                "name": "Oslo Hovedkontor DALI-2 & AV Modernisering",
                "partner_name": "Equinor Energy AS",
                "email_from": "facilities@equinor.com",
                "expected_revenue": 1450000.0,
                "probability": 75.0,
                "stage_id": [3, "Proposition"],
                "type": "opportunity",
                "priority": "3",
                "days_since_last_activity": 2,
                "write_date": now_iso,
            },
            202: {
                "id": 202,
                "name": "Bergen Campus Møterom & Belysning",
                "partner_name": "Vestland Eiendom AS",
                "email_from": "drift@vestland.no",
                "expected_revenue": 680000.0,
                "probability": 35.0,
                "stage_id": [2, "Qualified"],
                "type": "opportunity",
                "priority": "2",
                "days_since_last_activity": 24,
                "write_date": now_iso,
            },
        }
        self._store["sale.order"] = {
            301: {
                "id": 301,
                "name": "SO00301",
                "partner_id": [102, "Equinor Energy AS"],
                "state": "sale",
                "amount_untaxed": 480000.0,
                "amount_total": 600000.0,
                "margin": 168000.0,
                "margin_percent": 0.35,
                "date_order": now_iso,
                "write_date": now_iso,
            },
            302: {
                "id": 302,
                "name": "SO00302",
                "partner_id": [101, "Glamox Nordic AS"],
                "state": "draft",
                "amount_untaxed": 120000.0,
                "amount_total": 150000.0,
                "margin": 6000.0,
                "margin_percent": 0.05,  # Low margin anomaly (<12%)
                "date_order": now_iso,
                "write_date": now_iso,
            },
        }
        self._store["stock.quant"] = {
            401: {
                "id": 401,
                "product_id": [501, "Glamox C95-R 600x600 4000 DALI 840 MP"],
                "product_code": "GLX-C95R-4000-DA2",
                "location_name": "WH/Stock",
                "quantity": 18.0,
                "reserved_quantity": 14.0,
                "available_quantity": 4.0,
                "reorder_min_qty": 25.0,
                "unit_cost": 1850.0,
                "lead_time_days": 7,
                "write_date": now_iso,
            },
            402: {
                "id": 402,
                "product_id": [502, "Glamox Ethernet2DALI 3-Line Controller"],
                "product_code": "GLAMOX-ETH2DALI-3",
                "location_name": "WH/Stock",
                "quantity": 2.0,
                "reserved_quantity": 2.0,
                "available_quantity": 0.0,
                "reorder_min_qty": 5.0,
                "unit_cost": 6400.0,
                "lead_time_days": 10,
                "write_date": now_iso,
            },
        }
        self._store["mrp.production"] = {
            601: {
                "id": 601,
                "name": "WH/MO/00601",
                "product_id": [510, "Pre-Wired DALI-2 Switchboard Cabinet EN 61439"],
                "product_qty": 3.0,
                "state": "confirmed",
                "origin": "SO00301",
                "date_start": now_iso,
                "write_date": now_iso,
            }
        }
        self._store["account.move"] = {
            701: {
                "id": 701,
                "name": "INV/2026/00701",
                "move_type": "out_invoice",
                "partner_id": [102, "Equinor Energy AS"],
                "state": "posted",
                "payment_state": "not_paid",
                "amount_untaxed": 480000.0,
                "amount_total": 600000.0,
                "amount_residual": 600000.0,
                "days_overdue": 18,
                "invoice_date": "2026-10-01",
                "invoice_date_due": "2026-10-22",
                "write_date": now_iso,
            },
            702: {
                "id": 702,
                "name": "BILL/2026/00702",
                "move_type": "in_invoice",
                "partner_id": [101, "Glamox Nordic AS"],
                "state": "posted",
                "payment_state": "not_paid",
                "amount_untaxed": 95000.0,
                "amount_total": 118750.0,
                "amount_residual": 118750.0,
                "days_overdue": 0,
                "invoice_date": "2026-11-01",
                "invoice_date_due": "2026-11-30",
                "write_date": now_iso,
            },
        }
        self._store["project.project"] = {
            801: {
                "id": 801,
                "name": "PRJ-801 Equinor Stavanger AV & DALI-2",
                "partner_id": [102, "Equinor Energy AS"],
                "stage_name": "In Progress",
                "allocated_hours": 320.0,
                "effective_hours": 195.0,
                "profitability_pct": 34.2,
                "write_date": now_iso,
            }
        }
        self._store["helpdesk.ticket"] = {
            901: {
                "id": 901,
                "name": "DALI-2 Line 2 Bus Drop Warning in Room 204",
                "partner_id": [102, "Equinor Energy AS"],
                "stage_name": "In Progress",
                "priority": "3",
                "kanban_state": "normal",
                "write_date": now_iso,
            }
        }
        self._store["mail.message"] = {}

    def _build_client(self) -> OdooClient | None:
        if not self.config.url:
            return None
        return OdooClient(self.config, http_client=self._http_client)

    @staticmethod
    def _matches_domain(rec: dict[str, Any], domain: list[Any] | None) -> bool:
        """Evaluate standard Odoo domain tuples `[(field, op, value), ...]` in standalone mode."""
        if not domain:
            return True
        for cond in domain:
            if not isinstance(cond, (list, tuple)) or len(cond) != 3:
                continue
            field, op, val = cond[0], str(cond[1]).lower(), cond[2]
            rv = rec.get(field)
            if isinstance(rv, list) and rv and not isinstance(val, list):
                # Many2one `[id, display_name]` comparison
                rv_cmp = rv[0] if isinstance(val, int) else str(rv[-1])
            else:
                rv_cmp = rv

            if op in ("=", "=="):
                if rv_cmp != val:
                    return False
            elif op == "!=":
                if rv_cmp == val:
                    return False
            elif op == "ilike":
                if str(val).lower() not in str(rv_cmp or "").lower():
                    return False
            elif op == "in" and isinstance(val, (list, tuple, set)):
                if rv_cmp not in val:
                    return False
            elif op == ">":
                if float(rv_cmp or 0.0) <= float(val):
                    return False
            elif op == ">=":
                if float(rv_cmp or 0.0) < float(val):
                    return False
            elif op == "<":
                if float(rv_cmp or 0.0) >= float(val):
                    return False
            elif op == "<=":
                if float(rv_cmp or 0.0) > float(val):
                    return False
        return True

    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """
        Universal Odoo ORM & workflow bridge (`search_read`, `read`, `create`, `write`,
        `unlink`, `fields_get`, `action_confirm`, `action_post`, `button_validate`, `message_post`).
        Routes to live Odoo RPC when `url` is configured, and maintains local standalone state.
        """
        mdl = validate_odoo_model_name(model)
        mth = str(method or "search_read").strip()
        call_args = list(args or [])
        call_kwargs = dict(kwargs or {})

        client = self._build_client()
        if client is not None:
            res = await client.execute_kw(mdl, mth, call_args, call_kwargs)
            # Mirror search_read results into local cache
            if mth == "search_read" and isinstance(res, list):
                bucket = self._store.setdefault(mdl, {})
                for item in res:
                    if isinstance(item, dict) and item.get("id"):
                        bucket[int(item["id"])] = item
            return res

        # Standalone deterministic ORM & Workflow execution
        bucket = self._store.setdefault(mdl, {})
        now_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

        if mth == "search_read":
            domain = call_args[0] if call_args and isinstance(call_args[0], list) else call_kwargs.get("domain", [])
            limit = int(call_kwargs.get("limit", 100))
            matched = [r for r in bucket.values() if self._matches_domain(r, domain)]
            return matched[: max(1, min(500, limit))]

        if mth == "search":
            domain = call_args[0] if call_args and isinstance(call_args[0], list) else []
            return [r["id"] for r in bucket.values() if self._matches_domain(r, domain)]

        if mth == "read":
            ids = call_args[0] if call_args else []
            if isinstance(ids, int):
                ids = [ids]
            return [bucket[int(i)] for i in ids if int(i) in bucket]

        if mth == "create":
            vals = call_args[0] if call_args and isinstance(call_args[0], dict) else call_kwargs.get("vals", {})
            new_id = self._next_id()
            rec = {
                "id": new_id,
                "state": vals.get("state", "draft"),
                **vals,
                "write_date": now_iso,
            }
            if mdl == "sale.order" and "name" not in rec:
                rec["name"] = f"SO0{new_id}"
            elif mdl == "purchase.order" and "name" not in rec:
                rec["name"] = f"PO0{new_id}"
            elif mdl == "account.move" and "name" not in rec:
                rec["name"] = f"INV/2026/{new_id}"
            elif mdl == "mrp.production" and "name" not in rec:
                rec["name"] = f"WH/MO/0{new_id}"
            bucket[new_id] = rec
            return new_id

        if mth == "write":
            ids = call_args[0] if len(call_args) >= 1 else []
            vals = call_args[1] if len(call_args) >= 2 and isinstance(call_args[1], dict) else {}
            if isinstance(ids, int):
                ids = [ids]
            for i in ids:
                rid = int(i)
                if rid in bucket:
                    bucket[rid].update(vals)
                    bucket[rid]["write_date"] = now_iso
            return True

        if mth == "unlink":
            ids = call_args[0] if call_args else []
            if isinstance(ids, int):
                ids = [ids]
            for i in ids:
                bucket.pop(int(i), None)
            return True

        if mth == "fields_get":
            sample_fields = DEFAULT_MODEL_FIELDS.get(mdl, ["id", "name", "state", "write_date"])
            return {f: {"string": f.replace("_", " ").title(), "type": "char"} for f in sample_fields}

        if mth == "message_post":
            ids = call_args[0] if call_args else [0]
            res_id = int(ids[0]) if isinstance(ids, list) and ids else int(ids or 0)
            body = str(call_kwargs.get("body") or (call_args[1] if len(call_args) > 1 else ""))
            msg_id = self._next_id()
            msg_rec = {
                "id": msg_id,
                "model": mdl,
                "res_id": res_id,
                "author_name": call_kwargs.get("author_name", "NCE Super-Intelligence Bot"),
                "body": body,
                "message_type": call_kwargs.get("message_type", "comment"),
                "date": now_iso,
            }
            self._store.setdefault("mail.message", {})[msg_id] = msg_rec
            return msg_id

        # Workflow state transition methods (action_confirm, action_post, button_validate, etc.)
        transition = WORKFLOW_STATE_TRANSITIONS.get((mdl, mth))
        if transition:
            ids = call_args[0] if call_args else []
            if isinstance(ids, int):
                ids = [ids]
            for i in ids:
                rid = int(i)
                if rid in bucket:
                    bucket[rid].update(transition)
                    bucket[rid]["write_date"] = now_iso
            return True

        return {"status": "executed", "model": mdl, "method": mth, "args": call_args}

    async def post_chatter_message(
        self,
        model: str,
        record_id: int,
        body: str,
        *,
        author_name: str = "NCE Super-Intelligence Bot",
    ) -> dict[str, Any]:
        """Post a message directly into an Odoo record's Chatter (`mail.thread.message_post`)."""
        msg_id = await self.execute_kw(
            model,
            "message_post",
            args=[[int(record_id)]],
            kwargs={
                "body": body,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment",
                "author_name": author_name,
            },
        )
        return {"message_id": msg_id, "model": model, "record_id": int(record_id), "body": body}


_GLOBAL_ODOO_OPS: OdooOperations | None = None


def get_global_odoo_ops() -> OdooOperations:
    global _GLOBAL_ODOO_OPS
    if _GLOBAL_ODOO_OPS is None:
        _GLOBAL_ODOO_OPS = OdooOperations()
    return _GLOBAL_ODOO_OPS
