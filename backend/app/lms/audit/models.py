from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow
from app.lms.core.types import JSONType


class AdminAuditLog(UUIDPKMixin, Base):
    __tablename__ = "admin_audit_log"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('user','course','teacher_request','enrollment')", name="target_type_valid"
        ),
        Index("ix_admin_audit_log_created_at", "created_at", "id"),
        Index("ix_admin_audit_log_target", "target_type", "target_id", "created_at"),
        Index("ix_admin_audit_log_actor_id_created_at", "actor_id", "created_at"),
    )
