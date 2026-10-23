"""phase 1: courses, enrollments, teacher requests, audit log, rate limits

Revision ID: 0002_phase1_courses
Revises: 0001_baseline
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase1_courses"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    # 1. users
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("is_platform_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
        b.add_column(sa.Column("teacher_status", sa.String(length=16), server_default="none", nullable=False))
        b.add_column(sa.Column("locale", sa.String(length=2), nullable=True))
        b.add_column(sa.Column("age_band", sa.String(length=16), nullable=True))
        b.add_column(sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("disabled_by_id", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("disabled_reason", sa.String(length=500), nullable=True))
        b.create_foreign_key(
            op.f("fk_users_disabled_by_id_users"), "users", ["disabled_by_id"], ["id"], ondelete="SET NULL"
        )
        b.create_check_constraint(
            op.f("ck_users_teacher_status_valid"), "teacher_status IN ('none','pending','approved','revoked')"
        )
        b.create_check_constraint(op.f("ck_users_locale_valid"), "locale IS NULL OR locale IN ('en','ru','ky')")
        b.create_check_constraint(
            op.f("ck_users_age_band_valid"), "age_band IS NULL OR age_band IN ('under_14','14_17','18_plus')"
        )
        b.create_index("ix_users_teacher_status", ["teacher_status"])

    # 2. new tables
    op.create_table(
        "courses",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("description", JSONType, nullable=True),
        sa.Column("languages", JSONType, nullable=False),
        sa.Column("default_language", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("enrollment_mode", sa.String(length=16), nullable=False),
        sa.Column("join_code", sa.String(length=16), nullable=False),
        sa.Column("join_code_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrollment_limit", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", JSONType, nullable=False),
        sa.Column("copied_from_id", UUID, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlisted_by_admin_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint("default_language IN ('en','ru','ky')", name=op.f("ck_courses_default_language_valid")),
        sa.CheckConstraint("status IN ('draft','published','concluded')", name=op.f("ck_courses_status_valid")),
        sa.CheckConstraint("visibility IN ('private','catalog')", name=op.f("ck_courses_visibility_valid")),
        sa.CheckConstraint(
            "enrollment_mode IN ('closed','open','invite_code','form_auto','form_review')",
            name=op.f("ck_courses_enrollment_mode_valid"),
        ),
        sa.CheckConstraint(
            "enrollment_limit IS NULL OR (enrollment_limit >= 1 AND enrollment_limit <= 10000)",
            name=op.f("ck_courses_enrollment_limit_valid"),
        ),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at", name=op.f("ck_courses_dates_valid")
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_courses_owner_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["copied_from_id"], ["courses.id"], name=op.f("fk_courses_copied_from_id_courses"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by_id"], ["users.id"], name=op.f("fk_courses_deleted_by_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("join_code", name="uq_courses_join_code"),
    )
    op.create_index("ix_courses_owner_id", "courses", ["owner_id"])
    op.create_index("ix_courses_status_created_at", "courses", ["status", "created_at"])
    op.create_index("ix_courses_deleted_at", "courses", ["deleted_at"])

    op.create_table(
        "enrollments",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("content_language", sa.String(length=2), nullable=True),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint("role IN ('teacher','assistant','student')", name=op.f("ck_enrollments_role_valid")),
        sa.CheckConstraint(
            "state IN ('requested','invited','active','declined','removed')", name=op.f("ck_enrollments_state_valid")
        ),
        sa.CheckConstraint(
            "source IN ('owner','join_code','staff_add','admin','invite','form','open')",
            name=op.f("ck_enrollments_source_valid"),
        ),
        sa.CheckConstraint(
            "content_language IS NULL OR content_language IN ('en','ru','ky')",
            name=op.f("ck_enrollments_content_language_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_enrollments_course_id_courses"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_enrollments_user_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["removed_by_id"], ["users.id"], name=op.f("fk_enrollments_removed_by_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
        sa.UniqueConstraint("course_id", "user_id", name="uq_enrollments_course_id_user_id"),
    )
    op.create_index("ix_enrollments_user_id_state", "enrollments", ["user_id", "state"])
    op.create_index("ix_enrollments_course_id_role_state", "enrollments", ["course_id", "role", "state"])

    op.create_table(
        "enrollment_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("from_role", sa.String(length=16), nullable=True),
        sa.Column("to_role", sa.String(length=16), nullable=True),
        sa.Column("from_state", sa.String(length=16), nullable=True),
        sa.Column("to_state", sa.String(length=16), nullable=True),
        sa.Column("details", JSONType, nullable=True),
        _ts("created_at"),
        sa.CheckConstraint(
            "event IN ('created','joined','rejoined','staff_added','left','removed','role_changed',"
            "'owner_transferred_in','owner_transferred_out','admin_restored')",
            name=op.f("ck_enrollment_events_event_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"], ["enrollments.id"], name=op.f("fk_enrollment_events_enrollment_id_enrollments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_enrollment_events_course_id_courses"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_enrollment_events_actor_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_events")),
    )
    op.create_index("ix_enrollment_events_course_id_created_at", "enrollment_events", ["course_id", "created_at"])
    op.create_index(
        "ix_enrollment_events_enrollment_id_created_at", "enrollment_events", ["enrollment_id", "created_at"]
    )

    op.create_table(
        "teacher_requests",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decided_by_id", sa.String(length=64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')", name=op.f("ck_teacher_requests_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_teacher_requests_user_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], name=op.f("fk_teacher_requests_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teacher_requests")),
    )
    op.create_index("ix_teacher_requests_status_created_at", "teacher_requests", ["status", "created_at"])
    op.create_index("ix_teacher_requests_user_id", "teacher_requests", ["user_id"])
    op.create_index(
        "uq_teacher_requests_user_pending", "teacher_requests", ["user_id"], unique=True,
        postgresql_where=sa.text("status = 'pending'"), sqlite_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "admin_audit_log",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("details", JSONType, nullable=True),
        sa.Column("ip_hash", sa.String(length=32), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "target_type IN ('user','course','teacher_request','enrollment')",
            name=op.f("ck_admin_audit_log_target_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_admin_audit_log_actor_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_log")),
    )
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at", "id"])
    op.create_index("ix_admin_audit_log_target", "admin_audit_log", ["target_type", "target_id", "created_at"])
    op.create_index("ix_admin_audit_log_actor_id_created_at", "admin_audit_log", ["actor_id", "created_at"])

    op.create_table(
        "rate_limit_buckets",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start", name=op.f("pk_rate_limit_buckets")),
    )
    op.create_index("ix_rate_limit_buckets_expires_at", "rate_limit_buckets", ["expires_at"])

    # 3. data: existing old-app admins become platform admins and approved teachers
    users = sa.table(
        "users", sa.column("role", sa.String), sa.column("is_platform_admin", sa.Boolean),
        sa.column("teacher_status", sa.String),
    )
    op.execute(
        users.update().where(users.c.role == "admin").values(is_platform_admin=sa.true(), teacher_status="approved")
    )


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
    op.drop_table("admin_audit_log")
    op.drop_table("teacher_requests")
    op.drop_table("enrollment_events")
    op.drop_table("enrollments")
    op.drop_table("courses")
    with op.batch_alter_table("users") as b:
        b.drop_index("ix_users_teacher_status")
        b.drop_constraint(op.f("ck_users_age_band_valid"), type_="check")
        b.drop_constraint(op.f("ck_users_locale_valid"), type_="check")
        b.drop_constraint(op.f("ck_users_teacher_status_valid"), type_="check")
        b.drop_constraint(op.f("fk_users_disabled_by_id_users"), type_="foreignkey")
        for col in ("disabled_reason", "disabled_by_id", "disabled_at", "age_band", "locale",
                    "teacher_status", "is_platform_admin"):
            b.drop_column(col)
