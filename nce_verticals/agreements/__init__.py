"""Agreements Engine vertical module (Module 3).

Exports public core functions for agreement lifecycle authoring, extraction,
review, coverage/gap matrix, kickback reconciliation, compliance audit,
signing orchestration, and SLA coverage.
"""

from __future__ import annotations

from nce_verticals.agreements._guard import (
    AgreementsDisabledError,
    require_agreements_enabled,
)
from nce_verticals.agreements.authoring import (
    do_add_comment,
    do_create_agreement,
    do_suggest_revision,
)
from nce_verticals.agreements.compliance import (
    do_run_compliance_audit,
    do_suggest_terms,
)
from nce_verticals.agreements.coverage import do_coverage_matrix
from nce_verticals.agreements.extract import do_extract_agreement
from nce_verticals.agreements.graph import do_upsert_agreement
from nce_verticals.agreements.index_series import (
    do_calculate_index_adjustment,
    do_get_index_series,
)
from nce_verticals.agreements.kickback import do_reconcile_kickback
from nce_verticals.agreements.price_rules import (
    do_evaluate_price_rule,
    do_get_price_rules,
)
from nce_verticals.agreements.review import do_review_extraction
from nce_verticals.agreements.signing import (
    do_record_signature,
    do_request_signature,
)
from nce_verticals.agreements.sla import do_set_sla_coverage

__all__ = [
    "AgreementsDisabledError",
    "do_add_comment",
    "do_calculate_index_adjustment",
    "do_coverage_matrix",
    "do_create_agreement",
    "do_evaluate_price_rule",
    "do_extract_agreement",
    "do_get_index_series",
    "do_get_price_rules",
    "do_reconcile_kickback",
    "do_record_signature",
    "do_request_signature",
    "do_review_extraction",
    "do_run_compliance_audit",
    "do_set_sla_coverage",
    "do_suggest_revision",
    "do_suggest_terms",
    "do_upsert_agreement",
    "require_agreements_enabled",
]
