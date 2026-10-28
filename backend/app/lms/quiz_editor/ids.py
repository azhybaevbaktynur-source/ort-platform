"""Stable names shared by every Phase 7c slice (PHASE_7C_DESIGN 3, 5.7, 5.8, 16). Pure constants: no DB, no app
imports. Policy names: none new, every quiz editor route uses a `course:*` policy (6.1)."""
from __future__ import annotations

# Cap of a draft's JSON payload (5.2): create/autosave refuse larger payloads with 413 `payload_too_large`.
DRAFT_PAYLOAD_MAX = 262_144

# ------------------------------------------------------------------ error codes (5.7; HTTP as in core/errors.py)
E_DRAFT_NOT_FOUND = "draft_not_found"                    # 404
E_DRAFT_EXISTS = "draft_exists"                          # 409, details: the existing DraftOut
E_DRAFT_CONFLICT = "draft_conflict"                      # 409, details: {draft_rev, payload, updated_by_name}
E_PAYLOAD_TOO_LARGE = "payload_too_large"                # 413
E_SCOPE_REQUIRED = "scope_required"                      # 409, details: {assessment_count, can_update_all, assessments}
E_SCOPE_NOT_ALLOWED = "scope_not_allowed"                # 403
E_PASSAGE_CHILD_SCOPE = "passage_child_scope"            # 409
E_PASSAGE_NOT_IN_QUIZ_BANK = "passage_not_in_quiz_bank"  # 422
E_QUIZ_BANK_FOLLOWS_QUIZ = "quiz_bank_follows_quiz"      # 409
E_TARGET_NOT_SHARED_BANK = "target_not_shared_bank"      # 422
E_QUESTION_HAS_PASSAGE = "question_has_passage"          # 409
E_QUIZ_BANK_PRIVATE = "quiz_bank_private"                # 422 (16: a quiz bank is private to its own quiz)
# existing codes the quiz editor reuses (owned by content / assessments)
E_VERSION_CONFLICT = "version_conflict"                  # 409 (content)
E_INVALID_QUESTION_DATA = "invalid_question_data"        # 422 (content)
E_ITEM_TYPE_NOT_ALLOWED = "item_type_not_allowed"        # 422 (builder)
E_ITEM_LANGUAGE_MISMATCH = "item_language_mismatch"      # 422 (builder)
E_TOO_MANY_ITEMS = "too_many_items"                      # 422 (builder)
E_ITEM_NOT_FOUND = "item_not_found"                      # 404 (builder)

ERROR_CODES = (
    E_DRAFT_NOT_FOUND, E_DRAFT_EXISTS, E_DRAFT_CONFLICT, E_PAYLOAD_TOO_LARGE, E_SCOPE_REQUIRED, E_SCOPE_NOT_ALLOWED,
    E_PASSAGE_CHILD_SCOPE, E_PASSAGE_NOT_IN_QUIZ_BANK, E_QUIZ_BANK_FOLLOWS_QUIZ, E_TARGET_NOT_SHARED_BANK,
    E_QUESTION_HAS_PASSAGE, E_QUIZ_BANK_PRIVATE,
)

# Publish issue (warning, 5.8): one per unfinished draft; publishing still succeeds.
ISSUE_UNFINISHED_DRAFTS = "unfinished_drafts"

# Edit scope of a commit (7c-2) and what a commit did (5.4).
SCOPES = ("all", "this")
APPLIED = ("created", "in_place", "all", "this", "unchanged")

# Bank listing filter (6.1): `GET /courses/{course_id}/banks?kind=`; `quiz` = assessment_id IS NOT NULL.
BANK_KINDS = ("all", "shared", "quiz")
