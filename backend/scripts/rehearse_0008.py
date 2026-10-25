#!/usr/bin/env python3
"""Verification SQL of the migration 0008 rehearsal (PHASE_6_DESIGN section 4).

Run it against a LOCAL PostgreSQL copy of production after `alembic upgrade head` and one lifespan start:

    venv/bin/python scripts/rehearse_0008.py postgresql+psycopg2://postgres@localhost:55432/rehearsal

Read-only (one transaction, rolled back). Refuses any host other than localhost / 127.0.0.1 / ::1.
Exit code 0 when every check passes, 1 otherwise."""
from __future__ import annotations

import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ORG_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/organizations")  # app/lms/organizations/ids.py
ORT_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/ort")  # app/lms/ort/seed.py
PLATFORM = uuid.uuid5(ORG_NS, "org:platform")
ORT_COURSES = [str(uuid.uuid5(ORT_NS, f"ort-course:{lang}")) for lang in ("ky", "ru")]
DEMO = "usr_ort_demo_teacher"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

CHECKS = [
    ("courses without organization", "SELECT count(*) FROM courses WHERE organization_id IS NULL", 0),
    ("banks without organization", "SELECT count(*) FROM question_banks WHERE organization_id IS NULL", 0),
    ("ORT courses present", "SELECT count(*) FROM courses WHERE id::text IN :ort", None),
    ("ORT courses in platform with template ort v1, locked",
     "SELECT count(*) FROM courses WHERE id::text IN :ort AND organization_id = :platform "
     "AND template_key = 'ort' AND template_version = 1 AND template_locked", None),
    ("template grants", "SELECT count(*) FROM organization_template_grants", 1),
    ("active platform ort grant",
     "SELECT count(*) FROM organization_template_grants WHERE organization_id = :platform "
     "AND template_key = 'ort' AND revoked_at IS NULL", 1),
    ("platform organization", "SELECT count(*) FROM organizations WHERE id = :platform", 1),
    ("banks of ORT courses outside platform",
     "SELECT count(*) FROM question_banks WHERE course_id::text IN :ort AND organization_id <> :platform", 0),
    ("courses whose bank is in another organization",
     "SELECT count(*) FROM question_banks b JOIN courses c ON c.id = b.course_id "
     "WHERE b.organization_id <> c.organization_id", 0),
    ("approved independents without a personal org admin membership",
     "SELECT count(*) FROM users u WHERE u.teacher_status = 'approved' AND NOT u.is_platform_admin "
     "AND u.id <> :demo AND NOT EXISTS (SELECT 1 FROM organization_members m WHERE m.user_id = u.id "
     "AND m.role = 'org_admin' AND m.organization_id <> :platform)", 0),
    ("platform admins without the platform membership",
     "SELECT count(*) FROM users u WHERE u.is_platform_admin AND u.id <> :demo AND NOT EXISTS "
     "(SELECT 1 FROM organization_members m WHERE m.user_id = u.id AND m.organization_id = :platform)", 0),
    ("ORT courses still owned by the demo teacher while an active platform admin exists",
     "SELECT count(*) FROM courses WHERE id::text IN :ort AND owner_id = :demo AND EXISTS "
     "(SELECT 1 FROM users WHERE is_platform_admin AND disabled_at IS NULL AND id <> :demo)", 0),
]
INFO = [
    ("personal organizations", "SELECT count(*) FROM organizations WHERE id <> :platform"),
    ("approved teachers (not admins, not demo)",
     "SELECT count(*) FROM users WHERE teacher_status = 'approved' AND NOT is_platform_admin AND id <> :demo"),
    ("memberships", "SELECT count(*) FROM organization_members"),
    ("ort_* preset assessments outside ORT courses",
     "SELECT count(*) FROM assessments a JOIN courses c ON c.id = a.course_id "
     "WHERE a.preset IN ('ort_main','ort_subject') AND c.template_key IS NULL"),
    ("courses per organization",
     "SELECT string_agg(o.slug || '=' || n::text, ', ' ORDER BY o.slug) FROM "
     "(SELECT organization_id, count(*) AS n FROM courses GROUP BY organization_id) x "
     "JOIN organizations o ON o.id = x.organization_id"),
]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    url = make_url(argv[1])
    if url.get_backend_name() != "postgresql" or (url.host or "localhost") not in LOCAL_HOSTS:
        print("Refusing: only a local PostgreSQL database may be rehearsed.")
        return 2
    from sqlalchemy import bindparam

    params = {"ort": ORT_COURSES, "platform": str(PLATFORM), "demo": DEMO}
    engine = create_engine(url)
    ok = True
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            present = None
            for name, sql, expected in CHECKS:
                stmt = text(sql)
                if ":ort" in sql:
                    stmt = stmt.bindparams(bindparam("ort", expanding=True))
                value = conn.execute(stmt, {k: v for k, v in params.items() if f":{k}" in sql}).scalar()
                if name == "ORT courses present":
                    present = value
                    print(f"  info  {name}: {value}")
                    continue
                if expected is None:
                    expected = present
                passed = value == expected
                ok &= passed
                print(f"  {'ok  ' if passed else 'FAIL'}  {name}: {value} (expected {expected})")
            for name, sql in INFO:
                print(f"  info  {name}: {conn.execute(text(sql), {k: v for k, v in params.items() if f':{k}' in sql}).scalar()}")
        finally:
            trans.rollback()
    engine.dispose()
    print("0008 rehearsal checks:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
