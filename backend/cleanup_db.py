#!/usr/bin/env python3
"""
Database cleanup script for ORT Platform.
Purges test/dummy students, duplicate test exams, broken test attempts,
and orphaned references while strictly preserving essential admin accounts,
canonical exam sets, and core subject question banks.
"""

import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.db.session import SessionLocal, engine
from app.models.user import User
from app.models.exam_set import ExamSet
from app.models.question import Question
from app.models.test_attempt import TestAttempt
from app.models.exam_access import ExamAccess
from app.db.init_db import init_db

# Essential canonical users to preserve
PRESERVED_USER_EMAILS = {
    "admin@ort.kg",
    "azhybaev.baktynur@gmail.com",
    "student@ort.kg",
}

# Essential canonical exam sets to preserve
PRESERVED_EXAM_SET_IDS = {
    "exam_practice_bank_ky",
    "exam_practice_bank_ru",
    "ort_main_standard",
    "ort_main_standard_ru",
    "ort_subject_chemistry_ky",
    "ort_subject_chemistry_ru",
    "ort_subject_biology_ky",
    "ort_subject_biology_ru",
    "ort_subject_physics_ky",
    "ort_subject_physics_ru",
    "ort_subject_history_ky",
    "ort_subject_history_ru",
    "ort_subject_english_ky",
    "ort_subject_english_ru",
    "ort_subject_advanced_math_ky",
    "ort_subject_advanced_math_ru",
    "ort_subject_native_language_ky",
    "ort_subject_native_language_ru",
}


def cleanup_database():
    session = SessionLocal()
    try:
        print("=" * 60)
        print("STARTING ORT PLATFORM LOCAL DATABASE CLEANUP")
        print("=" * 60)

        # 1. Identify dummy/test users to purge
        all_users = session.query(User).all()
        users_to_delete = []
        users_to_keep = []

        for u in all_users:
            email_lower = (u.email or "").lower()
            if email_lower in PRESERVED_USER_EMAILS:
                users_to_keep.append(u)
            elif (
                email_lower.startswith("newstudent_")
                or email_lower.startswith("phone_user_")
                or email_lower.startswith("reset_test_")
                or "@example.com" in email_lower
                or u.role == "student"
            ):
                users_to_delete.append(u)
            else:
                users_to_keep.append(u)

        deleted_user_ids = {u.id for u in users_to_delete}
        print(f"Users: {len(users_to_keep)} preserved, {len(users_to_delete)} to purge.")

        # 2. Identify random test exams to purge
        all_exams = session.query(ExamSet).all()
        exams_to_delete = []
        exams_to_keep = []

        for e in all_exams:
            if e.id in PRESERVED_EXAM_SET_IDS:
                exams_to_keep.append(e)
            else:
                # Any random/temporary exam generated during tests
                exams_to_delete.append(e)

        deleted_exam_ids = {e.id for e in exams_to_delete}
        print(f"ExamSets: {len(exams_to_keep)} preserved, {len(exams_to_delete)} to purge.")

        # 3. Clean up ExamAccess (cascade foreign keys)
        access_to_delete = session.query(ExamAccess).filter(
            (ExamAccess.user_id.in_(deleted_user_ids)) |
            (ExamAccess.exam_set_id.in_(deleted_exam_ids))
        ).all()
        deleted_access_count = len(access_to_delete)
        for a in access_to_delete:
            session.delete(a)
        print(f"ExamAccess: {deleted_access_count} records purged.")

        # 4. Clean up TestAttempts (broken or belonging to deleted users/exams)
        attempts_to_delete = session.query(TestAttempt).filter(
            (TestAttempt.user_id.in_(deleted_user_ids)) |
            (TestAttempt.template_id.in_(deleted_exam_ids))
        ).all()
        deleted_attempts_count = len(attempts_to_delete)
        for att in attempts_to_delete:
            session.delete(att)
        print(f"TestAttempts: {deleted_attempts_count} records purged.")

        # 5. Clean up Questions attached to deleted test exams
        questions_to_delete = session.query(Question).filter(
            Question.exam_set_id.in_(deleted_exam_ids)
        ).all()
        deleted_questions_count = len(questions_to_delete)
        for q in questions_to_delete:
            session.delete(q)
        print(f"Questions: {deleted_questions_count} ephemeral test questions purged.")

        # 6. Delete purged exams
        for e in exams_to_delete:
            session.delete(e)

        # 7. Delete purged users
        for u in users_to_delete:
            session.delete(u)

        session.commit()
        print("Database purge committed successfully.")

        # 8. Re-run init_db to ensure canonical accounts and sets are in pristine condition
        print("-" * 60)
        print("Verifying canonical data integrity with init_db()...")
        init_db()

        # 9. Print final state
        remaining_users = session.query(User).all()
        remaining_exams = session.query(ExamSet).all()
        remaining_questions = session.query(Question).count()
        remaining_attempts = session.query(TestAttempt).count()
        remaining_access = session.query(ExamAccess).count()

        print("-" * 60)
        print("FINAL DATABASE STATE:")
        print(f"  Users: {len(remaining_users)}")
        for u in remaining_users:
            print(f"    - [{u.role}] {u.email} ({u.display_name})")
        print(f"  ExamSets: {len(remaining_exams)}")
        for e in remaining_exams:
            print(f"    - [{e.exam_type}] {e.id} ({e.title})")
        print(f"  Questions Count: {remaining_questions}")
        print(f"  Test Attempts Count: {remaining_attempts}")
        print(f"  Exam Access Records Count: {remaining_access}")
        print("=" * 60)
        print("CLEANUP COMPLETED SUCCESSFULLY.")

    except Exception as exc:
        session.rollback()
        print(f"ERROR DURING CLEANUP: {exc}", file=sys.stderr)
        raise exc
    finally:
        session.close()


if __name__ == "__main__":
    cleanup_database()
