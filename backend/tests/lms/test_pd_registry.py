"""Phase 11 S1: the personal-data registry (PHASE_11_DESIGN 3.5). A new foreign key to `users.id`, or a new text or JSON
column the name scan matches, fails here until someone decides what deletion does to it."""
from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa

import app.models  # noqa: F401
from app.db.session import Base
from app.lms.privacy.export import sections
from app.lms.privacy.registry import ACTIONS, ENTRIES, NAME_SCAN, NOT_PERSONAL, exported_columns, markdown

REGISTERED = {(e.table, e.column) for e in ENTRIES}
DOC = Path(__file__).resolve().parents[3] / "docs" / "PERSONAL_DATA.md"


def _is_text(col) -> bool:
    return isinstance(col.type, (sa.String, sa.Text, sa.JSON)) or "JSON" in type(col.type).__name__


def test_every_foreign_key_to_users_is_registered():
    missing = [(t.name, c.name) for t in Base.metadata.tables.values() for c in t.columns
               if any(fk.target_fullname == "users.id" for fk in c.foreign_keys) and (t.name, c.name) not in REGISTERED]
    assert missing == []


def test_every_column_the_name_scan_matches_is_decided():
    missing = [(t.name, c.name) for t in Base.metadata.tables.values() for c in t.columns
               if _is_text(c) and NAME_SCAN.search(c.name) and (t.name, c.name) not in REGISTERED
               and (t.name, c.name) not in NOT_PERSONAL]
    assert missing == []


def test_the_registry_names_real_columns_and_valid_actions():
    tables = Base.metadata.tables
    for table, column in REGISTERED | set(NOT_PERSONAL):
        assert table in tables and column in tables[table].c, (table, column)
    assert {e.action for e in ENTRIES} <= set(ACTIONS)
    assert len(REGISTERED) == len(ENTRIES)  # no column twice
    assert not REGISTERED & set(NOT_PERSONAL)


def test_immutable_tables_are_only_ever_kept():
    """Invariant 2: the registry cannot promise a write to an immutable table."""
    for entry in ENTRIES:
        if entry.table in ("grade_events", "attempts", "attempt_sections", "attempt_items", "attempt_grades",
                           "consent_records"):
            assert entry.action in ("keep_immutable", "keep_tombstone", "none"), entry


def test_every_exported_table_reaches_the_export():
    exported_tables = {e.table for e in ENTRIES if e.exported}
    assert exported_tables == {"users", "assignment_submissions", "assets", "submissions", "attempt_items",
                               "consent_records", "data_requests", "teacher_requests", "access_passes"}
    assert {s.name for s in sections()} >= {"enrollments", "grades", "course_grades", "hand_ins", "consents", "requests",
                                            "teacher_requests", "access_passes"}
    assert exported_columns("assets") == ["original_filename"]


def test_the_document_is_current():
    assert DOC.read_text(encoding="utf-8") == markdown(), \
        "run: cd backend && python -m app.lms.privacy.registry --markdown > ../docs/PERSONAL_DATA.md"
