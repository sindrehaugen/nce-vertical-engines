"""
nce_verticals/salesforce/operations.py
======================================
Standalone-first read & write domain operations for the Salesforce Vertical Engine.

Designed to work:
1. Completely standalone (direct pass-through to Salesforce REST API or in-memory read-model
   without requiring a local PostgreSQL database).
2. Integrated with NCE (synchronizing writes and reads with `salesforce_read_model` and `kg_edges`).

Supports:
- Generic SOQL & SObject CRUD (`query_soql`, `get_record`, `create_record`, `update_record`, `delete_record`)
- Standard CRM Objects (`Account`, `Contact`, `Lead`, `Opportunity`, `Case`, `Task` / `Note`)
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from nce_verticals.salesforce.auth import SalesforceAuthConfig, SalesforceTokenManager
from nce_verticals.salesforce.client import SalesforceClient

log = logging.getLogger("nce_verticals.salesforce.operations")

_SAFE_SOBJECT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(__c|__r)?$")

DEFAULT_SOBJECT_FIELDS: dict[str, list[str]] = {
    "Account": ["Id", "Name", "Type", "Industry", "Phone", "Website", "BillingCity", "BillingCountry", "OwnerId", "SystemModstamp"],
    "Contact": ["Id", "FirstName", "LastName", "Name", "Email", "Phone", "Title", "AccountId", "OwnerId", "SystemModstamp"],
    "Lead": ["Id", "FirstName", "LastName", "Name", "Company", "Email", "Phone", "Status", "Rating", "OwnerId", "SystemModstamp"],
    "Opportunity": ["Id", "Name", "AccountId", "StageName", "Amount", "CloseDate", "Probability", "IsClosed", "IsWon", "OwnerId", "SystemModstamp"],
    "Case": ["Id", "CaseNumber", "Subject", "Status", "Priority", "Origin", "Description", "AccountId", "ContactId", "OwnerId", "SystemModstamp"],
    "Task": ["Id", "Subject", "Status", "Priority", "Description", "WhoId", "WhatId", "ActivityDate", "OwnerId", "SystemModstamp"],
}


def validate_sobject_name(sobject: str) -> str:
    clean = str(sobject or "").strip()
    if not _SAFE_SOBJECT_RE.match(clean):
        raise ValueError(f"Invalid Salesforce SObject name: {sobject!r}")
    return clean


class SalesforceOperations:
    """
    Standalone & hybrid Salesforce operations coordinator.
    Maintains an in-memory local mirror for standalone mode and uses `SalesforceClient`
    whenever `instance_url` is configured.
    """

    def __init__(
        self,
        token_manager: SalesforceTokenManager | None = None,
        http_client: Any = None,
    ) -> None:
        self.token_manager = token_manager or SalesforceTokenManager()
        self._http_client = http_client
        self._standalone_store: dict[tuple[str, str], dict[str, Any]] = {}
        self._webhook_history: list[dict[str, Any]] = []
        self._last_sync_summary: dict[str, Any] = {}

    @property
    def config(self) -> SalesforceAuthConfig:
        return self.token_manager.config

    async def _build_client(self, entra_token: str | None = None) -> SalesforceClient | None:
        """Build a live `SalesforceClient` if `instance_url` is configured."""
        if not self.config.instance_url:
            return None
        token, inst_url = await self.token_manager.get_access_token(entra_token=entra_token)
        return SalesforceClient(
            instance_url=inst_url,
            access_token=token,
            api_version=self.config.api_version,
            http_client=self._http_client,
        )

    def _cache_record_in_memory(self, sobject: str, record_id: str, data: dict[str, Any]) -> dict[str, Any]:
        sobj = validate_sobject_name(sobject)
        existing = self._standalone_store.get((sobj, record_id), {})
        merged = {
            **existing,
            **data,
            "Id": record_id,
            "attributes": {"type": sobj},
            "SystemModstamp": data.get("SystemModstamp") or time.strftime("%Y-%m-%dT%H:%M:%S.000+0000", time.gmtime()),
        }
        self._standalone_store[(sobj, record_id)] = merged
        return merged

    async def query_soql(
        self,
        soql: str,
        *,
        entra_token: str | None = None,
        max_records: int = 200,
    ) -> dict[str, Any]:
        """Execute a SOQL query against Salesforce (or evaluate against standalone local store if offline)."""
        query_str = str(soql or "").strip()
        if not query_str.upper().startswith("SELECT "):
            raise ValueError("SOQL query must begin with SELECT")

        client = await self._build_client(entra_token=entra_token)
        if client is not None:
            records = await client.query_all_records(query_str, max_records=max_records)
            for rec in records:
                rid = rec.get("Id")
                rtype = (rec.get("attributes") or {}).get("type")
                if rid and rtype:
                    self._cache_record_in_memory(str(rtype), str(rid), rec)
            return {
                "mode": "live_salesforce",
                "totalSize": len(records),
                "done": True,
                "records": records,
            }

        # Standalone local store fallback when no remote Salesforce org URL is configured
        m = re.search(r"\bFROM\s+([A-Za-z0-9_]+)", query_str, flags=re.IGNORECASE)
        target_sobject = m.group(1) if m else ""
        matched = [
            rec
            for (sobj, _), rec in self._standalone_store.items()
            if not target_sobject or sobj.lower() == target_sobject.lower()
        ][:max_records]
        return {
            "mode": "standalone_local_store",
            "totalSize": len(matched),
            "done": True,
            "records": matched,
        }

    async def get_record(
        self,
        sobject: str,
        record_id: str,
        *,
        fields: list[str] | None = None,
        entra_token: str | None = None,
    ) -> dict[str, Any]:
        sobj = validate_sobject_name(sobject)
        client = await self._build_client(entra_token=entra_token)
        if client is not None:
            rec = await client.get_sobject(sobj, record_id, fields=fields)
            self._cache_record_in_memory(sobj, record_id, rec)
            return {"mode": "live_salesforce", "sobject": sobj, "record": rec}

        rec = self._standalone_store.get((sobj, record_id))
        if not rec:
            raise KeyError(f"{sobj} record '{record_id}' not found in standalone store")
        return {"mode": "standalone_local_store", "sobject": sobj, "record": rec}

    async def create_record(
        self,
        sobject: str,
        payload: dict[str, Any],
        *,
        entra_token: str | None = None,
    ) -> dict[str, Any]:
        sobj = validate_sobject_name(sobject)
        if not isinstance(payload, dict) or not payload:
            raise ValueError("payload must be a non-empty dictionary")

        client = await self._build_client(entra_token=entra_token)
        if client is not None:
            res = await client.create_sobject(sobj, payload)
            new_id = str(res.get("id") or res.get("Id") or "")
            if new_id:
                self._cache_record_in_memory(sobj, new_id, {**payload, "Id": new_id})
            return {"mode": "live_salesforce", "sobject": sobj, "id": new_id, "success": True, "result": res}

        # Standalone creation
        new_id = f"00{uuid.uuid4().hex[:13].upper()}"
        stored = self._cache_record_in_memory(sobj, new_id, payload)
        return {
            "mode": "standalone_local_store",
            "sobject": sobj,
            "id": new_id,
            "success": True,
            "record": stored,
        }

    async def update_record(
        self,
        sobject: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        entra_token: str | None = None,
    ) -> dict[str, Any]:
        sobj = validate_sobject_name(sobject)
        if not record_id:
            raise ValueError("record_id is required")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("payload must be a non-empty dictionary")

        client = await self._build_client(entra_token=entra_token)
        if client is not None:
            res = await client.update_sobject(sobj, record_id, payload)
            self._cache_record_in_memory(sobj, record_id, payload)
            return {"mode": "live_salesforce", "sobject": sobj, "id": record_id, "updated": True, "result": res}

        stored = self._cache_record_in_memory(sobj, record_id, payload)
        return {
            "mode": "standalone_local_store",
            "sobject": sobj,
            "id": record_id,
            "updated": True,
            "record": stored,
        }

    async def delete_record(
        self,
        sobject: str,
        record_id: str,
        *,
        entra_token: str | None = None,
    ) -> dict[str, Any]:
        sobj = validate_sobject_name(sobject)
        if not record_id:
            raise ValueError("record_id is required")

        client = await self._build_client(entra_token=entra_token)
        if client is not None:
            res = await client.delete_sobject(sobj, record_id)
            self._standalone_store.pop((sobj, record_id), None)
            return {"mode": "live_salesforce", "sobject": sobj, "id": record_id, "deleted": True, "result": res}

        existed = self._standalone_store.pop((sobj, record_id), None) is not None
        return {
            "mode": "standalone_local_store",
            "sobject": sobj,
            "id": record_id,
            "deleted": existed,
        }

    async def manage_crm_entity(
        self,
        sobject: str,
        action: str,
        *,
        record_id: str | None = None,
        payload: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        entra_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Unified high-level read/write dispatcher for standard CRM entities:
        `Account`, `Contact`, `Lead`, `Opportunity`, `Case`, `Task`.
        Actions: `get`, `list`, `create`, `update`, `delete`.
        """
        sobj = validate_sobject_name(sobject)
        act = str(action or "list").strip().lower()

        if act == "get":
            if not record_id:
                raise ValueError(f"record_id is required for {sobj}.get")
            return await self.get_record(
                sobj,
                record_id,
                fields=DEFAULT_SOBJECT_FIELDS.get(sobj),
                entra_token=entra_token,
            )

        if act == "create":
            return await self.create_record(sobj, payload or {}, entra_token=entra_token)

        if act == "update":
            if not record_id:
                raise ValueError(f"record_id is required for {sobj}.update")
            return await self.update_record(sobj, record_id, payload or {}, entra_token=entra_token)

        if act == "delete":
            if not record_id:
                raise ValueError(f"record_id is required for {sobj}.delete")
            return await self.delete_record(sobj, record_id, entra_token=entra_token)

        # Default: list / search
        fields = DEFAULT_SOBJECT_FIELDS.get(sobj, ["Id", "Name", "SystemModstamp"])
        where_clauses: list[str] = []
        for k, v in (filters or {}).items():
            if _SAFE_SOBJECT_RE.match(k) and v is not None:
                safe_v = str(v).replace("'", "\\'")
                where_clauses.append(f"{k} = '{safe_v}'")
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        soql = f"SELECT {', '.join(fields)} FROM {sobj}{where_sql} ORDER BY SystemModstamp DESC LIMIT {max(1, min(200, int(limit)))}"
        return await self.query_soql(soql, entra_token=entra_token, max_records=limit)

    def list_cached_records(self, sobject: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for (sobj, _), rec in self._standalone_store.items():
            if sobject and sobj.lower() != sobject.lower():
                continue
            out.append(rec)
        return out[: max(1, min(500, limit))]


_GLOBAL_SF_OPS: SalesforceOperations | None = None


def get_global_salesforce_ops() -> SalesforceOperations:
    global _GLOBAL_SF_OPS
    if _GLOBAL_SF_OPS is None:
        _GLOBAL_SF_OPS = SalesforceOperations()
    return _GLOBAL_SF_OPS
