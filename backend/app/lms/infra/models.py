"""I5a (migration 0031_infra): one cached snapshot per provider. No personal data, no secrets: `payload` holds only the
allow-listed fields of INFRA_PANEL_DESIGN 2 (the provider modules return typed dataclasses, never raw responses)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import utcnow
from app.lms.core.types import JSONType

# Stored statuses. `empty`: never fetched; `refreshing`: a refresh holds the row (the guard, 60 s); `unavailable`: the
# provider has no usage API (SMTP / console email).
STATUSES = ("empty", "ok", "error", "not_connected", "unavailable", "refreshing")


class InfraSnapshot(Base):
    __tablename__ = "infra_snapshots"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict, server_default=text("'{}'"))
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
