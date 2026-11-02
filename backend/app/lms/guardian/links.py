"""Whether a user is a parent right now (auth profile and `/me/lms`). Its own module: the auth endpoints import it, and
`guardian.service` pulls in most of the LMS."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import object_session

from app.lms.guardian.models import GuardianLink
from app.models.user import User


def has_active_link(user: User) -> bool:
    """From the database on every call, like every other permission."""
    db = object_session(user)
    return db is not None and db.execute(select(GuardianLink.id).where(
        GuardianLink.guardian_user_id == user.id, GuardianLink.revoked_at.is_(None)).limit(1)).first() is not None
