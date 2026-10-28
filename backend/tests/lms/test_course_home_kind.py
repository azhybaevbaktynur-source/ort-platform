"""Phase 8a S3: course home kind and student tab features (PHASE_8A_DESIGN 2.1, 5.5, 8.2, 13, invariant 7, P8A-7):
transitions, `home_page_invalid`, page delete resets the home, ORT 409 `template_locked`, new general courses default
to `modules`, ORT courses (created and seeded) stay `assignments`, `features` computed from published rows."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.courses.service import _default_home_kind
from app.lms.pages.models import Page
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage  # noqa: F401
from tests.lms.factories import make_course
from tests.lms.modules_support import (
    C, make_announcement, make_course_file, make_module, make_page, structure_world,
)
from tests.lms.org_support import add_member, grant, make_org
from tests.lms.s3_support import teacher
from tests.lms.structure_content_support import gate_calls, open_gate  # noqa: F401

BODY = {"title": {"en": "Algebra"}, "languages": ["en"], "default_language": "en"}


def course_of(db, w) -> Course:
    db.expire_all()
    return db.get(Course, w.course.id)


async def patch(api, user, w, body):
    return await api.call(user, "PATCH", C(w), json=body)


async def test_transitions(api, db):
    w = structure_world(db)
    p = make_page(db, w.course, w.O)
    res = await patch(api, w.O, w, {"home_kind": "page", "home_page_id": str(p.id)})
    assert res.status_code == 200, res.text
    assert (res.json()["home_kind"], res.json()["home_page_id"]) == ("page", str(p.id))
    # changing only other fields keeps the home
    res = await patch(api, w.O, w, {"title": {"en": "Renamed"}})
    assert res.json()["home_kind"] == "page"
    res = await patch(api, w.T, w, {"home_kind": "modules"})
    assert res.status_code == 200 and (res.json()["home_kind"], res.json()["home_page_id"]) == ("modules", None)
    res = await patch(api, w.O, w, {"home_kind": "assignments"})
    assert res.json()["home_kind"] == "assignments"
    c = course_of(db, w)
    assert (c.home_kind, c.home_page_id) == ("assignments", None)


async def test_home_page_invalid(api, db):
    w = structure_world(db)
    other = structure_world(db)
    foreign = make_page(db, other.course, other.O)
    deleted = make_page(db, w.course, w.O)
    deleted.soft_delete(w.O.id)
    db.commit()
    own = make_page(db, w.course, w.O)
    for body in ({"home_kind": "page"}, {"home_kind": "page", "home_page_id": None},
                 {"home_kind": "page", "home_page_id": str(foreign.id)},
                 {"home_kind": "page", "home_page_id": str(deleted.id)},
                 {"home_kind": "page", "home_page_id": str(uuid.uuid4())},
                 {"home_kind": "modules", "home_page_id": str(own.id)}):
        res = await patch(api, w.O, w, body)
        assert res.status_code == 422 and res.json()["error"]["code"] == "home_page_invalid", (body, res.text)
    assert (await patch(api, w.O, w, {"home_kind": None})).status_code == 422
    assert (await patch(api, w.O, w, {"home_kind": "weird"})).status_code == 422
    c = course_of(db, w)
    assert (c.home_kind, c.home_page_id) == ("assignments", None)


async def test_who_may_change_home(api, db):
    w = structure_world(db)
    for user, status in ((w.S, 403), (w.OA, 403), (w.X, 404)):
        res = await patch(api, user, w, {"home_kind": "modules"})
        assert res.status_code == status, (user, res.text)
    assert course_of(db, w).home_kind == "assignments"


async def test_page_delete_resets_home(api, db):
    w = structure_world(db)
    p = make_page(db, w.course, w.O)
    await patch(api, w.O, w, {"home_kind": "page", "home_page_id": str(p.id)})
    assert (await api.call(w.T, "DELETE", f"{C(w)}/pages/{p.id}")).status_code == 204
    c = course_of(db, w)
    assert (c.home_kind, c.home_page_id) == ("assignments", None)
    # deleting another page leaves a page home alone
    p2 = make_page(db, w.course, w.O)
    p3 = make_page(db, w.course, w.O)
    await patch(api, w.O, w, {"home_kind": "page", "home_page_id": str(p2.id)})
    await api.call(w.O, "DELETE", f"{C(w)}/pages/{p3.id}")
    assert course_of(db, w).home_page_id == p2.id


async def test_ort_home_locked(api, db):
    owner = teacher(db)
    ort = make_course(db, owner, status="published", template_key="ort", template_version=1, template_locked=True,
                      template_settings={"language": "en"})
    res = await api.call(owner, "PATCH", f"/courses/{ort.id}", json={"home_kind": "modules"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "template_locked"
    assert res.json()["error"]["details"] == {"field": "home_kind"}
    res = await api.call(owner, "PATCH", f"/courses/{ort.id}", json={"home_page_id": None})
    assert res.status_code == 409
    # other fields still editable; home stays today's layout
    res = await api.call(owner, "PATCH", f"/courses/{ort.id}", json={"title": {"en": "ORT renamed"}})
    assert res.status_code == 200 and res.json()["home_kind"] == "assignments"
    # an unlocked ORT course (admin unlocked the template) may change it
    ort.template_locked = False
    db.commit()
    assert (await api.call(owner, "PATCH", f"/courses/{ort.id}", json={"home_kind": "modules"})).status_code == 200


async def test_new_general_course_defaults_to_modules_and_ort_to_assignments(api, db):
    t = teacher(db)
    res = await api.call(t, "POST", "/courses", json=BODY)
    assert res.status_code == 201 and res.json()["home_kind"] == "modules"
    assert _default_home_kind(None) == "modules" and _default_home_kind("ort") == "assignments"
    assert _default_home_kind("retired_kind") == "modules"
    school = make_org(db)
    add_member(db, school, t, role="org_admin")
    grant(db, school)
    res = await api.call(t, "POST", "/courses", json={**BODY, "organization_id": str(school.id),
                                                     "template_key": "ort"})
    assert res.status_code == 201, res.text
    assert res.json()["home_kind"] == "assignments"


def test_ort_seed_courses_stay_assignments(db):
    from app.lms.ort.seed import course_id_for, ensure_ort_courses

    ensure_ort_courses(db, samples=False)
    db.expire_all()
    for lang in ("ky", "ru"):
        c = db.get(Course, course_id_for(lang))
        assert c is not None and (c.home_kind, c.home_page_id) == ("assignments", None)
        assert db.scalar(select(func.count()).select_from(Page).where(Page.course_id == c.id)) == 0


async def test_features_follow_published_rows(api, db):
    w = structure_world(db)

    async def features(user):
        res = await api.call(user, "GET", C(w))
        assert res.status_code == 200, res.text
        return res.json()["features"]

    none = {"modules": False, "files": False, "announcements": False}
    assert await features(w.S) == none
    make_module(db, w.course, w.O, published=False)
    make_course_file(db, w.course, w.O, published=False)
    make_announcement(db, w.course, w.O, published=False)
    make_announcement(db, w.course, w.O, published_at=utcnow() + timedelta(days=1))
    gone = make_module(db, w.course, w.O)
    gone.soft_delete(w.O.id)
    db.commit()
    assert await features(w.S) == none
    make_module(db, w.course, w.O)
    assert await features(w.S) == {"modules": True, "files": False, "announcements": False}
    make_course_file(db, w.course, w.O)
    make_announcement(db, w.course, w.O)
    full = {"modules": True, "files": True, "announcements": True}
    assert await features(w.S) == full
    assert await features(w.O) == full  # staff shape carries the same flags
