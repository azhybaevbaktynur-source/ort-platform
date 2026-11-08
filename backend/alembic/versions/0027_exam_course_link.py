"""Lesson course linked to an exam course (docs/phases/TEACHER_TO_STUDENT_MAP.md 2.2, slice S1)

Revision ID: 0027_exam_course_link
Revises: 0026_course_cover
Create Date: 2026-11-08

Additive, no data step: `courses.exam_course_id` (null for every existing course, ORT included), a self-referencing
foreign key with ON DELETE SET NULL (a removed exam course detaches its lesson courses), an index on it (the lesson
course list and the SET NULL lookup) and a CHECK that a course never links to itself. Downgrade drops the check, the
index, the key and the column (the links are lost; the courses stay).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_exam_course_link"
down_revision: Union[str, None] = "0026_course_cover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EXAM_FK = "fk_courses_exam_course_id_courses"
NOT_SELF = "ck_courses_exam_course_not_self"


def upgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("exam_course_id", sa.Uuid(), nullable=True))
        b.create_foreign_key(op.f(EXAM_FK), "courses", ["exam_course_id"], ["id"], ondelete="SET NULL")
        b.create_index(op.f("ix_courses_exam_course_id"), ["exam_course_id"])
        b.create_check_constraint(op.f(NOT_SELF), "exam_course_id IS NULL OR exam_course_id <> id")


def downgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.drop_constraint(op.f(NOT_SELF), type_="check")
        b.drop_index(op.f("ix_courses_exam_course_id"))
        b.drop_constraint(op.f(EXAM_FK), type_="foreignkey")
        b.drop_column("exam_course_id")
