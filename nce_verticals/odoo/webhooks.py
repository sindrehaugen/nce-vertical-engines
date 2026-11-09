"""
nce_verticals/odoo/webhooks.py
==============================
Real-Time Odoo Webhook & Automated Server Action Receiver.
Validates `X-Odoo-Signature` (HMAC-SHA256) and routes incoming Chatter `@nce` / `@llm`
mentions directly into `OdooLLMCrossTalker`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from nce_verticals.odoo.crosstalk import OdooLLMCrossTalker
from nce_verticals.odoo.operations import OdooOperations, get_global_odoo_ops


class OdooWebhookReceiver:
    """Validates and processes incoming Odoo webhooks and Chatter @nce mentions."""

    def __init__(self, ops: OdooOperations | None = None) -> None:
        self.ops = ops or get_global_odoo_ops()
        self.crosstalk = OdooLLMCrossTalker(ops=self.ops)

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        secret = self.ops.config.webhook_secret
        if not secret:
            return True
        if not signature_header:
            return False

        sig_clean = signature_header.strip()
        mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256)
        expected_hex = mac.hexdigest()
        expected_b64 = base64.b64encode(mac.digest()).decode("ascii")
        return hmac.compare_digest(sig_clean.lower(), expected_hex.lower()) or hmac.compare_digest(
            sig_clean, expected_b64
        )

    async def process_webhook(self, raw_body: bytes) -> dict[str, Any]:
        data = json.loads(raw_body.decode("utf-8", errors="replace"))
        model = str(data.get("model") or data.get("_model") or "sale.order")
        record_id = int(data.get("id") or data.get("res_id") or 301)
        event_type = str(data.get("event") or data.get("action") or "record_updated")
        body_text = str(data.get("body") or data.get("prompt") or "")
        author = str(data.get("author") or data.get("user") or "odoo_webhook")

        event_record = {
            "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": model,
            "record_id": record_id,
            "event_type": event_type,
            "author": author,
        }
        self.ops._webhook_history.insert(0, event_record)
        del self.ops._webhook_history[200:]

        # If this webhook is a Chatter message or contains @nce / @llm, trigger LLM Cross-Talker
        bot_handle = self.ops.config.bot_handle.lower()
        if body_text and (
            bot_handle in body_text.lower()
            or "@llm" in body_text.lower()
            or event_type == "chatter_mention"
        ):
            ct_res = await self.crosstalk.handle_crosstalk_prompt(
                body_text,
                model=model,
                record_id=record_id,
                author=author,
                post_reply_to_chatter=True,
            )
            return {"status": "ok", "crosstalk_triggered": True, "crosstalk": ct_res}

        # Otherwise update the standalone mirror store
        if isinstance(data.get("values"), dict):
            await self.ops.execute_kw(model, "write", args=[[record_id], data["values"]])

        return {"status": "ok", "crosstalk_triggered": False, "event": event_record}
