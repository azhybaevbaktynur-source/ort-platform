"""Phase 8a S2: authorization of every modules route (PHASE_8A_DESIGN 7.1, 7.3), action x role x course status:
teacher and assistant manage (draft and published; concluded is read-only), students read their own evaluated
outline and record facts only in a published course, org admins read the student shape and never write, outsiders
and other courses' teachers get 404, course-scoped loaders answer 404 for another course's ids, and a student never
reads another student's progress."""
import uuid

import pytest

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.modules.policies import MODULE_POLICIES
from tests.lms.modules_support import (
    C, I, M, make_item, make_module, make_page, set_requirement, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

READ = {"GET modules"}
STUDENT = {"POST view", "POST done"}
STAFF_READ = {"GET progress"}


def _setup(db, status):
    w = structure_world(db, status="published")
    w.m1 = make_module(db, w.course, w.O)
    w.m2 = make_module(db, w.course, w.O)
    w.page = make_page(db, w.course, w.O)
    w.item = make_item(db, w.m1, w.page)
    set_requirement(db, w.item, "view")
    w.item2 = make_item(db, w.m1, "https://x.org")
    if status != "published":
        w.course.status = status
        db.commit()
    return w


def routes(w):
    """(name, method, path, body) for every route of MODULE_POLICIES."""
    return [
        ("GET modules", "GET", f"{C(w)}/modules", None),
        ("POST modules", "POST", f"{C(w)}/modules", {"title": {"en": "N"}}),
        ("PATCH module", "PATCH", M(w, w.m1), {"sequential": True}),
        ("DELETE module", "DELETE", M(w, w.m2), None),
        ("POST restore", "POST", M(w, w.m2) + "/restore", None),
        ("PUT order", "PUT", f"{C(w)}/modules/order", {"ids": [str(w.m1.id), str(w.m2.id)]}),
        ("PUT prerequisites", "PUT", M(w, w.m2) + "/prerequisites", {"module_ids": [str(w.m1.id)]}),
        ("POST items", "POST", M(w, w.m1) + "/items", {"kind": "url", "url": "https://y.org"}),
        ("PATCH item", "PATCH", I(w, w.m1, w.item2), {"indent": 1}),
        ("DELETE item", "DELETE", I(w, w.m1, w.item2), None),
        ("PUT items order", "PUT", M(w, w.m1) + "/items/order", {"ids": [str(w.item.id), str(w.item2.id)]}),
        ("PUT move", "PUT", I(w, w.m1, w.item2) + "/move", {"module_id": str(w.m2.id), "position": 1}),
        ("PUT requirement", "PUT", I(w, w.m1, w.item2) + "/requirement", {"type": "view"}),
        ("DELETE requirement", "DELETE", I(w, w.m1, w.item) + "/requirement", None),
        ("POST quiz", "POST", M(w, w.m1) + "/quiz", {"title": {"en": "Q"}, "kind": "quiz",
                                                    "quiz": {"languages": ["en"]}}),
        ("POST reapply", "POST", f"{C(w)}/modules/reapply", None),
        ("POST module reapply", "POST", M(w, w.m1) + "/reapply", None),
        ("POST view", "POST", I(w, w.m1, w.item) + "/view", None),
        ("POST done", "POST", I(w, w.m1, w.item) + "/done", {"done": True}),
        ("GET progress", "GET", f"{C(w)}/modules/progress/{w.enr.id}", None),
    ]


def test_every_route_is_listed_with_its_policy():
    assert len(MODULE_POLICIES) == 22  # Phase 8c S1: + GET modules/unsorted, POST modules/{mid}/duplicate
    for key, policy in MODULE_POLICIES.items():
        assert ROUTE_POLICIES[key] == policy


def expected(role: str, status: str, name: str) -> int:
    """The status class a role gets (2 = success; 403; 404)."""
    if role == "X":
        return 404
    staff = role in ("O", "T")
    if name in READ:
        if role == "S" and status == "draft":
            return 403
        return 2
    if name in STUDENT:
        return 2 if role == "S" and status == "published" else 403
    if name in STAFF_READ:
        return 2 if staff else 403
    return 2 if staff and status != "concluded" else 403


@pytest.mark.parametrize("status", ["draft", "published", "concluded"])
@pytest.mark.parametrize("role", ["S", "OA", "X"])
async def test_non_staff_matrix(db, api, status, role):
    w = _setup(db, status)
    user = getattr(w, role)
    for name, method, path, body in routes(w):
        r = await api.call(user, method, path, json=body)
        want = expected(role, status, name)
        got = 2 if 200 <= r.status_code < 300 else r.status_code
        assert got == want, (role, status, name, r.status_code, r.text)


@pytest.mark.parametrize("status", ["draft", "published", "concluded"])
@pytest.mark.parametrize("role", ["O", "T"])
async def test_staff_matrix(db, api, status, role):
    """One fresh course per route so destructive routes do not depend on each other."""
    for idx in range(20):
        w = _setup(db, status)
        if idx == 4:  # restore needs a deleted module
            w.m2.soft_delete(w.O.id)
            db.commit()
        name, method, path, body = routes(w)[idx]
        r = await api.call(getattr(w, role), method, path, json=body)
        want = expected(role, status, name)
        got = 2 if 200 <= r.status_code < 300 else r.status_code
        assert got == want, (role, status, name, r.status_code, r.text)


async def test_other_course_teacher_and_cross_course_ids(db, api):
    w = _setup(db, "published")
    other = _setup(db, "published")
    for name, method, path, body in routes(w):
        r = await api.call(other.O, method, path, json=body)
        assert r.status_code == 404, (name, r.status_code)
    # other course's own path with this course's module / item / enrollment ids
    ob = f"/courses/{other.cid}/modules"
    for method, path, body in [
        ("PATCH", f"{ob}/{w.m1.id}", {"sequential": True}),
        ("DELETE", f"{ob}/{w.m1.id}", None),
        ("PUT", f"{ob}/{w.m1.id}/prerequisites", {"module_ids": []}),
        ("POST", f"{ob}/{w.m1.id}/items", {"kind": "url", "url": "https://y.org"}),
        ("PATCH", f"{ob}/{other.m1.id}/items/{w.item.id}", {"indent": 1}),
        ("PUT", f"{ob}/{other.m1.id}/items/{other.item.id}/move", {"module_id": str(w.m1.id), "position": 1}),
        ("POST", f"{ob}/{w.m1.id}/reapply", None),
        ("GET", f"{ob}/progress/{w.enr.id}", None),
    ]:
        r = await api.call(other.O, method, path, json=body)
        assert r.status_code == 404, (method, path, r.text)
    r = await api.call(other.S, "POST", f"{ob}/{w.m1.id}/items/{w.item.id}/view")
    assert r.status_code == 404
    r = await api.call(w.O, "PATCH", f"{C(w)}/modules/{uuid.uuid4()}/items/{w.item.id}", json={"indent": 1})
    assert r.status_code == 404


async def test_student_reads_only_own_progress(db, api):
    w = _setup(db, "published")
    assert (await api.call(w.S, "GET", f"{C(w)}/modules/progress/{w.enr.id}")).status_code == 403
    assert (await api.call(w.S, "GET", f"{C(w)}/modules/progress/{w.enr2.id}")).status_code == 403
    assert (await api.call(w.S, "POST", I(w, w.m1, w.item) + "/view")).status_code == 200
    mine = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    theirs = (await api.call(w.S2, "GET", f"{C(w)}/modules")).json()
    assert mine["modules"][0]["state"] == "completed" and theirs["modules"][0]["state"] == "unlocked"


async def test_org_admin_reads_student_shape_without_state(db, api):
    w = _setup(db, "published")
    out = (await api.call(w.OA, "GET", f"{C(w)}/modules")).json()
    assert [m["state"] for m in out["modules"]] == [None, None] and out["up_next"] is None
    assert out["modules"][0]["items"][0]["requirement"] == {"type": "view", "threshold": None, "met": False,
                                                            "best_score_percent": None}
    assert "rules_version" not in out["modules"][0]
