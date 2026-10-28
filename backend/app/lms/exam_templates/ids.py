"""Stable names shared by every Phase 7b slice (PHASE_7B_DESIGN 3, 5.4, 5.6, 6, 9.1). Pure constants: no DB, no app
imports beyond `templates/base.py` (the course-template lock names)."""
from __future__ import annotations

from app.lms.templates import base as tpl_fields

# Version of the `ExamTemplateSpec` JSON shape (the spec's `schema` field).
SPEC_SCHEMA = 1

# ------------------------------------------------------------------ owner scopes and statuses (exam_templates CHECKs)
OWNER_SCOPES = ("platform", "organization", "teacher")
TEMPLATE_STATUSES = ("draft", "published", "archived")

# ------------------------------------------------------------------ error codes (5.6)
E_TEMPLATE_NOT_FOUND = "template_not_found"                    # 404
E_TEMPLATE_NOT_PUBLISHED = "template_not_published"            # 422
E_TEMPLATE_ARCHIVED = "template_archived"                      # 409
E_SPEC_INVALID = "spec_invalid"                                # 422, details [{loc, msg}]
E_NOTHING_TO_PUBLISH = "nothing_to_publish"                    # 422
E_DRAFT_CONFLICT = "draft_conflict"                            # 409
E_TEMPLATE_LOCKED = "template_locked"                          # 409 (6a code; details.source = "exam_template")
E_PRESET_TEMPLATE_EXCLUSIVE = "preset_template_exclusive"      # 422
E_PRESET_NOT_TEMPLATABLE = "preset_not_templatable"            # 409
E_PARAMETER_MISSING = "parameter_missing"                      # 422
E_PARAMETER_INVALID = "parameter_invalid"                      # 422
E_DISPLAY_MODE_NOT_AVAILABLE = "display_mode_not_available"    # 422 (scrolling until 8b, P7B-1)
E_IMPORTER_PROFILE_RESERVED = "importer_profile_reserved"      # 422 ("ort" belongs to the ORT course template)
E_SCHEME_NOT_SHAREABLE = "scheme_not_shareable"                # 422 (P7B-2)
E_TEMPLATE_UPGRADE_NOT_ALLOWED = "template_upgrade_not_allowed"  # 409
E_NOT_A_TEMPLATE_ASSESSMENT = "not_a_template_assessment"      # 422
E_SCOPE_NOT_ALLOWED = "scope_not_allowed"                      # 403
# import (S3)
E_SECTION_NOT_IN_TEMPLATE = "section_not_in_template"          # error
E_TYPE_NOT_ALLOWED_IN_SECTION = "type_not_allowed_in_section"  # error
E_PASSAGE_NOT_ALLOWED = "passage_not_allowed"                  # error
E_TYPE_REQUIRED = "type_required"                              # error
E_COUNT_BELOW_MIN = "count_below_min"                          # warning
E_COUNT_ABOVE_MAX = "count_above_max"                          # warning
E_ATTACH_TARGET_MISMATCH = "attach_target_mismatch"
E_FORMAT_MISMATCH = "format_mismatch"

ERROR_CODES = (
    E_TEMPLATE_NOT_FOUND, E_TEMPLATE_NOT_PUBLISHED, E_TEMPLATE_ARCHIVED, E_SPEC_INVALID, E_NOTHING_TO_PUBLISH,
    E_DRAFT_CONFLICT, E_TEMPLATE_LOCKED, E_PRESET_TEMPLATE_EXCLUSIVE, E_PRESET_NOT_TEMPLATABLE, E_PARAMETER_MISSING,
    E_PARAMETER_INVALID, E_DISPLAY_MODE_NOT_AVAILABLE, E_IMPORTER_PROFILE_RESERVED, E_SCHEME_NOT_SHAREABLE,
    E_TEMPLATE_UPGRADE_NOT_ALLOWED, E_NOT_A_TEMPLATE_ASSESSMENT, E_SCOPE_NOT_ALLOWED,
    E_SECTION_NOT_IN_TEMPLATE, E_TYPE_NOT_ALLOWED_IN_SECTION, E_PASSAGE_NOT_ALLOWED, E_TYPE_REQUIRED,
    E_COUNT_BELOW_MIN, E_COUNT_ABOVE_MAX, E_ATTACH_TARGET_MISMATCH, E_FORMAT_MISMATCH,
)

# Publish issue (snapshot.py, next to too_many_items; an error at publish, P7B-4).
ISSUE_TOO_FEW_ITEMS = "too_few_items"

# ------------------------------------------------------------------ audit (admin_audit_log; migration 0010 widens the
# target_type CHECK with these two values)
AUDIT_TARGET_EXAM_TEMPLATE = "exam_template"
AUDIT_TARGET_ASSESSMENT = "assessment"
AUDIT_PUBLISH = "exam_template.publish"
AUDIT_ARCHIVE = "exam_template.archive"
AUDIT_LOCK = "exam_template.lock"
AUDIT_UNLOCK = "exam_template.unlock"
AUDIT_PROMOTE = "exam_template.promote"
AUDIT_STRUCTURE_UNLOCK = "assessment.structure_unlock"
AUDIT_ACTIONS = (AUDIT_PUBLISH, AUDIT_ARCHIVE, AUDIT_LOCK, AUDIT_UNLOCK, AUDIT_PROMOTE, AUDIT_STRUCTURE_UNLOCK)
# --- Phase 7b S6 begin --- (security review 7b: platform template drafts, save as template, instantiate)
AUDIT_CREATE = "exam_template.create"            # platform scope only
AUDIT_UPDATE = "exam_template.update"            # platform scope only (draft patch)
AUDIT_SAVE_AS = "exam_template.save_as"          # every scope: an assessment's structure copied into a template
AUDIT_INSTANTIATE = "assessment.from_template"   # target the new assessment
AUDIT_ACTIONS = AUDIT_ACTIONS + (AUDIT_CREATE, AUDIT_UPDATE, AUDIT_SAVE_AS, AUDIT_INSTANTIATE)
# --- Phase 7b S6 end ---

# ------------------------------------------------------------------ snapshot (6): additive keys, values from the
# assessment row (None stays None); SNAPSHOT_SCHEMA is unchanged.
SNAPSHOT_TEMPLATE_KEYS = ("exam_template_version_id", "display_mode", "passage_display", "result_view")

# ------------------------------------------------------------------ lock scope (5.4): spec `lock_scope` keys -> the
# course-template lock field names the builder guards pass.
LOCK_SCOPE_MAP: dict[str, frozenset] = {
    "sections": frozenset({tpl_fields.LOCK_SECTION_KEY, tpl_fields.LOCK_SECTION_ORDER,
                           tpl_fields.LOCK_SECTION_ADD_REMOVE}),
    "section_time_limit_s": frozenset({tpl_fields.LOCK_SECTION_TIME_LIMIT}),
    "rules": frozenset({tpl_fields.LOCK_SECTION_RULES}),
    "navigation": frozenset({tpl_fields.LOCK_NAVIGATION}),
    "scheme": frozenset({tpl_fields.LOCK_SCHEME_VERSION}),
    "result_view": frozenset({tpl_fields.LOCK_RESULT_VIEW}),
    "importer_profile": frozenset({tpl_fields.LOCK_IMPORTER_PROFILE}),
    "display_mode": frozenset({tpl_fields.LOCK_DISPLAY_MODE}),
}
LOCK_SCOPE_KEYS = tuple(LOCK_SCOPE_MAP)


def expand_lock_scope(lock_scope) -> frozenset:
    """The course-template lock field names covered by a spec's `lock_scope` list (unknown keys are ignored)."""
    out: set = set()
    for k in lock_scope or ():
        out |= LOCK_SCOPE_MAP.get(k, frozenset())
    return frozenset(out)


# ------------------------------------------------------------------ route policies (9.1; listed in POLICY_NAMES)
POLICY_CREATE = "exam_template_create"
POLICY_MANAGE = "exam_template_manage"
POLICY_READ = "exam_template_read"
POLICY_NAMES = (POLICY_CREATE, POLICY_MANAGE, POLICY_READ)

# --- Phase 8b S1 begin --- (PHASE_8B_DESIGN 5.1, 5.5: sandbox, preview, diff)
E_NOTHING_TO_PREVIEW = "nothing_to_preview"                    # 422 (no draft and no version)
E_PREVIEW_NOT_READY = "preview_not_ready"                      # 422, details.issues (publish issues of the sample)
E_LANGUAGE_NOT_IN_ASSESSMENT = "language_not_in_assessment"    # 422
E_SANDBOX_COURSE = "sandbox_course"                            # 409 (course routes refuse a template's sandbox)
E_DIFF_TARGET_INVALID = "diff_target_invalid"                  # 422 (to=draft without a draft)
E_VERSION_NOT_FOUND = "version_not_found"                      # 404 (diff: unknown version number)
# E_DISPLAY_MODE_NOT_AVAILABLE stays in ERROR_CODES for one phase (old clients); 8b never raises it.
ERROR_CODES = ERROR_CODES + (E_NOTHING_TO_PREVIEW, E_PREVIEW_NOT_READY, E_LANGUAGE_NOT_IN_ASSESSMENT,
                             E_SANDBOX_COURSE, E_DIFF_TARGET_INVALID, E_VERSION_NOT_FOUND)

AUDIT_SANDBOX_CREATE = "exam_template.sandbox_create"
AUDIT_PREVIEW = "exam_template.preview"          # platform scope only, like AUDIT_UPDATE
AUDIT_ACTIONS = AUDIT_ACTIONS + (AUDIT_SANDBOX_CREATE, AUDIT_PREVIEW)

# A sandbox staff enrollment reuses an existing `enrollments.source` value (no CHECK change).
SANDBOX_ENROLLMENT_SOURCE = "staff_add"
# Sample sections carry type and passage rules but never item counts (invariant 3).
SANDBOX_DROPPED_RULE_KEYS = ("min_items", "max_items")

# The preview route starts an attempt (the existing `attempt_start_limit` applies).
POLICY_MANAGE_RATELIMIT = "exam_template_manage+ratelimit"
POLICY_NAMES = POLICY_NAMES + (POLICY_MANAGE_RATELIMIT,)
# --- Phase 8b S1 end ---
