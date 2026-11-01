"""`policy_versions` (immutable), `consent_records` (append-only), `data_requests` (PHASE_11_DESIGN 2).

Both guards have an ORM listener and a PostgreSQL trigger, the same function as `grade_events`: only the maintenance
setting `lms.allow_grade_purge`, which no API path sets, gets past it."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, event, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow
from app.lms.grading.models import GUARD_FN_SQL


class PolicyVersion(UUIDPKMixin, Base):
    __tablename__ = "policy_versions"

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    body_en: Mapped[str] = mapped_column(Text, nullable=False)
    body_ky: Mapped[str] = mapped_column(Text, nullable=False)
    body_ru: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requires_reconsent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('privacy','terms','guardian_consent')", name="kind_valid"),
        CheckConstraint("status IN ('draft_legal_review','approved')", name="status_valid"),
        UniqueConstraint("kind", "version", name="uq_policy_versions_kind_version"),
    )


class ConsentRecord(UUIDPKMixin, Base):
    __tablename__ = "consent_records"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    granted_by_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False, default="granted")
    locale: Mapped[str] = mapped_column(String(2), nullable=False)
    source: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("action IN ('granted','withdrawn')", name="action_valid"),
        CheckConstraint("source IN ('signup','prompt','guardian','admin')", name="source_valid"),
        Index("ix_consent_records_user_kind", "user_id", "kind", "created_at"),
    )


class DataRequest(UUIDPKMixin, Base):
    __tablename__ = "data_requests"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    requested_by_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"),
                                                         nullable=True)
    reject_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        CheckConstraint("kind IN ('export','delete')", name="kind_valid"),
        CheckConstraint("status IN ('pending','completed','rejected','cancelled')", name="status_valid"),
        Index("uq_data_request_open", "user_id", "kind", unique=True,
              postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'")),
        Index("ix_data_requests_status_due_at", "status", "due_at"),
        Index("ix_data_requests_user_id", "user_id"),
    )


class ImmutablePrivacyRowError(RuntimeError):
    """Raised when code tries to UPDATE or DELETE a consent record or a policy version."""


def _forbid(_mapper, _connection, target):
    raise ImmutablePrivacyRowError(f"{type(target).__name__} rows are immutable")


for _model in (PolicyVersion, ConsentRecord):
    event.listen(_model, "before_update", _forbid)
    event.listen(_model, "before_delete", _forbid)

_GUARDS = {
    "consent_records": ("trg_consent_records_append_only", "user_id"),
    "policy_versions": ("trg_policy_versions_immutable", "kind"),
}


def _create_guard(target, connection, **_kw) -> None:
    """create_all databases (tests); migration 0017 is the production twin."""
    if connection.dialect.name != "postgresql":
        return
    name, col = _GUARDS[target.name]
    connection.execute(text(GUARD_FN_SQL))
    connection.execute(text(f"CREATE TRIGGER {name} BEFORE UPDATE OR DELETE ON {target.name} FOR EACH ROW "
                            f"EXECUTE FUNCTION lms_grading_immutable('{col}')"))


event.listen(PolicyVersion.__table__, "after_create", _create_guard)
event.listen(ConsentRecord.__table__, "after_create", _create_guard)
