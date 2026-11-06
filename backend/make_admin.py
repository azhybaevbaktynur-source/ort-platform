#!/usr/bin/env python3
"""
Standalone script for platform admins (needs database access; run it on the server or against its database).

Usage:
    python make_admin.py [email]               # make a registered user a platform admin (not a teacher)
    python make_admin.py [email] --revoke      # remove the platform-admin flag (never from the last active admin)
    python make_admin.py --reset-2fa [email]   # turn two-step login off after a lost phone; every session ends

A new admin sets up two-step login on their first visit to the admin area. The admin user page can also make and remove
platform admins, confirmed with the acting admin's authenticator code.
"""

import sys
import os

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.user import User


def _find(session, email: str):
    clean_email = email.strip().lower()
    if not clean_email:
        print("Error: Email cannot be empty.")
        return None, clean_email
    user = session.query(User).filter(User.email == clean_email).first()
    if not user:
        print("User not found.")
    return user, clean_email


def promote_user(email: str, revoke: bool = False) -> bool:
    """Grant (or with revoke=True remove) platform admin. Granting does not make the person a teacher; removing refuses
    the last active platform admin."""
    from app.lms.core.errors import Conflict
    from app.lms.platform_admin import admins

    session = SessionLocal()
    try:
        user, clean_email = _find(session, email)
        if not user:
            return False

        if revoke:
            if not user.is_platform_admin:
                print(f"'{clean_email}' is not a platform admin.")
                return True
            try:
                admins.revoke(session, user)
            except Conflict:
                session.rollback()
                print("Refused: this is the last active platform admin. Make another admin first.")
                return False
            session.commit()
            print(f"Revoked admin rights from '{clean_email}' (ID: {user.id}).")
            return True

        if user.is_platform_admin:
            admins.ensure_platform_membership(session, user.id)  # Phase 6 S1 (idempotent)
            session.commit()
            print(f"User '{clean_email}' is already an admin.")
            return True

        admins.grant(session, user)
        session.commit()
        print(f"Success! '{clean_email}' (ID: {user.id}) is now an admin. "
              "They set up two-step login on their first visit to the admin area.")
        return True
    except Exception as e:
        session.rollback()
        print(f"Database error: {type(e).__name__}")
        return False
    finally:
        session.close()


def reset_2fa(email: str) -> bool:
    """Two-step login off for a lost device: secret and recovery codes deleted, every session ended. Prints nothing
    secret."""
    from app.lms.mfa import service as mfa

    session = SessionLocal()
    try:
        user, clean_email = _find(session, email)
        if not user:
            return False
        mfa.reset(session, user)
        session.commit()
        mfa.notify(user, "mfa_reset")  # the account learns of it by email
        print(f"Two-step login was reset for '{clean_email}'. Every session of the account ended; "
              "they set it up again on their next visit to the admin area.")
        return True
    except Exception as e:
        session.rollback()
        print(f"Database error: {type(e).__name__}")
        return False
    finally:
        session.close()


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    revoke = "--revoke" in args
    reset = "--reset-2fa" in args
    args = [a for a in args if a not in ("--revoke", "--reset-2fa")]
    if revoke and reset:
        print("Use either --revoke or --reset-2fa.")
        sys.exit(2)
    if args:
        target_email = args[0].strip()
    else:
        try:
            target_email = input("Enter email address of the user: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled.")
            sys.exit(1)

    success = reset_2fa(target_email) if reset else promote_user(target_email, revoke=revoke)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
