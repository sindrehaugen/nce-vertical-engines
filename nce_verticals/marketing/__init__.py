"""
Module 14: The Marketing Engine.
Grounded case study generation, testimonial consent management, and AEO/GEO publication.
"""

from __future__ import annotations

from nce_verticals.marketing._guard import (
    MarketingConsentMissingError,
    MarketingDisabledError,
    MarketingLowHealthTriggerError,
    MarketingSensitiveDataLeakError,
    MarketingUnapprovedPublishError,
    MarketingUngroundedClaimError,
    require_marketing_enabled,
)
from nce_verticals.marketing.advisor import (
    do_audit_seo,
    do_suggest_content,
)
from nce_verticals.marketing.approval import do_approve_content
from nce_verticals.marketing.brief import (
    do_query_marketing_a2a,
    get_marketing_morning_brief_slice,
)
from nce_verticals.marketing.candidates import do_find_case_study_candidates
from nce_verticals.marketing.drafting import (
    do_draft_case_study,
    validate_draft_grounding,
)
from nce_verticals.marketing.publish import (
    PublishTransport,
    do_publish_content,
)
from nce_verticals.marketing.redaction import redact_for_marketing_draft
from nce_verticals.marketing.taxonomy import DEFAULT_BRAND_VOICE
from nce_verticals.marketing.testimonials import (
    do_capture_testimonial,
    do_request_testimonial,
    do_retract_testimonial,
)

__all__ = [
    "DEFAULT_BRAND_VOICE",
    "MarketingConsentMissingError",
    "MarketingDisabledError",
    "MarketingLowHealthTriggerError",
    "MarketingSensitiveDataLeakError",
    "MarketingUnapprovedPublishError",
    "MarketingUngroundedClaimError",
    "PublishTransport",
    "do_approve_content",
    "do_audit_seo",
    "do_capture_testimonial",
    "do_draft_case_study",
    "do_find_case_study_candidates",
    "do_publish_content",
    "do_query_marketing_a2a",
    "do_request_testimonial",
    "do_retract_testimonial",
    "do_suggest_content",
    "get_marketing_morning_brief_slice",
    "redact_for_marketing_draft",
    "require_marketing_enabled",
    "validate_draft_grounding",
]
