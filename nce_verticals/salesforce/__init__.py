"""
nce_verticals/salesforce
========================
Standalone & Integrated Salesforce Vertical Engine.

Supports:
- 3 Authentication modes: Connected App OAuth 2.0 (Client Credentials / Refresh Token),
  OAuth 2.0 JWT Bearer Flow, and Entra ID Delegated / Pass-Through SSO.
- Standalone direct pass-through execution (zero local DB dependency) AND
  bidirectional sync into NCE `salesforce_read_model` and `kg_edges`.
- Full read & write operations for Account, Contact, Lead, Opportunity, Case,
  Task/Note, and generic SOQL / SObject CRUD.
- Real-time Webhook / Outbound Message / Platform Event receiver.
"""

from typing import Any

from nce_verticals.salesforce.auth import SalesforceAuthConfig, SalesforceTokenManager
from nce_verticals.salesforce.client import SalesforceAPIError, SalesforceClient
from nce_verticals.salesforce.operations import (
    SalesforceOperations,
    get_global_salesforce_ops,
)
from nce_verticals.salesforce.sync import SalesforceSyncEngine
from nce_verticals.salesforce.webhooks import SalesforceWebhookReceiver


def __getattr__(name: str) -> Any:
    if name == "SalesforcePlugin":
        from nce_verticals.plugin import SalesforcePlugin
        return SalesforcePlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SalesforceAPIError",
    "SalesforceAuthConfig",
    "SalesforceClient",
    "SalesforceOperations",
    "SalesforcePlugin",
    "SalesforceSyncEngine",
    "SalesforceTokenManager",
    "SalesforceWebhookReceiver",
    "get_global_salesforce_ops",
]
