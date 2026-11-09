"""
nce_verticals/odoo/auth.py
==========================
Configuration & Authentication Manager for the Standalone Odoo Vertical Engine.

Supports all 3 connection & authentication protocols:
1. `jsonrpc`: Odoo JSON-RPC 2.0 (`/jsonrpc` service=`common`/`object`) with API Key or password.
2. `xmlrpc`: Odoo External API XML-RPC (`/xmlrpc/2/common` & `/xmlrpc/2/object`).
3. `rest_oauth2`: Odoo REST API / OAuth 2.0 Bearer + Microsoft Entra ID SSO delegation.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any


@dataclasses.dataclass(slots=True)
class OdooAuthConfig:
    """Configuration for the Standalone Super-Intelligent Odoo Vertical Engine."""

    enabled: bool = True
    url: str = ""
    db_name: str = "odoo"
    protocol: str = "jsonrpc"  # 'jsonrpc' | 'xmlrpc' | 'rest_oauth2'
    username: str = "admin"
    api_key: str = ""
    oauth_bearer_token: str = ""
    uid: int | None = None
    webhook_secret: str = ""
    require_entra_gate: bool = True
    crosstalk_enabled: bool = True
    standalone_passthrough: bool = True
    bot_handle: str = "@nce"
    synced_models: list[str] = dataclasses.field(
        default_factory=lambda: [
            "res.partner",
            "crm.lead",
            "sale.order",
            "sale.order.line",
            "purchase.order",
            "stock.picking",
            "stock.quant",
            "product.template",
            "mrp.production",
            "mrp.bom",
            "account.move",
            "project.project",
            "project.task",
            "helpdesk.ticket",
            "hr.employee",
        ]
    )

    @classmethod
    def from_env(cls) -> OdooAuthConfig:
        models_raw = os.environ.get(
            "NCE_ODOO_SYNCED_MODELS",
            "res.partner,crm.lead,sale.order,purchase.order,stock.picking,mrp.production,account.move,project.project,helpdesk.ticket",
        )
        uid_env = os.environ.get("NCE_ODOO_UID", "").strip()
        protocol = os.environ.get("NCE_ODOO_PROTOCOL", "jsonrpc").strip().lower()
        if protocol not in ("jsonrpc", "xmlrpc", "rest_oauth2"):
            protocol = "jsonrpc"

        return cls(
            enabled=os.environ.get("NCE_ODOO_ENABLED", "true").lower() in ("1", "true", "yes"),
            url=os.environ.get("NCE_ODOO_URL", "").strip().rstrip("/"),
            db_name=os.environ.get("NCE_ODOO_DB", "odoo").strip(),
            protocol=protocol,
            username=os.environ.get("NCE_ODOO_USERNAME", "admin").strip(),
            api_key=os.environ.get("NCE_ODOO_API_KEY", "").strip(),
            oauth_bearer_token=os.environ.get("NCE_ODOO_BEARER_TOKEN", "").strip(),
            uid=int(uid_env) if uid_env.isdigit() else None,
            webhook_secret=os.environ.get("NCE_ODOO_WEBHOOK_SECRET", "").strip(),
            require_entra_gate=os.environ.get("NCE_ODOO_REQUIRE_ENTRA_GATE", "true").lower() in ("1", "true", "yes"),
            crosstalk_enabled=os.environ.get("NCE_ODOO_CROSSTALK_ENABLED", "true").lower() in ("1", "true", "yes"),
            standalone_passthrough=os.environ.get("NCE_ODOO_STANDALONE", "true").lower() in ("1", "true", "yes"),
            bot_handle=os.environ.get("NCE_ODOO_BOT_HANDLE", "@nce").strip() or "@nce",
            synced_models=[m.strip() for m in models_raw.split(",") if m.strip()],
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Return safe dictionary representation with secrets masked."""
        return {
            "enabled": self.enabled,
            "url": self.url,
            "db_name": self.db_name,
            "protocol": self.protocol,
            "username": self.username,
            "api_key_set": bool(self.api_key),
            "oauth_bearer_token_set": bool(self.oauth_bearer_token),
            "uid": self.uid,
            "webhook_secret_set": bool(self.webhook_secret),
            "require_entra_gate": self.require_entra_gate,
            "crosstalk_enabled": self.crosstalk_enabled,
            "standalone_passthrough": self.standalone_passthrough,
            "bot_handle": self.bot_handle,
            "synced_models": list(self.synced_models),
        }
