"""Stable names shared by every Phase 8a slice (PHASE_8A_DESIGN 2.3-2.9, 5.2, 5.6, 6). Pure constants: no DB, no app
imports. The pages, course files and announcements packages keep their own `ids.py`; the error codes every 8a package
shares are defined here once and re-exported there."""
from __future__ import annotations

# ------------------------------------------------------------------ caps (5.2, 2.3; service, 422 `limit_reached`)
MODULES_PER_COURSE_MAX = 100   # live modules per course
ITEMS_PER_MODULE_MAX = 200     # live items per module
PREREQUISITES_PER_MODULE_MAX = 99  # bounded by MODULES_PER_COURSE_MAX (earlier modules only)
INDENT_MAX = 3
URL_MAX = 2000
MODULE_TITLE_MAX = 200         # per language value (LocalizedText)
REQUIREMENT_THRESHOLD_MAX = 999_999.99  # NUMERIC(8,2)
MIN_PERCENT_MAX = 100
REAPPLY_RATE_PER_HOUR = 10     # per user (7.1)
PROGRESS_RATE_PER_HOUR = 600   # per user, shared `progress_limit` for view + done (6.6)

# ------------------------------------------------------------------ enumerations (CHECKs in models.py / 0012)
ITEM_KINDS = ("page", "file", "assignment", "url", "header")
TARGET_KINDS = ("page", "file", "assignment")      # items whose target has its own published/deleted state
REQUIREMENT_TYPES = ("view", "mark_done", "submit", "min_score", "min_percent")
ASSIGNMENT_ONLY_REQUIREMENTS = ("submit", "min_score", "min_percent")  # else 422 `requirement_kind_mismatch`
THRESHOLD_REQUIREMENTS = ("min_score", "min_percent")
PROGRESS_EVENTS = ("viewed", "marked_done", "unmarked_done")
MODULE_STATES = ("locked", "unlocked", "started", "completed")
COMPLETION_MODES = ("all", "any")
HOME_KINDS = ("modules", "page", "assignments")
DEFAULT_HOME_KIND = "assignments"  # server default of courses.home_kind: today's layout

# Submission states that satisfy `submit` / `min_*` (6.2 step 4)
SUBMIT_MET_STATES = ("pending_review", "graded", "excused")

# ------------------------------------------------------------------ lock reasons (6.5, `details.reasons[].kind`)
REASON_UNLOCK_AT = "unlock_at"
REASON_PREREQUISITE = "prerequisite"
REASON_SEQUENTIAL = "sequential"
LOCK_REASON_KINDS = (REASON_UNLOCK_AT, REASON_PREREQUISITE, REASON_SEQUENTIAL)

# ------------------------------------------------------------------ staff outline warnings (5.2; computed)
W_TARGET_UNPUBLISHED = "target_unpublished"
W_TARGET_DELETED = "target_deleted"
W_PREREQUISITE_UNPUBLISHED = "prerequisite_unpublished"
W_PREREQUISITE_DELETED = "prerequisite_deleted"
W_REQUIREMENT_ON_UNPUBLISHED_TARGET = "requirement_on_unpublished_target"
W_UNLOCK_IN_PAST_WITH_LOCKED_STUDENTS = "unlock_in_past_with_locked_students"  # placeholder, none in 8a
WARNING_CODES = (
    W_TARGET_UNPUBLISHED, W_TARGET_DELETED, W_PREREQUISITE_UNPUBLISHED, W_PREREQUISITE_DELETED,
    W_REQUIREMENT_ON_UNPUBLISHED_TARGET, W_UNLOCK_IN_PAST_WITH_LOCKED_STUDENTS,
)

# ------------------------------------------------------------------ prerequisite_invalid reasons (2.4)
PREREQ_NOT_SAME_COURSE = "not_same_course"
PREREQ_NOT_EARLIER = "not_earlier"
PREREQ_DELETED = "deleted"
PREREQ_INVALID_REASONS = (PREREQ_NOT_SAME_COURSE, PREREQ_NOT_EARLIER, PREREQ_DELETED)

# ------------------------------------------------------------------ error codes (5.6; HTTP as noted)
# 422
E_PREREQUISITE_INVALID = "prerequisite_invalid"      # details {module_id, prerequisite_module_id, reason}
E_PREREQUISITE_ORDER = "prerequisite_order"          # details: the pairs an order would break
E_REQUIREMENT_KIND_MISMATCH = "requirement_kind_mismatch"
E_URL_INVALID = "url_invalid"
E_LANGUAGE_NOT_IN_COURSE = "language_not_in_course"
E_HOME_PAGE_INVALID = "home_page_invalid"
E_LIMIT_REACHED = "limit_reached"
E_ORDER_INCOMPLETE = "order_incomplete"
# 409
E_TEMPLATE_LOCKED = "template_locked"
E_ALREADY_PUBLISHED = "already_published"
E_PAGE_CONFLICT = "page_conflict"                    # pages and announcements: stale `rev`
# 413
E_PAYLOAD_TOO_LARGE = "payload_too_large"
E_COURSE_FILES_QUOTA = "course_files_quota"          # details {used, max}
# 423
E_MODULE_LOCKED = "module_locked"                    # details {module_id, module_title, reasons}
# 507
E_STORAGE_FULL = "storage_full"

ERROR_CODES = (
    E_PREREQUISITE_INVALID, E_PREREQUISITE_ORDER, E_REQUIREMENT_KIND_MISMATCH, E_URL_INVALID,
    E_LANGUAGE_NOT_IN_COURSE, E_HOME_PAGE_INVALID, E_LIMIT_REACHED, E_ORDER_INCOMPLETE, E_TEMPLATE_LOCKED,
    E_ALREADY_PUBLISHED, E_PAGE_CONFLICT, E_PAYLOAD_TOO_LARGE, E_COURSE_FILES_QUOTA, E_MODULE_LOCKED, E_STORAGE_FULL,
)
HTTP_STATUS = {
    E_PREREQUISITE_INVALID: 422, E_PREREQUISITE_ORDER: 422, E_REQUIREMENT_KIND_MISMATCH: 422, E_URL_INVALID: 422,
    E_LANGUAGE_NOT_IN_COURSE: 422, E_HOME_PAGE_INVALID: 422, E_LIMIT_REACHED: 422, E_ORDER_INCOMPLETE: 422,
    E_TEMPLATE_LOCKED: 409, E_ALREADY_PUBLISHED: 409, E_PAGE_CONFLICT: 409, E_PAYLOAD_TOO_LARGE: 413,
    E_COURSE_FILES_QUOTA: 413, E_MODULE_LOCKED: 423, E_STORAGE_FULL: 507,
}

# ------------------------------------------------------------------ audit actions
AUDIT_MODULE_REAPPLY = "module.reapply"
