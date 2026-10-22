#!/usr/bin/env python3
"""
Standalone script to promote any registered user to 'admin' role.

Usage:
    python make_admin.py [email]            # grant (role=admin and is_platform_admin=true)
    python make_admin.py [email] --revoke   # revoke both
"""

import sys
import os

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.user import User


def promote_user(email: str, revoke: bool = False) -> bool:
    """Grant (or with revoke=True remove) platform admin: sets role and is_platform_admin together."""
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
            user.role = "student"
            user.is_platform_admin = False
            session.commit()
            print(f"Revoked admin rights from '{clean_email}' (ID: {user.id}).")
            return True

        if user.role == "admin" and user.is_platform_admin:
            print(f"User '{clean_email}' is already an admin.")
            return True

        user.role = "admin"
        user.is_platform_admin = True
        session.commit()
        print(f"Success! '{clean_email}' (ID: {user.id}) is now an admin.")
        return True
    except Exception as e:
        session.rollback()
        print(f"Database error: {e}")
        return False
    finally:
        session.close()


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
