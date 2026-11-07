"""Pro subscription: plan of a pass and the owner's Pro settings (docs/phases/SUBSCRIPTION_DESIGN.md 2, slice F6a)

Revision ID: 0025_pro
Revises: 0024_course_lessons
Create Date: 2026-11-07

Additive, no data step: `access_passes.plan` (null for every existing pass; set only by new grants by plan), the
`platform_settings` key/value table (empty; defaults live in `app/lms/access/plans.py`), and one more audit target type
(`platform_setting`). Downgrade drops the column and the table and deletes the audit rows of the new target type (the
plan labels and the owner's texts are lost; passes and codes are not).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0025_pro"
down_revision: Union[str, None] = "0024_course_lessons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TARGETS = ("target_type IN ('user','course','teacher_request','enrollment','organization','invitation',"
               "'exam_template','assessment','access_batch','access_code','access_pass')")
NEW_TARGETS = ("target_type IN ('user','course','teacher_request','enrollment','organization','invitation',"
               "'exam_template','assessment','access_batch','access_code','access_pass','platform_setting')")


def upgrade() -> None:
    with op.batch_alter_table("access_passes") as b:
        b.add_column(sa.Column("plan", sa.String(16), nullable=True))
        b.create_check_constraint(op.f("ck_access_passes_plan_valid"),
                                  "plan IS NULL OR plan IN ('month_1','month_3','season')")

    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name=op.f("fk_platform_settings_updated_by_id_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_platform_settings")),
    )

    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), NEW_TARGETS)


def downgrade() -> None:
    op.execute("DELETE FROM admin_audit_log WHERE target_type = 'platform_setting'")
    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), OLD_TARGETS)
    op.drop_table("platform_settings")
    with op.batch_alter_table("access_passes") as b:
        b.drop_constraint(op.f("ck_access_passes_plan_valid"), type_="check")
        b.drop_column("plan")
