"""
nce_verticals/procurement/__init__.py
============================================
Procurement Engine vertical module (Module 1).

Exports public core functions for purchase orders, supplier ranking,
bids, rebate frontiers, TCO calculation, and 3-way matching.
"""

from __future__ import annotations

from nce_verticals.procurement.bids import do_resolve_bids
from nce_verticals.procurement.frontier import (
    do_forecast_rebate,
    do_recommend_move_spend,
    do_whatif_spend,
)
from nce_verticals.procurement.po import do_generate_po, do_submit_po
from nce_verticals.procurement.po_line import (
    ALLOWED_TRANSITIONS,
    NODE_TYPE_PO_LINE,
    POLineStatus,
    po_line_label,
    update_po_line_status,
    upsert_po_line_node,
    validate_status_transition,
)
from nce_verticals.procurement.ranking import do_rank_suppliers
from nce_verticals.procurement.recalibration import (
    do_recalibrate_supplier,
    do_record_match_decision,
)
from nce_verticals.procurement.savings import do_aggregate_savings
from nce_verticals.procurement.tco import do_calculate_tco
from nce_verticals.procurement.three_way_match import (
    do_evaluate_three_way_match,
)
from nce_verticals.procurement.transports import (
    ManualPoTransport,
    NetsetPoTransport,
    PoTransport,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ManualPoTransport",
    "NODE_TYPE_PO_LINE",
    "NetsetPoTransport",
    "POLineStatus",
    "PoTransport",
    "do_aggregate_savings",
    "do_calculate_tco",
    "do_evaluate_three_way_match",
    "do_forecast_rebate",
    "do_generate_po",
    "do_rank_suppliers",
    "do_recalibrate_supplier",
    "do_recommend_move_spend",
    "do_record_match_decision",
    "do_resolve_bids",
    "do_submit_po",
    "do_whatif_spend",
    "po_line_label",
    "update_po_line_status",
    "upsert_po_line_node",
    "validate_status_transition",
]
