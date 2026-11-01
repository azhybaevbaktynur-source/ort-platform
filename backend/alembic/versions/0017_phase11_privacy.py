"""phase 11: privacy (consent state, policy versions, consent records, parents, data requests, asset erasure)

Revision ID: 0017_phase11_privacy
Revises: 0016_phase10_practice_analytics
Create Date: 2026-11-02

Additive. Every existing account reads `consent_state='legacy'` (nothing restricted); test students read `exempt`.
See docs/phases/PHASE_11_DESIGN.md section 2.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_phase11_privacy"
down_revision: Union[str, None] = "0016_phase10_practice_analytics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = sa.DateTime(timezone=True)
_USER = sa.String(64)
# lms_grading_immutable() comes from 0005: it honours lms.allow_grade_purge. Its argument names a column allowed to go
# NULL through an FK SET NULL; these columns are NOT NULL, so that branch can never commit.
_GUARDS = {
    "consent_records": ("trg_consent_records_append_only", "user_id"),
    "policy_versions": ("trg_policy_versions_immutable", "kind"),
}


def _fk(name: str, ondelete: str = "RESTRICT", nullable: bool = False) -> sa.Column:
    return sa.Column(name, _USER, sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("consent_state", sa.String(20), server_default="legacy", nullable=False))
        b.add_column(sa.Column("consent_due_at", _TS, nullable=True))
        b.add_column(sa.Column("deleted_at", _TS, nullable=True))
        b.add_column(sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
        b.create_check_constraint("ck_users_consent_state_valid",
                                  "consent_state IN ('legacy','ok','pending_guardian','exempt')")
    users = sa.table("users", sa.column("consent_state", sa.String), sa.column("is_test_student", sa.Boolean))
    op.execute(users.update().where(users.c.is_test_student.is_(sa.true())).values(consent_state="exempt"))

    op.add_column("assets", sa.Column("erased_at", _TS, nullable=True))

    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("body_en", sa.Text(), nullable=False),
        sa.Column("body_ky", sa.Text(), nullable=False),
        sa.Column("body_ru", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("requires_reconsent", sa.Boolean(), nullable=False),
        sa.Column("effective_at", _TS, nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.CheckConstraint("kind IN ('privacy','terms','guardian_consent')", name="ck_policy_versions_kind_valid"),
        sa.CheckConstraint("status IN ('draft_legal_review','approved')", name="ck_policy_versions_status_valid"),
        sa.UniqueConstraint("kind", "version", name="uq_policy_versions_kind_version"),
    )
    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("user_id"),
        _fk("granted_by_id"),
        sa.Column("policy_version_id", sa.Uuid(), sa.ForeignKey("policy_versions.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("action", sa.String(12), nullable=False),
        sa.Column("locale", sa.String(2), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.CheckConstraint("action IN ('granted','withdrawn')", name="ck_consent_records_action_valid"),
        sa.CheckConstraint("source IN ('signup','prompt','guardian','admin')", name="ck_consent_records_source_valid"),
    )
    op.create_index("ix_consent_records_user_kind", "consent_records", ["user_id", "kind", "created_at"])
    op.create_table(
        "guardian_pairing_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("student_user_id"),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("consumed_at", _TS, nullable=True),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.UniqueConstraint("code_hash", name="uq_guardian_pairing_codes_code_hash"),
    )
    _open = "consumed_at IS NULL AND revoked_at IS NULL"
    op.create_index("uq_pairing_open", "guardian_pairing_codes", ["student_user_id"], unique=True,
                    postgresql_where=sa.text(_open), sqlite_where=sa.text(_open))
    op.create_table(
        "guardian_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("guardian_user_id"),
        _fk("student_user_id"),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("revoked_at", _TS, nullable=True),
        _fk("revoked_by_id", "SET NULL", True),
        sa.CheckConstraint("guardian_user_id <> student_user_id", name="ck_guardian_links_guardian_not_student"),
    )
    op.create_index("uq_guardian_active", "guardian_links", ["guardian_user_id", "student_user_id"], unique=True,
                    postgresql_where=sa.text("revoked_at IS NULL"), sqlite_where=sa.text("revoked_at IS NULL"))
    op.create_index("ix_guardian_links_guardian_user_id", "guardian_links", ["guardian_user_id"])
    op.create_index("ix_guardian_links_student_user_id", "guardian_links", ["student_user_id"])
    op.create_table(
        "data_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("user_id"),
        _fk("requested_by_id"),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("requested_at", _TS, nullable=False),
        sa.Column("due_at", _TS, nullable=False),
        sa.Column("completed_at", _TS, nullable=True),
        _fk("handled_by_id", "SET NULL", True),
        sa.Column("reject_code", sa.String(40), nullable=True),
        sa.CheckConstraint("kind IN ('export','delete')", name="ck_data_requests_kind_valid"),
        sa.CheckConstraint("status IN ('pending','completed','rejected','cancelled')",
                           name="ck_data_requests_status_valid"),
    )
    op.create_index("uq_data_request_open", "data_requests", ["user_id", "kind"], unique=True,
                    postgresql_where=sa.text("status = 'pending'"), sqlite_where=sa.text("status = 'pending'"))
    op.create_index("ix_data_requests_status_due_at", "data_requests", ["status", "due_at"])
    op.create_index("ix_data_requests_user_id", "data_requests", ["user_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table, (name, col) in _GUARDS.items():
            op.execute(f"CREATE TRIGGER {name} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
                       f"EXECUTE FUNCTION lms_grading_immutable('{col}')")


def downgrade() -> None:
    for table in ("data_requests", "guardian_links", "guardian_pairing_codes", "consent_records", "policy_versions"):
        op.drop_table(table)
    op.drop_column("assets", "erased_at")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("ck_users_consent_state_valid", type_="check")
        for col in ("token_version", "deleted_at", "consent_due_at", "consent_state"):
            b.drop_column(col)
