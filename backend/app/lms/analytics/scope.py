"""Phase 10 S0: the one exclusion predicate for every staff aggregate over attempts (PHASE_10_DESIGN 0.3).

`final_attempt` matches the partial indexes on `attempts` (`ix_attempts_*_final`)."""
from __future__ import annotations

from sqlalchemy import and_, case, not_

from app.lms.enrollments.models import not_test_enrollment

COUNTED_STATUSES = ("graded", "needs_review")


def final_attempt(a):
    """Graded or needs-review, not a preview. `not_(col)` renders `NOT col` on PG and `col = 0` on SQLite."""
    return and_(a.c.status.in_(COUNTED_STATUSES), not_(a.c.is_preview))


def counted_attempt(a):
    """`final_attempt` and not a test student's enrollment (active or retired). Void and in-progress are out."""
    return and_(final_attempt(a), not_test_enrollment(a.c.enrollment_id))


def real_student(e):
    return and_(e.c.role == "student", e.c.state == "active", e.c.is_test_student.is_(False))


def percent_bucket(points, possible):
    """Bucket 0..9 of points/possible (100% goes in bucket 9). A CASE ladder: no FLOOR, no cast rounding, so SQLite
    and PostgreSQL agree. `possible <= 0` gives bucket 0."""
    whens = [(possible <= 0, 0)]
    whens += [(points * 10 < possible * k, k - 1) for k in range(1, 10)]
    return case(*whens, else_=9)
