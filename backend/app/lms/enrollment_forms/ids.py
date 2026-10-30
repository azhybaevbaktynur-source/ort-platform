"""Stable names of the Phase 9 enrollment forms and applications (PHASE_9_DESIGN 2.4, 2.5, 4.6-4.10, 4.12). Pure
constants: no DB, no app imports.

Purge trigger (orchestrator decision, Phase 9 S1, 2026-10-31): production has **no scheduled cron**; the attempt
sweep runs lazily during normal traffic. The D7 application purge (`purge.run_purge(limit=500)`) is therefore
triggered opportunistically and bounded, as design 4.7 describes: on the staff application list views and on submit
(at most once per process per hour, at most `PURGE_BATCH` rows per call). `POST /internal/purge-applications`
(`internal_token`) exists for a future free scheduler, but nothing schedules it. S4 implements this."""
from __future__ import annotations

# ------------------------------------------------------------------ enumerations (CHECKs in models.py / 0014)
FORM_MODES = ("form_auto", "form_review")
ENROLLMENT_MODES = ("invite_code", "closed", "open", "form_auto", "form_review")
NON_FORM_MODES = ("invite_code", "closed", "open")  # the only modes of ORT template courses (invariant 9)
FORM_STATUSES = ("draft", "active", "retired")
FIELD_TYPES = ("short_text", "long_text", "single_choice", "multi_choice", "number", "date", "email", "phone")
CHOICE_TYPES = ("single_choice", "multi_choice")
PII_CATEGORIES = ("none", "contact", "personal")
APPLICATION_STATUSES = ("pending", "approved", "rejected", "withdrawn")
OPEN_APPLICATION_STATUSES = ("pending",)

# ------------------------------------------------------------------ caps (design 2.4, 4.10)
FIELDS_PER_FORM_MAX = 25
OPTIONS_PER_FIELD_MAX = 20
FIELD_KEY_MAX = 40
FIELD_KEY_RE = r"^[a-z][a-z0-9_]{0,39}$"
INTRO_MAX = 2000                  # characters per language
SHORT_TEXT_DEFAULT_MAX, SHORT_TEXT_MAX = 200, 500
LONG_TEXT_DEFAULT_MAX, LONG_TEXT_MAX = 1000, 2000
MULTI_CHOICE_MAX = 20
PHONE_DIGITS_MIN, PHONE_DIGITS_MAX = 7, 15
DATE_YEAR_MIN = 1900
DECISION_NOTE_MAX = 500

# ------------------------------------------------------------------ retention and purge (D7, design 4.7, 6)
RETENTION_DAYS_DEFAULT = 30
RETENTION_DAYS_MIN, RETENTION_DAYS_MAX = 30, 90
PURGE_BATCH = 500
PURGE_OPPORTUNISTIC_INTERVAL_S = 3600   # once per process per hour (no cron in production)

# ------------------------------------------------------------------ rate limits (design 4.7)
APPLY_USER_24H = 10
APPLY_IP_FAIL_10M = 60

# ------------------------------------------------------------------ error codes (4xx, standard error shape)
E_FORM_REQUIRED = "form_required"            # 422: form mode without an active form
E_FORM_NEEDS_CATALOG = "form_needs_catalog"  # 422: form mode on a private course
E_FORM_ANSWERED = "form_answered"            # 409: the form has answers; create a new version
E_FORM_DRAFT_EXISTS = "form_draft_exists"    # 409: one draft per course
E_TOO_MANY_FIELDS = "too_many_fields"        # 422
E_APPLICATION_PENDING = "application_pending"  # 409
E_APPLICATION_DECIDED = "application_decided"  # 409
E_ALREADY_ENROLLED = "already_enrolled"      # 409
E_COURSE_FULL = "course_full"                # 409
E_COURSE_NOT_OPEN = "course_not_open"        # 409
E_TEMPLATE_LOCKED = "template_locked"        # reused: ORT template courses refuse form modes (422 here, design 4.6)
# answer validation codes (`details[].type`, never the submitted value; design 4.10)
A_REQUIRED, A_TOO_LONG, A_BAD_OPTION, A_BAD_FORMAT = "required", "too_long", "bad_option", "bad_format"

# ------------------------------------------------------------------ audit actions (ids and statuses only, never answers)
AUDIT_APPROVED = "course.application_approved"
AUDIT_REJECTED = "course.application_rejected"
