"""Step 3a S1 (STUDENT_IA_DESIGN 6.1): `courses.exam_family` / `courses.subject` through `PATCH /courses/{id}`: platform
admins on platform courses only (422 `exam_family_forbidden`), values from the registry (422 `exam_family_invalid` /
`subject_invalid`), a subject needs a family, the current values are a no-op for anyone, linking a lesson course to an
exam copies the exam's family; every course shape carries both (student, staff, admin); new ORT courses get `ort`."""
from __future__ import annotations

from app.lms.courses import exam_families
from app.lms.organizations.defaults import ort_course_fields
from tests.lms.factories import enroll, make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_course_link import world


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


async def patch(api, user, course, **body):
    return await api.call(user, "PATCH", f"/courses/{course.id}", json=body)


def test_registry():
    assert exam_families.FAMILIES == ("ort", "nct")
    assert "math" in exam_families.SUBJECTS and len(set(exam_families.SUBJECTS)) == len(exam_families.SUBJECTS)


async def test_admin_sets_and_clears_family_and_subject(db, api):
    w = world(db)
    r = await patch(api, w.admin, w.lc, exam_family="ort", subject="math")
    assert r.status_code == 200, r.text
    assert (r.json()["exam_family"], r.json()["subject"]) == ("ort", "math")
    db.refresh(w.lc)
    assert (w.lc.exam_family, w.lc.subject) == ("ort", "math")
    enroll(db, w.lc, w.s)
    student = (await api.call(w.s, "GET", f"/courses/{w.lc.id}")).json()
    assert (student["exam_family"], student["subject"]) == ("ort", "math")
    admin = (await api.call(w.admin, "GET", f"/platform/courses/{w.lc.id}")).json()
    assert (admin["exam_family"], admin["subject"]) == ("ort", "math")
    listed = (await api.call(w.admin, "GET", "/platform/courses", params={"limit": 50})).json()["items"]
    assert {x["id"]: x["subject"] for x in listed}[str(w.lc.id)] == "math"
    r = await patch(api, w.admin, w.lc, subject=None)  # back to the family's main course
    assert (r.json()["exam_family"], r.json()["subject"]) == ("ort", None)
    r = await patch(api, w.admin, w.lc, exam_family=None)
    assert r.status_code == 200 and r.json()["exam_family"] is None


async def test_values_are_validated(db, api):
    w = world(db)
    for body, err in (({"exam_family": "sat"}, "exam_family_invalid"),
                      ({"exam_family": "ort", "subject": "astrology"}, "subject_invalid"),
                      ({"subject": "math"}, "subject_invalid")):  # a subject needs a family
        r = await patch(api, w.admin, w.lc, **body)
        assert r.status_code == 422 and code(r) == err, (body, r.text)
    await patch(api, w.admin, w.lc, exam_family="nct", subject="physics")
    r = await patch(api, w.admin, w.lc, exam_family=None)  # the subject would be left without a family
    assert r.status_code == 422 and code(r) == "subject_invalid"
    r = await patch(api, w.admin, w.lc, exam_family="x" * 17)
    assert r.status_code == 422


async def test_only_platform_admins_on_platform_courses(db, api):
    w = world(db)
    own = make_course(db, w.teacher, title={"en": "Mine"}, status="published")
    r = await patch(api, w.teacher, own, exam_family="ort")
    assert r.status_code == 422 and code(r) == "exam_family_forbidden", r.text
    # the current values are a no-op for anyone (a settings form may send them back)
    r = await patch(api, w.teacher, own, exam_family=None, subject=None)
    assert r.status_code == 200, r.text
    # a platform admin who staffs a teacher's course still cannot group it under an exam
    enroll(db, own, w.admin, role="teacher", source="owner")
    r = await patch(api, w.admin, own, exam_family="ort")
    assert r.status_code == 422 and code(r) == "exam_family_forbidden", r.text
    db.refresh(own)
    assert own.exam_family is None


async def test_linking_an_exam_copies_its_family(db, api):
    w = world(db)
    w.exam.exam_family = "ort"
    db.commit()
    r = await api.call(w.admin, "PATCH", f"/courses/{w.lc.id}", json={"exam_course_id": str(w.exam.id)})
    assert r.status_code == 200, r.text
    assert (r.json()["exam_course_id"], r.json()["exam_family"]) == (str(w.exam.id), "ort")
    # a course that has a family keeps it; a family named in the same request wins
    other = make_course(db, w.admin, title={"ru": "Другой"}, languages=["ru"], default_language="ru",
                        status="published", organization_id=w.exam.organization_id, exam_family="nct")
    r = await api.call(w.admin, "PATCH", f"/courses/{other.id}", json={"exam_course_id": str(w.exam.id)})
    assert r.status_code == 200 and r.json()["exam_family"] == "nct", r.text
    third = make_course(db, w.admin, title={"ru": "Третий"}, languages=["ru"], default_language="ru",
                        status="published", organization_id=w.exam.organization_id)
    r = await api.call(w.admin, "PATCH", f"/courses/{third.id}",
                       json={"exam_course_id": str(w.exam.id), "exam_family": "nct"})
    assert r.status_code == 200 and r.json()["exam_family"] == "nct", r.text
    # unlinking keeps the family (grouping is its own setting)
    r = await api.call(w.admin, "PATCH", f"/courses/{w.lc.id}", json={"exam_course_id": None})
    assert r.json()["exam_course_id"] is None and r.json()["exam_family"] == "ort"


def test_new_ort_courses_get_the_family(db):
    assert ort_course_fields(db.connection(), "ru")["exam_family"] == "ort"


async def test_created_ort_template_course_gets_the_family(db, api):
    from tests.lms.org_support import add_member, grant, make_org

    t = make_user(db, teacher_status="approved")
    school = make_org(db)
    add_member(db, school, t, role="org_admin")
    grant(db, school)
    body = {"title": {"en": "ORT"}, "languages": ["en"], "default_language": "en"}
    r = await api.call(t, "POST", "/courses", json={**body, "organization_id": str(school.id), "template_key": "ort"})
    assert r.status_code == 201, r.text
    assert (r.json()["exam_family"], r.json()["subject"]) == ("ort", None)
    r = await api.call(t, "POST", "/courses", json={**body, "organization_id": str(school.id)})
    assert r.status_code == 201 and r.json()["exam_family"] is None
