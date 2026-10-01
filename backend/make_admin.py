#!/usr/bin/env python3
"""
Standalone script to promote any registered user to 'admin' role.

Usage:
    python make_admin.py [optional_email]
    or simply:
    python make_admin.py
"""

import sys
import os

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.user import User


def promote_user(email: str) -> bool:
    clean_email = email.strip().lower()
    if not clean_email:
        print("❌ Error: Email cannot be empty.")
        return False

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == clean_email).first()
        if not user:
            print(f"❌ User with email '{clean_email}' not found in database.")
            print("Registered users currently in database:")
            all_users = session.query(User).all()
            for u in all_users:
                print(f"  - {u.email} (Role: {u.role}, ID: {u.id})")
            return False

        if user.role == "admin":
            print(f"ℹ️ User '{clean_email}' is already an admin.")
            return True

        old_role = user.role
        user.role = "admin"
        session.commit()
        print(f"✅ Success! Promoted '{clean_email}' (ID: {user.id}) from '{old_role}' to 'admin' role.")
        return True
    except Exception as e:
        session.rollback()
        print(f"❌ Database error: {e}")
        return False
    finally:
        session.close()


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        target_email = sys.argv[1].strip()
    else:
        try:
            target_email = input("Enter email address of user to promote to admin: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled.")
            sys.exit(1)

    success = promote_user(target_email)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

