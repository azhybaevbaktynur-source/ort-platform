"""Edit rights on a bank (PHASE_7C_DESIGN 6.3, P7C-10).

Phase 7c: every live bank of the course is editable by whoever holds `course:content.manage` (course staff). This is
the single place Phase 9 extends for organization-shared banks (owner or org admin only)."""
from __future__ import annotations

from app.core.authz import A, AuthzContext, can


def can_edit_bank(ctx: AuthzContext, course, bank) -> bool:
    if bank is None or bank.deleted_at is not None or bank.course_id != course.id:
        return False
    return can(ctx, A.CONTENT_MANAGE, course)
