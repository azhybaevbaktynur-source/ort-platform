"""Edit rights on a bank (PHASE_7C_DESIGN 6.3, P7C-10; PHASE_9_DESIGN 4.2, P9-2).

Phase 7c: every live bank of the course is editable by whoever holds `course:content.manage` (course staff).
Phase 9 extends this single place for organization-shared banks: an org admin of the bank's organization (or of an
ancestor of it: departments, `organizations.tree`) may edit a bank its home course has shared with the organization,
without a teacher enrollment (owner decision A13 is otherwise kept: org admins stay read-only inside courses)."""
from __future__ import annotations

from app.core.authz import A, AuthzContext, can


def can_edit_bank(ctx: AuthzContext, course, bank) -> bool:
    """`bank.course_id == course.id` and (`course:content.manage` on the home course, or the bank is shared with
    the organization (`visibility = 'organization'`) and the caller administers its organization through the tree).

    The org-admin branch keeps every gate `content.manage` has for staff: no deleted, concluded or sandbox course,
    no write while the organization (its root) is suspended, nothing in Student view (`org_admin_for` is false for
    that course's organization). Quiz banks and ORT template banks never reach it: they are never shared (CHECK
    `quiz_bank_private`, invariant 1; design 9), and it refuses them explicitly as well. Platform admins get no edit
    right from their flag (only from an org-admin membership, like anyone else)."""
    if bank is None or bank.deleted_at is not None or bank.course_id != course.id:
        return False
    if can(ctx, A.CONTENT_MANAGE, course):
        return True
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 4.2: org admins on organization-shared banks)
    if getattr(bank, "visibility", "private") != "organization" or bank.assessment_id is not None:
        return False
    if (course.deleted_at is not None or course.status == "concluded"
            or getattr(course, "sandbox_for_template_id", None) is not None
            or getattr(course, "template_key", None) == "ort"):
        return False
    if ctx.org_suspended(course.organization_id, course.id):
        return False
    return ctx.org_admin_for(bank.organization_id)
    # --- Phase 9 S1 end ---
