"""
nce_verticals/salesforce/client.py
==================================
Async Salesforce REST API Client (v60.0).

Supports:
- SOQL queries (`query`, `query_all` with automatic `nextRecordsUrl` pagination)
- SObject CRUD (`get_sobject`, `create_sobject`, `update_sobject`, `upsert_sobject`, `delete_sobject`)
- SObject metadata inspection (`describe_sobject`, `list_sobjects`)
- Explicit timeouts (<5s connect, <10s read) per Senior Architect AV/HTTP rules.
"""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import AsyncIterator
from typing import Any

from nce_verticals.entra_id._http_compat import httpx

log = logging.getLogger("nce_verticals.salesforce.client")

SF_TIMEOUT = httpx.Timeout(connect=4.5, read=9.5, write=4.5, pool=4.5)


class SalesforceAPIError(RuntimeError):
    """Raised when Salesforce REST API returns an error status."""

    def __init__(self, status_code: int, message: str, error_code: str = "SF_API_ERROR") -> None:
        super().__init__(f"Salesforce API Error ({status_code} {error_code}): {message}")
        self.status_code = status_code
        self.error_code = error_code


class SalesforceClient:
    """Async Salesforce REST API client with automatic pagination and strict timeouts."""

    def __init__(
        self,
        instance_url: str,
        access_token: str,
        *,
        api_version: str = "v60.0",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.api_version = api_version if api_version.startswith("v") else f"v{api_version}"
        self._external_client = http_client

    @property
    def base_data_path(self) -> str:
        return f"/services/data/{self.api_version}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = (
            path_or_url
            if path_or_url.startswith("http://") or path_or_url.startswith("https://")
            else f"{self.instance_url}{path_or_url}"
        )

        if self._external_client is not None:
            resp = await self._external_client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=self._headers(),
            )
        else:
            async with httpx.AsyncClient(timeout=SF_TIMEOUT) as client:
                resp = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=self._headers(),
                )

        if resp.status_code in (200, 201):
            if not resp.content:
                return {"success": True}
            return resp.json()
        if resp.status_code == 204:
            return {"success": True, "status_code": 204}

        err_msg = resp.text[:300]
        err_code = "SF_API_ERROR"
        try:
            err_json = resp.json()
            if isinstance(err_json, list) and err_json:
                err_msg = str(err_json[0].get("message") or err_msg)
                err_code = str(err_json[0].get("errorCode") or err_code)
            elif isinstance(err_json, dict):
                err_msg = str(
                    err_json.get("message") or err_json.get("error_description") or err_msg
                )
                err_code = str(err_json.get("errorCode") or err_json.get("error") or err_code)
        except Exception:
            pass
        raise SalesforceAPIError(resp.status_code, err_msg, error_code=err_code)

    async def query(self, soql: str, *, include_deleted: bool = False) -> dict[str, Any]:
        """Execute a single SOQL query page (`/query` or `/queryAll`)."""
        endpoint = "queryAll" if include_deleted else "query"
        return await self._request(
            "GET",
            f"{self.base_data_path}/{endpoint}",
            params={"q": soql},
        )

    async def query_all_records(
        self,
        soql: str,
        *,
        include_deleted: bool = False,
        max_records: int = 2000,
    ) -> list[dict[str, Any]]:
        """Execute a SOQL query and follow `nextRecordsUrl` up to `max_records`."""
        records: list[dict[str, Any]] = []
        page = await self.query(soql, include_deleted=include_deleted)
        batch = page.get("records", [])
        if isinstance(batch, list):
            records.extend(batch)

        next_url = page.get("nextRecordsUrl")
        while next_url and len(records) < max_records:
            page = await self._request("GET", str(next_url))
            batch = page.get("records", [])
            if isinstance(batch, list):
                records.extend(batch)
            next_url = page.get("nextRecordsUrl")

        return records[:max_records]

    async def paginate_soql(
        self,
        soql: str,
        *,
        include_deleted: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding records across all Salesforce query locator pages."""
        page = await self.query(soql, include_deleted=include_deleted)
        for rec in page.get("records", []):
            yield rec
        next_url = page.get("nextRecordsUrl")
        while next_url:
            page = await self._request("GET", str(next_url))
            for rec in page.get("records", []):
                yield rec
            next_url = page.get("nextRecordsUrl")

    async def get_sobject(
        self,
        sobject: str,
        record_id: str,
        *,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch a single SObject record by ID."""
        safe_obj = urllib.parse.quote(sobject, safe="")
        safe_id = urllib.parse.quote(record_id, safe="")
        params = {"fields": ",".join(fields)} if fields else None
        return await self._request(
            "GET",
            f"{self.base_data_path}/sobjects/{safe_obj}/{safe_id}",
            params=params,
        )

    async def create_sobject(self, sobject: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new SObject record (`POST /sobjects/{SObject}`)."""
        from nce_verticals.replay_fence import ReplaySandboxFenceError, check_replay_sandbox_env

        if check_replay_sandbox_env(payload) or check_replay_sandbox_env():
            raise ReplaySandboxFenceError(
                f"Salesforce create {sobject} blocked: replay sandbox mode active"
            )
        safe_obj = urllib.parse.quote(sobject, safe="")
        return await self._request(
            "POST",
            f"{self.base_data_path}/sobjects/{safe_obj}",
            json_body=payload,
        )

    async def update_sobject(
        self,
        sobject: str,
        record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing SObject record (`PATCH /sobjects/{SObject}/{id}`)."""
        from nce_verticals.replay_fence import ReplaySandboxFenceError, check_replay_sandbox_env

        if check_replay_sandbox_env(payload) or check_replay_sandbox_env():
            raise ReplaySandboxFenceError(
                f"Salesforce update {sobject}/{record_id} blocked: replay sandbox mode active"
            )
        safe_obj = urllib.parse.quote(sobject, safe="")
        safe_id = urllib.parse.quote(record_id, safe="")
        res = await self._request(
            "PATCH",
            f"{self.base_data_path}/sobjects/{safe_obj}/{safe_id}",
            json_body=payload,
        )
        return {"id": record_id, "sobject": sobject, "updated": True, **res}

    async def upsert_sobject(
        self,
        sobject: str,
        external_id_field: str,
        external_id_value: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Idempotent upsert by External ID (`PATCH /sobjects/{SObject}/{field}/{value}`)."""
        from nce_verticals.replay_fence import ReplaySandboxFenceError, check_replay_sandbox_env

        if check_replay_sandbox_env(payload) or check_replay_sandbox_env():
            raise ReplaySandboxFenceError(
                f"Salesforce upsert {sobject} blocked: replay sandbox mode active"
            )
        safe_obj = urllib.parse.quote(sobject, safe="")
        safe_field = urllib.parse.quote(external_id_field, safe="")
        safe_val = urllib.parse.quote(external_id_value, safe="")
        return await self._request(
            "PATCH",
            f"{self.base_data_path}/sobjects/{safe_obj}/{safe_field}/{safe_val}",
            json_body=payload,
        )

    async def delete_sobject(self, sobject: str, record_id: str) -> dict[str, Any]:
        """Delete an SObject record (`DELETE /sobjects/{SObject}/{id}`)."""
        from nce_verticals.replay_fence import ReplaySandboxFenceError, check_replay_sandbox_env

        if check_replay_sandbox_env():
            raise ReplaySandboxFenceError(
                f"Salesforce delete {sobject}/{record_id} blocked: replay sandbox mode active"
            )
        safe_obj = urllib.parse.quote(sobject, safe="")
        safe_id = urllib.parse.quote(record_id, safe="")
        res = await self._request(
            "DELETE",
            f"{self.base_data_path}/sobjects/{safe_obj}/{safe_id}",
        )
        return {"id": record_id, "sobject": sobject, "deleted": True, **res}

    async def describe_sobject(self, sobject: str) -> dict[str, Any]:
        """Retrieve SObject schema metadata (`/sobjects/{SObject}/describe`)."""
        safe_obj = urllib.parse.quote(sobject, safe="")
        return await self._request("GET", f"{self.base_data_path}/sobjects/{safe_obj}/describe")
