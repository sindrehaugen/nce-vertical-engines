"""
nce_verticals/hr
=======================
Module 13: HR Engine -- Native master data, skills taxonomy, cert lifecycle & expiry watcher,
absences, onboarding quest, private coaching, and assignment infrastructure.

Enforces RL-1 (NEVER ranking), RL-2 (EU AI Act Art. 5 emotion inference prohibition),
and RL-3 (GDPR erasure & PII protection).
"""

from __future__ import annotations

from nce_verticals.hr._guard import (
    NCE_HR_RANKING_DISABLED,
    HrDisabledError,
    HrRankingProhibitedError,
    require_hr_enabled,
)
from nce_verticals.hr.a2a import (
    get_morning_brief_hr_slice,
    handle_field_tech_dispatch_query,
    handle_project_assignment_query,
    handle_vendor_contractor_skill_align,
)
from nce_verticals.hr.absences import (
    EVENT_TYPE_HR_ABSENCE_REGISTERED,
    do_query_absences,
    do_register_absence,
)
from nce_verticals.hr.capacity import do_capacity
from nce_verticals.hr.certs import do_cert_status, do_check_hr_cert_expiry
from nce_verticals.hr.coaching import do_coach, do_log_one_on_one
from nce_verticals.hr.compliance import (
    EVENT_TYPE_HR_COMPLIANCE_MILESTONE_RECORDED,
    do_check_compliance_deadlines,
    do_query_compliance_deadlines,
    do_update_absence_compliance,
    handle_absence_compliance_alert,
    register_hr_compliance_subscribers,
)
from nce_verticals.hr.onboarding import (
    EVENT_TYPE_HR_QUEST_PROGRESSED,
    do_build_onboarding_quest,
    do_get_onboarding_progress,
)
from nce_verticals.hr.profile import (
    EVENT_TYPE_HR_EMPLOYEE_CREATED,
    do_create_employee,
    do_get_employee,
    do_query_employees,
)
from nce_verticals.hr.skills import (
    do_match_skills,
    do_record_certification,
    do_record_skill,
)

__all__ = [
    "EVENT_TYPE_HR_ABSENCE_REGISTERED",
    "EVENT_TYPE_HR_COMPLIANCE_MILESTONE_RECORDED",
    "EVENT_TYPE_HR_EMPLOYEE_CREATED",
    "EVENT_TYPE_HR_QUEST_PROGRESSED",
    "HrDisabledError",
    "HrRankingProhibitedError",
    "NCE_HR_RANKING_DISABLED",
    "do_build_onboarding_quest",
    "do_capacity",
    "do_cert_status",
    "do_check_compliance_deadlines",
    "do_check_hr_cert_expiry",
    "do_coach",
    "do_create_employee",
    "do_get_employee",
    "do_get_onboarding_progress",
    "do_log_one_on_one",
    "do_match_skills",
    "do_query_absences",
    "do_query_compliance_deadlines",
    "do_query_employees",
    "do_record_certification",
    "do_record_skill",
    "do_register_absence",
    "do_update_absence_compliance",
    "get_morning_brief_hr_slice",
    "handle_absence_compliance_alert",
    "handle_field_tech_dispatch_query",
    "handle_project_assignment_query",
    "handle_vendor_contractor_skill_align",
    "register_hr_compliance_subscribers",
    "require_hr_enabled",
]
