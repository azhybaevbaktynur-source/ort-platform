"""S3 access test helpers: a pass for a person, straight in the database (the redeem and grant routes have their own
tests)."""
import uuid
from datetime import timedelta

from app.lms.access.models import AccessPass
from app.lms.core import clock


def give_pass(db, user, *, days: int = 30, ends_in: timedelta = None, starts_ago: timedelta = timedelta(days=1),
              revoked: bool = False) -> AccessPass:
    now = clock.now()
    p = AccessPass(id=uuid.uuid4(), user_id=user.id, scope="all", starts_at=now - starts_ago,
                   ends_at=now + (ends_in if ends_in is not None else timedelta(days=days)), source="admin",
                   reason="test", revoked_at=now if revoked else None, created_at=now)
    db.add(p)
    db.commit()
    return p
