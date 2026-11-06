"""S3 free and paid exams: access tier of a test, access passes, activation code batches and codes
(docs/phases/S3_ACCESS_DESIGN.md 2)

Revision ID: 0022_access
Revises: 0021_admin_mfa
Create Date: 2026-11-06

Additive. `assessments.access_tier` is `free` for every existing row (server default), and every existing course of the
platform organization's tree gets `settings.practice_free = true` (review of S3), so nothing locks on deploy; the owner
switches tests to paid and practice off when selling starts. New platform courses keep the default (practice needs a
pass). The downgrade leaves `practice_free` in the settings (an unknown key is ignored there). Three new tables, empty. The audit log accepts three more target types
(`access_batch`, `access_code`, `access_pass`). Downgrade drops the tables and the column and deletes the audit rows of
the new target types (lossy by design: passes and codes go away with the feature).
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022_access"
down_revision: Union[str, None] = "0021_admin_mfa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TARGETS = ("target_type IN ('user','course','teacher_request','enrollment','organization','invitation',"
               "'exam_template','assessment')")
NEW_TARGETS = ("target_type IN ('user','course','teacher_request','enrollment','organization','invitation',"
               "'exam_template','assessment','access_batch','access_code','access_pass')")


# app/lms/organizations/ids.py::platform_org_id, copied (a migration never imports app code that may change)
PLATFORM_HEX = uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/organizations"), "org:platform").hex


def _practice_free_for_existing_platform_courses() -> None:
    conn = op.get_bind()
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    courses = sa.table("courses", sa.column("id", sa.Uuid()), sa.column("settings", json_type),
                       sa.column("organization_id", sa.Uuid()))
    orgs = sa.table("organizations", sa.column("id", sa.Uuid()), sa.column("path", sa.String()))
    rows = conn.execute(sa.select(courses.c.id, courses.c.settings)
                        .select_from(courses.join(orgs, orgs.c.id == courses.c.organization_id))
                        .where(orgs.c.path.like(f"{PLATFORM_HEX}%"))).all()
    for cid, settings in rows:
        merged = dict(settings or {})
        merged["practice_free"] = True
        conn.execute(courses.update().where(courses.c.id == cid).values(settings=merged))


def upgrade() -> None:
    with op.batch_alter_table("assessments") as b:
        b.add_column(sa.Column("access_tier", sa.String(8), nullable=False, server_default="free"))
        b.create_check_constraint(op.f("ck_assessments_access_tier_valid"), "access_tier IN ('free','paid')")

    op.create_table(
        "activation_code_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(duration_days IS NULL) <> (ends_on IS NULL)",
                           name=op.f("ck_activation_code_batches_one_length")),
        sa.CheckConstraint("duration_days IS NULL OR (duration_days >= 1 AND duration_days <= 400)",
                           name=op.f("ck_activation_code_batches_duration_valid")),
        sa.CheckConstraint("count >= 1 AND count <= 500", name=op.f("ck_activation_code_batches_count_valid")),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"],
                                name=op.f("fk_activation_code_batches_created_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activation_code_batches")),
    )
    op.create_index("ix_activation_code_batches_created_at", "activation_code_batches", ["created_at", "id"])

    op.create_table(
        "activation_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("code_hmac", sa.String(64), nullable=False),
        sa.Column("code_enc", sa.String(100), nullable=False),
        sa.Column("last4", sa.String(4), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("given_note", sa.String(200), nullable=True),
        sa.Column("redeemed_by_id", sa.String(64), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["activation_code_batches.id"],
                                name=op.f("fk_activation_codes_batch_id_activation_code_batches"),
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["redeemed_by_id"], ["users.id"], name=op.f("fk_activation_codes_redeemed_by_id_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activation_codes")),
        sa.UniqueConstraint("code_hmac", name="uq_activation_codes_code_hmac"),
        sa.UniqueConstraint("batch_id", "position", name="uq_activation_codes_batch_id_position"),
    )
    op.create_index("ix_activation_codes_redeemed_by_id", "activation_codes", ["redeemed_by_id"])

    op.create_table(
        "access_passes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False, server_default="all"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("code_id", sa.Uuid(), nullable=True),
        sa.Column("granted_by_id", sa.String(64), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope IN ('all')", name=op.f("ck_access_passes_scope_valid")),
        sa.CheckConstraint("source IN ('code','admin','payment')", name=op.f("ck_access_passes_source_valid")),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_access_passes_period_valid")),
        sa.CheckConstraint("source <> 'code' OR code_id IS NOT NULL",
                           name=op.f("ck_access_passes_code_source_has_code")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_access_passes_user_id_users"),
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["code_id"], ["activation_codes.id"],
                                name=op.f("fk_access_passes_code_id_activation_codes"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], name=op.f("fk_access_passes_granted_by_id_users"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["users.id"], name=op.f("fk_access_passes_revoked_by_id_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_passes")),
    )
    op.create_index("ix_access_passes_user_id_ends_at", "access_passes", ["user_id", "ends_at"])
    op.create_index("ix_access_passes_code_id", "access_passes", ["code_id"])

    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), NEW_TARGETS)

    _practice_free_for_existing_platform_courses()


def downgrade() -> None:
    op.execute("DELETE FROM admin_audit_log WHERE target_type IN ('access_batch','access_code','access_pass')")
    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), OLD_TARGETS)
    op.drop_index("ix_access_passes_code_id", table_name="access_passes")
    op.drop_index("ix_access_passes_user_id_ends_at", table_name="access_passes")
    op.drop_table("access_passes")
    op.drop_index("ix_activation_codes_redeemed_by_id", table_name="activation_codes")
    op.drop_table("activation_codes")
    op.drop_index("ix_activation_code_batches_created_at", table_name="activation_code_batches")
    op.drop_table("activation_code_batches")
    with op.batch_alter_table("assessments") as b:
        b.drop_constraint(op.f("ck_assessments_access_tier_valid"), type_="check")
        b.drop_column("access_tier")
