"""phase 5 cutover: export the old ORT exam sets, drop the old tables and the old users columns (one-way)

Revision ID: 0006_phase5_cutover
Revises: 0005_phase4_grading
Create Date: 2026-10-23

Design: docs/phases/PHASE_5_DESIGN.md section 3.1 (P5-1, P5-2, P5-8, P5-10). Core SQL only: the ORM models of the
old tables are deleted with this phase. Every exam set that has questions is copied into `legacy_ort_export` in the
same transaction as the drops, so the drop can never lose content; `app.lms.ort.seed.ensure_ort_courses()` turns
the export rows into course banks and assessments at startup.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import sqlite as sqlite_dialect

revision: str = "0006_phase5_cutover"
down_revision: Union[str, None] = "0005_phase4_grading"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# Frozen copy of the ORT section order (AGENTS.md 5.2): main sections, then subjects, then anything else.
SECTION_ORDER = ("math_1", "math_2", "analogies", "reading", "grammar",
                 "chemistry", "biology", "physics", "advanced_math", "history", "english", "native_language",
                 "math_subject", "kyrgyz_lang_lit", "russian_lang_lit")
OLD_TABLES = ("question_sources", "test_attempts", "exam_access", "questions", "exam_sets")  # FK order
OLD_USER_COLUMNS = ("role", "target_score", "exams_taken", "current_score", "starting_score")
CHUNK = 500

_exam_sets = sa.table(
    "exam_sets", sa.column("id", sa.String), sa.column("title", sa.String), sa.column("description", sa.Text),
    sa.column("language", sa.String), sa.column("exam_type", sa.String), sa.column("sections", sa.JSON),
    sa.column("max_attempts", sa.Integer), sa.column("available_from", sa.String),
    sa.column("available_until", sa.String), sa.column("question_ids", sa.JSON),
)
_questions = sa.table(
    "questions", sa.column("id", sa.String), sa.column("section", sa.String), sa.column("topic", sa.String),
    sa.column("difficulty", sa.String), sa.column("stem", sa.Text), sa.column("column_a", sa.Text),
    sa.column("column_b", sa.Text), *(sa.column(f"option_{x}", sa.Text) for x in "abcde"),
    sa.column("correct_option", sa.String), sa.column("passage_text", sa.Text), sa.column("explanation", sa.Text),
    sa.column("image_url", sa.String), sa.column("tags", sa.JSON), sa.column("exam_set_id", sa.String),
    sa.column("position", sa.Integer), sa.column("q_num", sa.String), sa.column("created_at", sa.DateTime),
)
_sources = sa.table(
    "question_sources", sa.column("external_id", sa.String), sa.column("question_id", sa.String),
    sa.column("source_id", sa.String), sa.column("q_num", sa.String), sa.column("fixed", sa.Boolean),
)


def _export_table() -> sa.Table:
    return sa.table(
        "legacy_ort_export", sa.column("exam_set_id", sa.String), sa.column("language", sa.String),
        sa.column("exam_type", sa.String), sa.column("title", sa.Text), sa.column("description", sa.Text),
        sa.column("sections", JSONType), sa.column("max_attempts", sa.Integer),
        sa.column("available_from", sa.String), sa.column("available_until", sa.String),
        sa.column("source_id", sa.String), sa.column("question_count", sa.Integer), sa.column("payload", JSONType),
        sa.column("exported_at", sa.DateTime(timezone=True)),
    )


def _cut(value: Optional[str], n: int) -> Optional[str]:
    return None if value is None else str(value)[:n]


def _sort_key(q: dict) -> tuple:
    sec = (q["section"] or "").strip().lower()
    rank = SECTION_ORDER.index(sec) if sec in SECTION_ORDER else len(SECTION_ORDER)
    pos = q["position"]
    created = q["created_at"]
    return (rank, sec if rank == len(SECTION_ORDER) else "", pos is None, pos if pos is not None else 0,
            created is None, str(created) if created is not None else "", q["id"])


def _set_question_ids(bind, set_id: str, listed) -> list[str]:
    ids = [r[0] for r in bind.execute(sa.select(_questions.c.id).where(_questions.c.exam_set_id == set_id))]
    seen = set(ids)
    for qid in listed if isinstance(listed, list) else []:
        if isinstance(qid, str) and qid not in seen:
            seen.add(qid)
            ids.append(qid)
    return ids


def _load_questions(bind, ids: list[str]) -> list[dict]:
    rows: list[dict] = []
    for k in range(0, len(ids), CHUNK):
        part = ids[k:k + CHUNK]
        rows += [dict(r) for r in bind.execute(sa.select(_questions).where(_questions.c.id.in_(part))).mappings()]
    return rows


def _load_sources(bind, ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for k in range(0, len(ids), CHUNK):
        part = ids[k:k + CHUNK]
        for r in bind.execute(sa.select(_sources).where(_sources.c.question_id.in_(part))).mappings():
            out[r["question_id"]] = dict(r)
    return out


def _payload_item(q: dict, src: Optional[dict]) -> dict:
    tags = q["tags"] if isinstance(q["tags"], list) else []
    return {
        "legacy_id": q["id"], "section": q["section"], "topic": q["topic"], "difficulty": q["difficulty"],
        "stem": q["stem"], "column_a": q["column_a"], "column_b": q["column_b"],
        **{f"option_{x}": q[f"option_{x}"] for x in "abcde"},
        "correct_option": q["correct_option"], "passage_text": q["passage_text"], "explanation": q["explanation"],
        "image_url": q["image_url"], "tags": [str(t) for t in tags], "position": q["position"],
        "q_num": (src or {}).get("q_num") or q["q_num"],
        "external_id": (src or {}).get("external_id"), "fixed": bool((src or {}).get("fixed") or False),
    }


def export_exam_sets(bind) -> list[str]:
    """Copy every exam set with >= 1 question into legacy_ort_export (ON CONFLICT DO NOTHING). Returns the ids."""
    export = _export_table()
    insert = postgresql.insert if bind.dialect.name == "postgresql" else sqlite_dialect.insert
    now = datetime.now(timezone.utc)
    exported: list[str] = []
    skipped_empty: list[str] = []
    used_sources: set[tuple] = set()
    for es in bind.execute(sa.select(_exam_sets).order_by(_exam_sets.c.id)).mappings().all():
        ids = _set_question_ids(bind, es["id"], es["question_ids"])
        questions = _load_questions(bind, ids) if ids else []
        if not questions:
            skipped_empty.append(es["id"])
            continue
        questions.sort(key=_sort_key)
        sources = _load_sources(bind, [q["id"] for q in questions])
        language = _cut(es["language"] or "ky", 2)
        distinct = {s["source_id"] for s in sources.values() if s.get("source_id")}
        source_id = _cut(next(iter(distinct)) if len(distinct) == 1 else f"legacy_{es['id']}", 120)
        if (language, source_id) in used_sources:  # two sets of one source in one course: keep the banks apart
            source_id = _cut(f"legacy_{es['id']}", 120)
        used_sources.add((language, source_id))
        payload = [_payload_item(q, sources.get(q["id"])) for q in questions]
        stmt = insert(export).values(
            exam_set_id=es["id"], language=language, exam_type=_cut(es["exam_type"] or "full_main", 16),
            title=es["title"] or es["id"], description=es["description"],
            sections=es["sections"] if isinstance(es["sections"], list) else [],
            max_attempts=es["max_attempts"], available_from=_cut(es["available_from"], 40),
            available_until=_cut(es["available_until"], 40), source_id=source_id, question_count=len(payload),
            payload=payload, exported_at=now,
        ).on_conflict_do_nothing(index_elements=["exam_set_id"])
        bind.execute(stmt)
        exported.append(es["id"])
    log.info("0006: exported %d exam set(s) with questions %s; skipped %d empty exam set(s)",
             len(exported), exported, len(skipped_empty))
    return exported


def upgrade() -> None:
    bind = op.get_bind()
    # 1. export table (model: app.lms.ort.models.LegacyOrtExport)
    op.create_table(
        "legacy_ort_export",
        sa.Column("exam_set_id", sa.String(length=200), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("exam_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sections", JSONType, nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column("available_from", sa.String(length=40), nullable=True),
        sa.Column("available_until", sa.String(length=40), nullable=True),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", JSONType, nullable=True),
        sa.PrimaryKeyConstraint("exam_set_id", name=op.f("pk_legacy_ort_export")),
    )
    tables = set(sa.inspect(bind).get_table_names())
    # 2. export (fresh databases reach this point with empty old tables: nothing is exported)
    if {"exam_sets", "questions", "question_sources"} <= tables:
        export_exam_sets(bind)
    # 3. defensive repeat of 0002: old admins are platform admins and approved teachers before `role` goes
    users = sa.table("users", sa.column("role", sa.String), sa.column("is_platform_admin", sa.Boolean),
                     sa.column("teacher_status", sa.String))
    op.execute(users.update().where(users.c.role == "admin")
               .values(is_platform_admin=sa.true(), teacher_status="approved"))
    # 4. drop the old tables, children first
    for table in OLD_TABLES:
        if table in tables:
            op.drop_table(table)
    # 5. old users columns. SQLite recreates the table: the reflected copy keeps the self-FK, the named CHECKs and
    # ix_users_teacher_status (asserted in tests/test_migration_0006_data.py); PostgreSQL runs plain ALTERs.
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("users", recreate=recreate) as b:
        for col in OLD_USER_COLUMNS:
            b.drop_column(col)


def downgrade() -> None:
    raise NotImplementedError("0006_phase5_cutover is one-way; restore the pre-cutover Neon branch")
