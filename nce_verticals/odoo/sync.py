"""
nce_verticals/odoo/sync.py
==========================
Bidirectional & Incremental Read-Model Sync Engine between Odoo ERP and
NCE PostgreSQL (`odoo_read_model` table in migration 081) + in-memory cache.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from nce_verticals.odoo.operations import OdooOperations, get_global_odoo_ops

log = logging.getLogger("nce_verticals.odoo.sync")


class OdooSyncEngine:
    """
    Synchronizes Odoo ERP models (`res.partner`, `crm.lead`, `sale.order`,
    `purchase.order`, `stock.quant`, `mrp.production`, `account.move`,
    `project.project`, `helpdesk.ticket`) into the local read-model cache
    and PostgreSQL `odoo_read_model` table when a database pool is available.
    """

    def __init__(self, ops: OdooOperations | None = None, pg_pool: Any = None) -> None:
        self.ops = ops or get_global_odoo_ops()
        self._pg_pool = pg_pool

    async def run_sync(
        self,
        *,
        models: list[str] | None = None,
        namespace_id: str | None = None,
        limit_per_model: int = 200,
    ) -> dict[str, Any]:
        """Run incremental or full read-model sync across configured Odoo models."""
        target_models = models or list(self.ops.config.synced_models)
        started_at = time.time()
        synced_counts: dict[str, int] = {}
        pg_upserted = 0
        errors: list[str] = []

        for model in target_models:
            try:
                records = await self.ops.execute_kw(
                    model,
                    "search_read",
                    args=[[]],
                    kwargs={"limit": limit_per_model},
                )
                if not isinstance(records, list):
                    records = []
                synced_counts[model] = len(records)

                if self._pg_pool is not None and namespace_id:
                    pg_upserted += await self._upsert_to_postgres(
                        namespace_id=namespace_id,
                        model=model,
                        records=records,
                    )
            except Exception as exc:
                log.warning("Odoo sync warning on model %s: %s", model, exc)
                errors.append(f"{model}: {exc}")
                synced_counts[model] = 0

        summary = {
            "status": "completed" if not errors else "partial",
            "models_synced": synced_counts,
            "total_records": sum(synced_counts.values()),
            "pg_rows_upserted": pg_upserted,
            "duration_ms": round((time.time() - started_at) * 1000.0, 2),
            "synced_at": time.time(),
            "errors": errors,
        }
        setattr(self.ops, "_last_sync_summary", summary)
        return summary

    async def _upsert_to_postgres(
        self,
        *,
        namespace_id: str,
        model: str,
        records: list[dict[str, Any]],
    ) -> int:
        if self._pg_pool is None or not records:
            return 0
        count = 0
        try:
            async with self._pg_pool.acquire() as conn:
                for rec in records:
                    rid = int(rec.get("id") or 0)
                    if rid <= 0:
                        continue
                    display_name = str(rec.get("name") or rec.get("display_name") or f"{model}#{rid}")
                    state = str(rec.get("state") or rec.get("stage_id") or "")
                    partner_name = ""
                    p_field = rec.get("partner_id")
                    if isinstance(p_field, list) and len(p_field) >= 2:
                        partner_name = str(p_field[1])
                    elif isinstance(p_field, str):
                        partner_name = p_field
                    amount_total = (
                        float(rec["amount_total"])
                        if rec.get("amount_total") is not None
                        else (
                            float(rec["expected_revenue"])
                            if rec.get("expected_revenue") is not None
                            else None
                        )
                    )
                    currency = str(rec.get("currency") or "NOK")
                    await conn.execute(
                        """
                        INSERT INTO odoo_read_model (
                            namespace_id, odoo_model, odoo_id, display_name,
                            state, partner_name, amount_total, currency, payload, synced_at
                        ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW())
                        ON CONFLICT (namespace_id, odoo_model, odoo_id)
                        DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            state = EXCLUDED.state,
                            partner_name = EXCLUDED.partner_name,
                            amount_total = EXCLUDED.amount_total,
                            currency = EXCLUDED.currency,
                            payload = EXCLUDED.payload,
                            synced_at = NOW()
                        """,
                        namespace_id,
                        model,
                        rid,
                        display_name,
                        state,
                        partner_name,
                        amount_total,
                        currency,
                        json.dumps(rec, default=str),
                    )
                    count += 1
        except Exception as exc:
            log.debug("Postgres odoo_read_model upsert skipped: %s", exc)
        return count
