"""
nce_verticals/odoo
==================
Standalone & Integrated Super-Intelligent Odoo Vertical Engine + Full LLM Cross-Talker.

Capabilities:
1. Multi-Protocol Client (`jsonrpc`, `xmlrpc`, `rest_oauth2`) with Microsoft Entra ID Security Gate.
2. Full 6-Domain ERP/CRM/MRP/Project/Inventory/Accounting Read, Write & Workflow Execution (`execute_kw`).
3. Super-Intelligent Cognitive Analyser:
   - Margin & Invoice Anomaly Detection (`analyze_margins_and_invoices`)
   - Smart Inventory & MRP Replenishment Forecaster (`forecast_inventory_and_mrp`)
   - AI Lead/Opportunity Scorer & Next-Best-Action (`score_leads_and_pipeline`)
   - 360° Executive ERP Pulse (`executive_erp_pulse`)
4. Full Bidirectional LLM Cross-Talker (`OdooLLMCrossTalker`):
   - Odoo Chatter (`mail.message`) & Discuss (`discuss.channel`) `@nce` / `@llm` conversational agent.
   - Cross-Engine orchestration bridging Odoo <-> Salesforce <-> Relux/Glamox DALI-2 <-> NCE Graph.
"""

from typing import Any

from nce_verticals.odoo.auth import OdooAuthConfig
from nce_verticals.odoo.client import OdooAPIError, OdooClient
from nce_verticals.odoo.crosstalk import OdooLLMCrossTalker
from nce_verticals.odoo.intelligence import OdooSuperIntelligence
from nce_verticals.odoo.operations import OdooOperations, get_global_odoo_ops


def __getattr__(name: str) -> Any:
    if name == "OdooPlugin":
        from nce_verticals.plugin import OdooPlugin
        return OdooPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "OdooAPIError",
    "OdooAuthConfig",
    "OdooClient",
    "OdooLLMCrossTalker",
    "OdooOperations",
    "OdooPlugin",
    "OdooSuperIntelligence",
    "get_global_odoo_ops",
]
