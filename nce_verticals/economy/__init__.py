"""
nce_verticals/economy/__init__.py
========================================
Economy Engine vertical module (Module 6).

Exports public core functions for invoices, Peppol/EHF, GL reconciliation,
matching, revenue recognition, dunning, and margin cascades.
"""

from __future__ import annotations

from nce_verticals.economy._guard import (
    EconomyDisabledError,
    require_economy_enabled,
)
from nce_verticals.economy.cascade import do_cascade_on_approval
from nce_verticals.economy.close_narrative import do_generate_close_narrative
from nce_verticals.economy.contracts import (
    do_scan_renewals,
    do_upsert_contract,
    do_validate_contract,
)
from nce_verticals.economy.dunning import do_compute_dunning
from nce_verticals.economy.events import do_emit_financial_event
from nce_verticals.economy.finago import do_gl_sync_status, do_reconcile_gl
from nce_verticals.economy.forecast import do_forecast_cashflow
from nce_verticals.economy.gl import do_get_gl_records
from nce_verticals.economy.ingestion import (
    do_get_invoice_watermark,
    do_ingest_invoice,
)
from nce_verticals.economy.matching import do_match_invoice
from nce_verticals.economy.ngaap import do_compute_bucket_targets
from nce_verticals.economy.peppol import (
    do_generate_ehf,
    do_generate_kid,
    do_validate_kid,
)
from nce_verticals.economy.recalibration import (
    do_recalibrate_supplier,
    do_record_match_decision,
)
from nce_verticals.economy.recurring import (
    do_compute_recognition_schedule,
    do_recognize_recurring,
    do_snapshot_mrr_arr_churn,
)

__all__ = [
    "EconomyDisabledError",
    "do_cascade_on_approval",
    "do_compute_bucket_targets",
    "do_compute_dunning",
    "do_compute_recognition_schedule",
    "do_emit_financial_event",
    "do_forecast_cashflow",
    "do_generate_close_narrative",
    "do_generate_ehf",
    "do_generate_kid",
    "do_get_gl_records",
    "do_get_invoice_watermark",
    "do_gl_sync_status",
    "do_ingest_invoice",
    "do_match_invoice",
    "do_recalibrate_supplier",
    "do_recognize_recurring",
    "do_reconcile_gl",
    "do_record_match_decision",
    "do_scan_renewals",
    "do_snapshot_mrr_arr_churn",
    "do_upsert_contract",
    "do_validate_contract",
    "do_validate_kid",
    "require_economy_enabled",
]
