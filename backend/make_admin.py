#!/usr/bin/env python3
"""
Standalone script to make a registered user a platform admin (and an approved teacher).

Usage:
    python make_admin.py [email]            # grant (is_platform_admin=true, teacher_status=approved)
    python make_admin.py [email] --revoke   # revoke the platform-admin flag
"""

import sys
import os

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.user import User


def promote_user(email: str, revoke: bool = False) -> bool:
    """Grant (or with revoke=True remove) platform admin. Grant also approves the user as a teacher."""
    clean_email = email.strip().lower()
    if not clean_email:
        print("Error: Email cannot be empty.")
        return False

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == clean_email).first()
        if not user:
            print("User not found.")
            return False

        if revoke:
            user.is_platform_admin = False
            _remove_platform_membership(session, user.id)  # Phase 6 S1
            session.commit()
            print(f"Revoked admin rights from '{clean_email}' (ID: {user.id}).")
            return True

        if user.is_platform_admin and user.teacher_status == "approved":
            _ensure_platform_membership(session, user.id)  # Phase 6 S1 (idempotent)
            session.commit()
            print(f"User '{clean_email}' is already an admin.")
            return True

        user.is_platform_admin = True
        user.teacher_status = "approved"
        _ensure_platform_membership(session, user.id)  # Phase 6 S1
        session.commit()
        print(f"Success! '{clean_email}' (ID: {user.id}) is now an admin.")
        return True
    except Exception as e:
        session.rollback()
        print(f"Database error: {e}")
        return False
    finally:
        session.close()


# --- Phase 6 S1 begin --- (PHASE_6_DESIGN 4: platform admins administer the platform organization)
def _ensure_platform_membership(session, user_id: str) -> None:
    """Insert where missing; a removed membership row is revived."""
    from sqlalchemy import update

    from app.lms.organizations.defaults import ensure_membership, ensure_platform_org
    from app.lms.organizations.models import OrganizationMember

    conn = session.connection()
    org_id = ensure_platform_org(conn)
    if not ensure_membership(conn, org_id, user_id):
        conn.execute(update(OrganizationMember.__table__).where(
            OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user_id,
            OrganizationMember.state != "active").values(state="active", role="org_admin", removed_at=None,
                                                         removed_by_id=None))


def _remove_platform_membership(session, user_id: str) -> None:
    from sqlalchemy import update

    from app.lms.core.models import utcnow
    from app.lms.organizations.ids import platform_org_id
    from app.lms.organizations.models import OrganizationMember

    session.connection().execute(update(OrganizationMember.__table__).where(
        OrganizationMember.organization_id == platform_org_id(), OrganizationMember.user_id == user_id,
        OrganizationMember.state == "active").values(state="removed", removed_at=utcnow()))
# --- Phase 6 S1 end ---


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    revoke = "--revoke" in args
    args = [a for a in args if a != "--revoke"]
    if args:
        target_email = args[0].strip()
    else:
        try:
            target_email = input("Enter email address of the user: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled.")
            sys.exit(1)

    success = promote_user(target_email, revoke=revoke)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
