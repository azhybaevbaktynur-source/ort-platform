"""Phase 8c S1: `GET _C/modules/unsorted` (PHASE_8C_DESIGN 3.4, 7, 7.1; P8C-5).

Unsorted = live assignments (every kind; ORT preset exams only in general courses), page translation groups and
course files that no live item of a live module references. Staff and org admins read it; students 403; outsiders,
platform admins (not enrolled) and other courses 404. Paginated per kind with totals; bounded statement count."""
import uuid
from contextlib import contextmanager

from sqlalchemy import event

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from tests.lms.factories import make_user
from tests.lms.modules_support import (
    C, make_assignment, make_course_file, make_item, make_module, make_page, published_quiz, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

U = "/modules/unsorted"


@contextmanager
def count_statements():
    stmts = []

    def hook(conn, cursor, statement, parameters, context, executemany):
        stmts.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", hook)
    try:
        yield stmts
    finally:
        event.remove(db_session.engine, "before_cursor_execute", hook)


async def unsorted(api, w, user=None, **params):
    r = await api.call(user or w.O, "GET", f"{C(w)}{U}", params=params or None)
    assert r.status_code == 200, r.text
    return r.json()


def ids_of(page) -> set:
    return {i["id"] for i in page["items"]}


def test_policies_declared():
    assert ROUTE_POLICIES[("GET", "/api/v1/courses/{course_id}/modules/unsorted")] == "course:content.read+staff"
    assert ROUTE_POLICIES[("POST", "/api/v1/courses/{course_id}/modules/{module_id}/duplicate")] == \
        "course:content.manage"
    assert ROUTE_POLICIES[("GET", "/api/v1/courses/{course_id}/todo")] == "course:content.read+staff"


async def test_unsorted_membership(db, api):
    w = structure_world(db)
    live, gone = make_module(db, w.course, w.O), make_module(db, w.course, w.O)
    in_module = make_assignment(db, w.course, w.O, kind="text")
    in_deleted_module = make_assignment(db, w.course, w.O, kind="file")
    in_deleted_item = make_assignment(db, w.course, w.O, kind="none", published=False)
    loose = make_assignment(db, w.course, w.O, kind="text", title={"en": "Loose", "ru": "Свободное"})
    deleted = make_assignment(db, w.course, w.O, kind="text")
    deleted.soft_delete(w.O.id)
    quiz = published_quiz(db, w.course, w.O)
    make_item(db, live, in_module)
    make_item(db, gone, in_deleted_module)
    it = make_item(db, live, in_deleted_item)
    from app.lms.core.models import utcnow

    it.deleted_at = utcnow()
    gone.deleted_at = utcnow()
    db.commit()
    # pages: a group with one referenced variant is not listed; an unreferenced group is, once, with its variants
    used_en = make_page(db, w.course, w.O, title="Used", language="en")
    make_page(db, w.course, w.O, title="Used ru", language="ru", group=used_en)
    make_item(db, live, used_en)
    free_en = make_page(db, w.course, w.O, title="Free", language="en", published=False)
    free_ru = make_page(db, w.course, w.O, title="Free ru", language="ru", group=free_en)
    # files
    f_used = make_course_file(db, w.course, w.O, title="a.pdf")
    make_item(db, live, f_used)
    f_free = make_course_file(db, w.course, w.O, title="b.pdf", folder="week1", published=False)

    out = await unsorted(api, w)
    a_ids = ids_of(out["assignments"])
    assert {str(in_deleted_module.id), str(in_deleted_item.id), str(loose.id), str(quiz.id)} == a_ids
    assert out["assignments"]["total"] == 4
    row = next(i for i in out["assignments"]["items"] if i["id"] == str(loose.id))
    assert row["kind"] == "assignment" and row["title"] == {"en": "Loose", "ru": "Свободное"}
    assert row["assignment_kind"] == "text" and row["published"] is True
    qrow = next(i for i in out["assignments"]["items"] if i["id"] == str(quiz.id))
    assert qrow["assignment_kind"] == "quiz" and qrow["assessment_id"] == str(quiz.assessment_id)
    pages = out["pages"]["items"]
    assert len(pages) == 1 and out["pages"]["total"] == 1
    assert pages[0]["id"] == str(free_en.id) and pages[0]["title"] == "Free" and pages[0]["published"] is False
    assert pages[0]["translation_group_id"] == str(free_en.translation_group_id)
    assert {(v["id"], v["language"]) for v in pages[0]["variants"]} == {(str(free_en.id), "en"),
                                                                        (str(free_ru.id), "ru")}
    files = out["files"]["items"]
    assert [f["id"] for f in files] == [str(f_free.id)] and files[0]["folder"] == "week1"
    assert files[0]["title"] == "b.pdf" and out["files"]["total"] == 1
    # kind=: only that page
    only = await unsorted(api, w, kind="file")
    assert only["assignments"] is None and only["pages"] is None and ids_of(only["files"]) == {str(f_free.id)}


async def test_ort_preset_exam_listed_only_in_general_courses(db, api):
    w = structure_world(db)
    ort_exam = published_quiz(db, w.course, w.O, preset="ort_main")
    assert str(ort_exam.id) in ids_of((await unsorted(api, w))["assignments"])
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    plain = published_quiz(db, w.course, w.O)
    out = await unsorted(api, w)
    assert str(ort_exam.id) not in ids_of(out["assignments"]) and str(plain.id) in ids_of(out["assignments"])


async def test_unsorted_access_matrix(db, api):
    w = structure_world(db)
    make_assignment(db, w.course, w.O)
    for user in (w.O, w.T):
        assert (await api.call(user, "GET", f"{C(w)}{U}")).status_code == 200
    r = await api.call(w.OA, "GET", f"{C(w)}{U}")
    assert r.status_code == 200 and r.json()["assignments"]["total"] == 1  # org admin (A13)
    assert (await api.call(w.S, "GET", f"{C(w)}{U}")).status_code == 403
    assert (await api.call(w.X, "GET", f"{C(w)}{U}")).status_code == 404
    admin = make_user(db, platform_admin=True)
    assert (await api.call(admin, "GET", f"{C(w)}{U}")).status_code == 404
    other = structure_world(db)
    assert (await api.call(w.O, "GET", f"{C(other)}{U}")).status_code == 404
    assert (await api.call(w.O, "GET", f"/courses/{uuid.uuid4()}{U}")).status_code == 404
    # concluded course: still readable
    from tests.lms.factories import set_status

    set_status(db, w.course, "concluded")
    assert (await api.call(w.O, "GET", f"{C(w)}{U}")).status_code == 200
    # a cursor without a kind is refused
    r = await api.call(w.O, "GET", f"{C(w)}{U}", params={"cursor": "x"})
    assert r.status_code == 422


async def test_pagination_per_kind_and_bounded_statements(db, api):
    w = structure_world(db)
    for i in range(3):
        make_assignment(db, w.course, w.O, title={"en": f"A{i}"})
        make_page(db, w.course, w.O, title=f"P{i}")
        make_course_file(db, w.course, w.O, title=f"f{i}.pdf")
    with count_statements() as small:
        await unsorted(api, w)
    for i in range(3, 30):
        make_assignment(db, w.course, w.O, title={"en": f"A{i}"})
        p = make_page(db, w.course, w.O, title=f"P{i}")
        make_page(db, w.course, w.O, title=f"P{i} ru", language="ru", group=p)
        make_course_file(db, w.course, w.O, title=f"f{i:02d}.pdf")
    with count_statements() as large:
        out = await unsorted(api, w)
    assert len(large) == len(small), (len(small), len(large))
    for key in ("assignments", "pages", "files"):
        assert out[key]["total"] == 30 and len(out[key]["items"]) == 20 and out[key]["next_cursor"]
    # walk the assignments with limit 7: every row once, in position order
    seen, cursor = [], None
    while True:
        page = await unsorted(api, w, kind="assignment", limit=7, **({"cursor": cursor} if cursor else {}))
        assert page["pages"] is None and page["files"] is None
        seen += [i["id"] for i in page["assignments"]["items"]]
        cursor = page["assignments"]["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 30
    # the limit is capped at 50
    big = await unsorted(api, w, kind="page", limit=100)
    assert len(big["pages"]["items"]) == 30 and big["pages"]["next_cursor"] is None
    assert all(len(i["variants"]) in (1, 2) for i in big["pages"]["items"])
