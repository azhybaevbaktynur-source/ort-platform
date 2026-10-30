"""Fixed organization ids (PHASE_6_DESIGN section 4). Migration 0008 copies these formulas; keep them identical."""
from __future__ import annotations

import hashlib
import uuid

ORG_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/organizations")


def platform_org_id() -> uuid.UUID:
    return uuid.uuid5(ORG_NS, "org:platform")


def personal_org_id(user_id: str) -> uuid.UUID:
    return uuid.uuid5(ORG_NS, f"org:personal:{user_id}")


def personal_org_slug(user_id: str) -> str:
    return "t-" + hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


# --- Phase 9 S1 begin --- (PHASE_9_DESIGN 4.1-4.4, 4.12: error codes and caps of the organization packages)
E_SHARING_DISABLED = "sharing_disabled"            # 409/422: root setting off, or a personal organization
E_QUIZ_BANK_NOT_SHAREABLE = "quiz_bank_not_shareable"  # 422 (quiz_editor.quiz_banks.assert_shareable)
E_BANK_TOO_LARGE = "bank_too_large"                # 422: copy > BANK_COPY_MAX_QUESTIONS
E_SETTINGS_ON_ROOT = "settings_on_root"            # 409: settings are written on the root only
E_DEPARTMENT_DEPTH = "department_depth"            # 409: depth > 2 after create / move
E_DEPARTMENT_CYCLE = "department_cycle"            # 409: move under itself or a descendant
E_DEPARTMENT_CAP = "department_cap"                # 409: > 200 organizations in one tree
E_DEPARTMENT_PARENT = "department_parent_invalid"  # 422: parent outside the tree, or a personal organization
E_FORBIDDEN_COLUMN = "forbidden_column"            # 422: a password-like CSV header
E_FILE_CHANGED = "file_changed"                    # 422: apply with a different file than the dry run
E_ALREADY_APPLIED = "already_applied"              # 409: same file applied to the same target
E_ROSTER_TOO_LARGE = "roster_too_large"            # 413/422: > 256 KiB or > 500 rows

BANK_COPY_MAX_QUESTIONS = 2000
BANK_COPY_CHUNK = 200
BANK_COPY_RATE_PER_HOUR = 20       # `bank_copy_1h`, per actor
ROSTER_MAX_BYTES = 256 * 1024
ROSTER_MAX_ROWS = 500
ROSTER_REPORT_ROWS = 500
ROSTER_CHUNK = 50
ROSTER_IMPORTS_PER_DAY = 5         # `roster_import_1d`, per organization
ROSTER_ROWS_PER_DAY = 1000         # `roster_rows_1d`, per organization (applied rows)
FORBIDDEN_HEADER_RE = r"^(password|pass|pwd)"
# --- Phase 9 S1 end ---
