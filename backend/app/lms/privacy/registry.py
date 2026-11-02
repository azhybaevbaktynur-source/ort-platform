"""The personal-data registry (PHASE_11_DESIGN 3.5): what the platform holds about a person and what happens to it.

`tests/lms/test_pd_registry.py` fails when a foreign key to `users.id`, or a text or JSON column the name scan matches, is
neither here nor in `NOT_PERSONAL`. `export.py` reads `exported` from here. The owner and the lawyer read the same table:

    python -m app.lms.privacy.registry --markdown > ../docs/PERSONAL_DATA.md
"""
from __future__ import annotations

import re
import sys
from typing import NamedTuple


class Entry(NamedTuple):
    table: str
    column: str
    category: str
    action: str  # null, scrub, keep_tombstone, keep_immutable, delete_row, erase_file, none
    exported: bool = False


ACTIONS = ("null", "scrub", "keep_tombstone", "keep_immutable", "delete_row", "erase_file", "none")
ACTION_TEXT = {
    "null": "Emptied",
    "scrub": "Replaced",
    "keep_tombstone": "Kept: points at the tombstone, which holds nothing personal",
    "keep_immutable": "Kept unchanged: immutable record (for the lawyer, design 9)",
    "delete_row": "Row deleted",
    "erase_file": "File erased",
    "none": "Kept: holds no personal data once the account is a tombstone",
}

# Columns the name scan below must find here or in NOT_PERSONAL.
NAME_SCAN = re.compile(r"email|mail|phone|name|note|message|reason|comment|feedback|answer|response|body|details|report"
                       r"|token|ip_hash|payload|text|file", re.I)


def _refs(table: str, *columns: str, action: str = "none") -> list[Entry]:
    return [Entry(table, c, "user reference", action) for c in columns]


ENTRIES: list[Entry] = [
    # the account
    Entry("users", "email", "contact", "scrub", True),
    Entry("users", "display_name", "identity", "null", True),
    Entry("users", "phone", "contact", "null", True),
    Entry("users", "locale", "preference", "null", True),
    Entry("users", "age_band", "age", "null", True),
    Entry("users", "password_hash", "credential", "scrub"),
    Entry("users", "reset_token", "credential", "null"),
    Entry("users", "email_code_hash", "credential", "null"),
    Entry("users", "disabled_reason", "account state", "scrub"),
    # enrollment
    Entry("enrollments", "invite_token_hash", "credential", "null"),
    Entry("enrollment_accommodations", "note", "may be medical", "null"),
    Entry("assignment_overrides", "note", "may be medical", "null"),
    Entry("enrollment_applications", "answers", "form answers", "scrub"),
    Entry("enrollment_applications", "decision_note", "about the person", "null"),
    Entry("course_goals", "target_percent", "own goal", "delete_row"),
    # hand-ins and grades
    Entry("assignment_submissions", "body_text", "own work", "scrub", True),
    Entry("assets", "original_filename", "own work (hand-in and feedback files)", "erase_file", True),
    Entry("submissions", "feedback_text", "about the person", "null", True),
    Entry("submissions", "override_reason", "about the person", "null"),
    Entry("submission_rubric_scores", "comment", "about the person", "null"),
    # kept because the rows are immutable (design 3.4, listed for the lawyer)
    Entry("attempt_items", "response", "own answers", "keep_immutable", True),
    Entry("attempt_items", "feedback", "about the person", "keep_immutable"),
    Entry("grade_events", "reason", "about the person", "keep_immutable"),
    # other rows about the person
    Entry("invitations", "email", "contact", "scrub"),
    Entry("invitations", "message", "about the person", "null"),
    Entry("teacher_requests", "message", "own text", "null", True),
    Entry("teacher_requests", "reason", "about the person", "null", True),
    Entry("teacher_requests", "applicant_name", "identity", "null", True),
    Entry("teacher_requests", "school", "own text", "null", True),
    Entry("teacher_requests", "subject", "own text", "null", True),
    Entry("teacher_requests", "phone", "contact", "null", True),
    Entry("teacher_requests", "phone_purge_after", "retention date of the phone", "null"),
    Entry("admin_audit_log", "details", "keys email, display_name, age band", "scrub"),
    Entry("admin_audit_log", "reason", "about the person", "null"),
    Entry("admin_audit_log", "ip_hash", "network", "null"),
    Entry("organizations", "name", "a personal organization carries its owner's name", "scrub"),
    # consent evidence, kept unchanged
    Entry("consent_records", "locale", "consent evidence", "none", True),
    Entry("data_requests", "reject_code", "request evidence", "none", True),
    # every foreign key to users.id
    *_refs("admin_audit_log", "actor_id", action="keep_tombstone"),
    *_refs("announcements", "author_id", action="keep_tombstone"),
    *_refs("announcements", "deleted_by_id"),
    *_refs("assessment_versions", "created_by_id"),
    *_refs("assessments", "created_by_id", "deleted_by_id"),
    *_refs("assets", "owner_id", action="keep_tombstone"),
    *_refs("assets", "deleted_by_id"),
    *_refs("assignment_overrides", "set_by_id"),
    *_refs("assignment_submissions", "user_id", action="keep_tombstone"),
    *_refs("assignments", "created_by_id", "deleted_by_id"),
    *_refs("attempt_items", "graded_by_id"),
    *_refs("attempts", "user_id", action="keep_tombstone"),
    *_refs("bank_questions", "deleted_by_id"),
    *_refs("consent_records", "user_id", "granted_by_id", action="keep_tombstone"),
    *_refs("course_files", "created_by_id", "deleted_by_id"),
    *_refs("course_modules", "created_by_id", "deleted_by_id"),
    *_refs("courses", "owner_id", action="keep_tombstone"),
    *_refs("courses", "deleted_by_id"),
    *_refs("data_requests", "user_id", "requested_by_id", action="keep_tombstone"),
    *_refs("data_requests", "handled_by_id"),
    *_refs("enrollment_accommodations", "set_by_id"),
    *_refs("enrollment_applications", "user_id", action="keep_tombstone"),
    *_refs("enrollment_applications", "decided_by_id"),
    *_refs("enrollment_events", "actor_id"),
    *_refs("enrollment_forms", "created_by_id"),
    *_refs("enrollments", "user_id", action="keep_tombstone"),
    *_refs("enrollments", "removed_by_id"),
    *_refs("exam_template_versions", "published_by_id"),
    *_refs("exam_templates", "owner_user_id", action="keep_tombstone"),
    *_refs("exam_templates", "created_by_id", "deleted_by_id"),
    *_refs("grade_categories", "deleted_by_id"),
    *_refs("grade_events", "actor_id", action="keep_immutable"),
    *_refs("grading_scheme_versions", "created_by_id", action="keep_immutable"),
    *_refs("grading_schemes", "owner_user_id", action="keep_tombstone"),
    *_refs("grading_schemes", "deleted_by_id"),
    *_refs("guardian_links", "guardian_user_id", "student_user_id", action="keep_tombstone"),
    *_refs("guardian_links", "revoked_by_id"),
    *_refs("guardian_pairing_codes", "student_user_id", action="keep_tombstone"),
    *_refs("invitations", "invited_by_id", action="keep_tombstone"),
    *_refs("invitations", "accepted_user_id", "revoked_by_id"),
    *_refs("module_items", "deleted_by_id"),
    *_refs("organization_members", "user_id", action="keep_tombstone"),
    *_refs("organization_members", "invited_by_id", "removed_by_id"),
    *_refs("organization_roster_imports", "created_by_id"),
    *_refs("organization_template_grants", "granted_by_id", "revoked_by_id"),
    *_refs("organizations", "created_by_id"),
    *_refs("pages", "created_by_id", "updated_by_id", "deleted_by_id"),
    *_refs("passage_versions", "created_by_id"),
    *_refs("passages", "deleted_by_id"),
    *_refs("question_banks", "owner_id", action="keep_tombstone"),
    *_refs("question_banks", "deleted_by_id", "shared_by_id"),
    *_refs("question_drafts", "created_by_id", "updated_by_id"),
    *_refs("question_versions", "created_by_id"),
    *_refs("submissions", "user_id", action="keep_tombstone"),
    *_refs("submissions", "graded_by_id", "override_by_id"),
    *_refs("teacher_requests", "user_id", action="keep_tombstone"),
    *_refs("teacher_requests", "decided_by_id"),
    *_refs("translation_groups", "created_by_id"),
    *_refs("users", "disabled_by_id"),
]

# Matched by the name scan, but they hold no personal data. Why, per column.
NOT_PERSONAL: dict[tuple[str, str], str] = {
    ("announcements", "body_md"): "course content written by staff",
    ("announcements", "body_html"): "course content written by staff",
    ("bank_questions", "search_text"): "question text",
    ("guardian_pairing_codes", "code_hash"): "keyed hash of a short-lived code, revoked with the account",
    ("invitations", "token_hash"): "hash of a random token",
    ("legacy_ort_export", "payload"): "old ORT questions and sources exported in migration 0006: no user data",
    ("organization_roster_imports", "file_name"): "an admin's file name",
    ("organization_roster_imports", "file_sha256"): "hash of an admin's file",
    ("organization_roster_imports", "report"): "line numbers, results and masked emails only (`mask_email`)",
    ("organizations", "suspended_reason"): "a fixed code",
    ("pages", "body_md"): "course content written by staff",
    ("pages", "body_html"): "course content written by staff",
    ("passage_versions", "body"): "question content",
    ("question_drafts", "payload"): "question content written by staff",
    ("enrollment_events", "details"): "ids and fixed reasons only",
    ("attempts", "submit_reason"): "a fixed code",
    ("attempt_sections", "close_reason"): "a fixed code",
    ("policy_versions", "body_en"): "policy text",
    ("policy_versions", "body_ky"): "policy text",
    ("policy_versions", "body_ru"): "policy text",
}


def by_table() -> dict[str, list[Entry]]:
    out: dict[str, list[Entry]] = {}
    for entry in ENTRIES:
        out.setdefault(entry.table, []).append(entry)
    return out


def exported_columns(table: str) -> list[str]:
    return [e.column for e in ENTRIES if e.table == table and e.exported]


def markdown() -> str:
    """The personal-data table. References to users are one line per table: the action is what matters."""
    lines = [
        "# Personal data",
        "",
        "Generated by `python -m app.lms.privacy.registry --markdown`; a test fails when it is out of date. The design is",
        "`docs/phases/PHASE_11_DESIGN.md` 3.4. Draft for the owner and the lawyer: nothing here is a legal decision.",
        "",
        "Erased data stays in the database provider's history until its restore window passes.",
        "",
        "| Table | Column | What it is | On deletion | In the export |",
        "|---|---|---|---|---|",
    ]
    for table, entries in sorted(by_table().items()):
        for e in sorted((e for e in entries if e.category != "user reference"), key=lambda x: x.column):
            lines.append(f"| `{table}` | `{e.column}` | {e.category} | {ACTION_TEXT[e.action]} | "
                         f"{'Yes' if e.exported else 'No'} |")
    lines += ["", "## References to the account", "",
              "These point at the tombstone row, which holds nothing personal after deletion.", "",
              "| Table | Columns |", "|---|---|"]
    for table, entries in sorted(by_table().items()):
        refs = sorted(e.column for e in entries if e.category == "user reference")
        if refs:
            lines.append(f"| `{table}` | {', '.join(f'`{c}`' for c in refs)} |")
    lines += ["", "## Matched by the name scan, not personal", "", "| Table | Column | Why |", "|---|---|---|"]
    for (table, column), why in sorted(NOT_PERSONAL.items()):
        lines.append(f"| `{table}` | `{column}` | {why} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if "--markdown" not in sys.argv[1:]:
        raise SystemExit("usage: python -m app.lms.privacy.registry --markdown")
    sys.stdout.write(markdown())
