"""Course exam family and subject (docs/phases/STUDENT_IA_DESIGN.md 6.1, step 3a slice S1)

Revision ID: 0033_course_exam_family
Revises: 0032_teacher_notice_dismissed
Create Date: 2026-11-13

Additive, two nullable columns and one index: `courses.exam_family` (`ort`, `nct`; null = «Другие курсы») and
`courses.subject` (null = the family's main course). No CHECK on the values: the registry
`app/lms/courses/exam_families.py` holds them and the service validates against it. Backfill, two bounded UPDATEs in
this order: ORT template courses get `ort`; then courses linked to an exam course (`exam_course_id`) take the parent's
family. Teacher courses stay null. Downgrade drops the index and both columns (nothing reads them before step 3a S3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033_course_exam_family"
down_revision: Union[str, None] = "0032_teacher_notice_dismissed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ix_courses_exam_family_subject"


def upgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("exam_family", sa.String(length=16), nullable=True))
        b.add_column(sa.Column("subject", sa.String(length=32), nullable=True))
        b.create_index(op.f(INDEX), ["exam_family", "subject"])
    op.execute("UPDATE courses SET exam_family = 'ort' WHERE template_key = 'ort' AND exam_family IS NULL")
    op.execute(
        "UPDATE courses SET exam_family = (SELECT p.exam_family FROM courses p WHERE p.id = courses.exam_course_id) "
        "WHERE exam_course_id IS NOT NULL AND exam_family IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.drop_index(op.f(INDEX))
        b.drop_column("subject")
        b.drop_column("exam_family")
