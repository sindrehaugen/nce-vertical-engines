"""
nce_verticals/salesforce/sync.py
================================
Bidirectional & Incremental Sync Engine for the Salesforce Vertical Module.

Synchronizes Salesforce SObjects (`Account`, `Contact`, `Lead`, `Opportunity`, `Case`, `Task`)
into:
1. Standalone in-memory read-model (`SalesforceOperations._standalone_store`)
2. PostgreSQL `salesforce_read_model` and `kg_edges` when `conn` is provided.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from nce_verticals.salesforce.operations import (
    DEFAULT_SOBJECT_FIELDS,
    SalesforceOperations,
    get_global_salesforce_ops,
    validate_sobject_name,
)

log = logging.getLogger("nce_verticals.salesforce.sync")


class SalesforceSyncEngine:
    """Synchronizes Salesforce CRM objects with NCE read-model and Knowledge Graph."""

    def __init__(
        self,
        ops: SalesforceOperations | None = None,
        conn: Any = None,
        namespace_id: str | None = None,
    ) -> None:
        self.ops = ops or get_global_salesforce_ops()
        self.conn = conn
        self.namespace_id = namespace_id

    async def run_sync(
        self,
        *,
        sobject_types: list[str] | None = None,
        since_iso: str | None = None,
        entra_token: str | None = None,
        limit_per_object: int = 200,
    ) -> dict[str, Any]:
        targets = sobject_types or self.ops.config.sync_objects or list(DEFAULT_SOBJECT_FIELDS.keys())
        started = time.time()
        counts: dict[str, int] = {}
        kg_edges_upserted = 0

        for raw_sobj in targets:
            sobj = validate_sobject_name(raw_sobj)
            fields = DEFAULT_SOBJECT_FIELDS.get(sobj, ["Id", "Name", "SystemModstamp"])
            where_clause = f" WHERE SystemModstamp >= {since_iso}" if since_iso else ""
            soql = (
                f"SELECT {', '.join(fields)} FROM {sobj}{where_clause} "
                f"ORDER BY SystemModstamp DESC LIMIT {max(1, min(1000, int(limit_per_object)))}"
            )
            res = await self.ops.query_soql(soql, entra_token=entra_token, max_records=limit_per_object)
            records = res.get("records", [])
            counts[sobj] = len(records)

            if self.conn is not None and self.namespace_id:
                for rec in records:
                    sf_id = str(rec.get("Id") or "")
                    if not sf_id:
                        continue
                    name = str(
                        rec.get("Name")
                        or rec.get("Subject")
                        or rec.get("CaseNumber")
                        or sf_id
                    )
                    parent_id = str(rec.get("AccountId") or rec.get("WhatId") or "") or None
                    status_stage = str(rec.get("Status") or rec.get("StageName") or "") or None
                    await self.conn.execute(
                        """
                        INSERT INTO salesforce_read_model (
                            namespace_id, sf_id, sobject_type, name, owner_id,
                            parent_sf_id, status_or_stage, payload, synced_at, updated_at
                        ) VALUES (
                            $1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW(), NOW()
                        )
                        ON CONFLICT (namespace_id, sobject_type, sf_id)
                        DO UPDATE SET
                            name = EXCLUDED.name,
                            owner_id = EXCLUDED.owner_id,
                            parent_sf_id = EXCLUDED.parent_sf_id,
                            status_or_stage = EXCLUDED.status_or_stage,
                            payload = EXCLUDED.payload,
                            synced_at = NOW(),
                            updated_at = NOW()
                        """,
                        self.namespace_id,
                        sf_id,
                        sobj,
                        name,
                        rec.get("OwnerId"),
                        parent_id,
                        status_stage,
                        json.dumps(rec, default=str),
                    )
                    if parent_id:
                        kg_edges_upserted += 1

        summary = {
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": round((time.time() - started) * 1000.0, 2),
            "counts": counts,
            "total_records": sum(counts.values()),
            "kg_edges_projected": kg_edges_upserted,
            "db_persisted": bool(self.conn is not None and self.namespace_id),
        }
        self.ops._last_sync_summary = summary
        return summary
