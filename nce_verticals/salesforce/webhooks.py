"""
nce_verticals/salesforce/webhooks.py
====================================
Salesforce Real-Time Webhook, Outbound Message (SOAP XML), and Platform Event /
Change Data Capture (JSON) Receiver with HMAC-SHA256 signature verification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from typing import Any

from nce_verticals.salesforce.operations import SalesforceOperations, get_global_salesforce_ops

log = logging.getLogger("nce_verticals.salesforce.webhooks")


class SalesforceWebhookReceiver:
    """Validates and ingests real-time Salesforce webhook / Outbound Message events."""

    def __init__(self, ops: SalesforceOperations | None = None) -> None:
        self.ops = ops or get_global_salesforce_ops()
        self._seen_event_ids: set[str] = set()

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        """
        Verify `X-Salesforce-Signature` (base64 or hex HMAC-SHA256) against configured
        `webhook_secret`. Default-deny when a webhook secret is configured.
        """
        secret = self.ops.config.webhook_secret
        if not secret:
            return True
        if not signature_header:
            return False

        sig_clean = signature_header.strip()
        mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256)
        expected_b64 = base64.b64encode(mac.digest()).decode("ascii")
        expected_hex = mac.hexdigest()

        return hmac.compare_digest(sig_clean, expected_b64) or hmac.compare_digest(
            sig_clean.lower(), expected_hex.lower()
        )

    def parse_payload(self, raw_body: bytes, content_type: str = "application/json") -> list[dict[str, Any]]:
        """
        Normalize either JSON (Platform Event / Change Data Capture / Custom Webhook)
        or SOAP XML (Salesforce Outbound Message) into canonical event dicts.
        """
        text = raw_body.decode("utf-8", errors="replace").strip()
        if "xml" in content_type.lower() or text.startswith("<"):
            return self._parse_outbound_soap_xml(text)

        data = json.loads(text)
        items = data if isinstance(data, list) else [data]
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sobj = str(
                item.get("sobject_type")
                or item.get("entityName")
                or (item.get("ChangeEventHeader") or {}).get("entityName")
                or (item.get("attributes") or {}).get("type")
                or "Account"
            )
            sf_id = str(
                item.get("Id")
                or item.get("id")
                or item.get("sf_id")
                or ((item.get("ChangeEventHeader") or {}).get("recordIds") or [""])[0]
                or f"EVT-{uuid.uuid4().hex[:10]}"
            )
            change_type = str(
                item.get("change_type")
                or (item.get("ChangeEventHeader") or {}).get("changeType")
                or "UPSERT"
            ).upper()
            event_id = str(item.get("event_id") or item.get("replayId") or f"{sobj}:{sf_id}:{change_type}")
            record_data = item.get("record") if isinstance(item.get("record"), dict) else item
            normalized.append(
                {
                    "event_id": event_id,
                    "sobject_type": sobj,
                    "sf_id": sf_id,
                    "change_type": change_type,
                    "payload": record_data,
                }
            )
        return normalized

    @staticmethod
    def _parse_outbound_soap_xml(xml_text: str) -> list[dict[str, Any]]:
        """Extract `<sObject xsi:type="sf:Account">...</sObject>` notifications from SOAP XML."""
        events: list[dict[str, Any]] = []
        type_match = re.search(r'xsi:type="(?:sf:)?([A-Za-z0-9_]+)"', xml_text)
        sobj = type_match.group(1) if type_match else "Account"
        id_matches = re.findall(r"<(?:sf:)?Id>([^<]+)</(?:sf:)?Id>", xml_text)
        name_match = re.search(r"<(?:sf:)?Name>([^<]+)</(?:sf:)?Name>", xml_text)
        sf_id = id_matches[-1] if id_matches else f"SOAP-{uuid.uuid4().hex[:10]}"
        payload: dict[str, Any] = {"Id": sf_id}
        if name_match:
            payload["Name"] = name_match.group(1)
        events.append(
            {
                "event_id": f"soap:{sobj}:{sf_id}",
                "sobject_type": sobj,
                "sf_id": sf_id,
                "change_type": "OUTBOUND_MESSAGE",
                "payload": payload,
            }
        )
        return events

    def process_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply incoming Salesforce webhook events idempotently to the read-model."""
        processed = 0
        duplicates = 0
        for ev in events:
            eid = str(ev.get("event_id") or "")
            if eid in self._seen_event_ids:
                duplicates += 1
                continue
            self._seen_event_ids.add(eid)
            sobj = str(ev.get("sobject_type") or "Account")
            sf_id = str(ev.get("sf_id") or "")
            ctype = str(ev.get("change_type") or "UPSERT").upper()
            payload = ev.get("payload") or {}

            if ctype == "DELETE":
                self.ops._standalone_store.pop((sobj, sf_id), None)
            elif sf_id:
                self.ops._cache_record_in_memory(sobj, sf_id, payload)

            self.ops._webhook_history.insert(
                0,
                {
                    **ev,
                    "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
            del self.ops._webhook_history[200:]
            processed += 1

        return {"processed": processed, "duplicates_skipped": duplicates}
