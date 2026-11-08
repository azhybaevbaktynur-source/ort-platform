"""Admin orgs (item 4) slice A (ADMIN_ORGS_DESIGN 2.1-2.2): the platform organization list shows roots only with
subtree roll-ups (teachers, courses, students, storage, departments), `kind` filter, `name_asc` keyset, and an exact
statement count per page; `GET /usage` is the subtree roll-up; `GET /courses` takes `q` and `status`."""
from contextlib import contextmanager

from sqlalchemy import event

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import personal_org_id, platform_org_id
from app.lms.platform_admin import organizations_service as svc
from tests.lms.factories import make_asset
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

P = "/platform/organizations"


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


def _school_with_tree(db, name="School"):
    """A school with a department and a sub-department: members, courses, students and assets in every level."""
    school = make_org(db, name)
    dept = make_department(db, school, "Dept")
    sub = make_department(db, dept, "Sub")
    oa, t1, t2 = make_user(db), make_user(db), make_user(db)
    add_member(db, school, oa, "org_admin")
    add_member(db, school, t1, "teacher")
    add_member(db, dept, t2, "teacher")
    add_member(db, sub, t1, "teacher")  # the same teacher in two organizations of the tree counts once
    c1 = make_course(db, t1, organization_id=school.id, status="published")
    c2 = make_course(db, t2, organization_id=dept.id, status="published")
    c3 = make_course(db, t1, organization_id=sub.id, status="draft")
    make_course(db, t1, organization_id=sub.id, status="published", deleted_at=c1.created_at)  # deleted: not counted
    s1, s2, s3 = make_user(db), make_user(db), make_user(db)
    enroll(db, c1, s1)
    enroll(db, c2, s1)  # one student in two courses counts once
    enroll(db, c2, s2)
    enroll(db, c3, s3)
    enroll(db, c3, make_user(db), state="removed")  # not active
    test_student = enroll(db, c1, make_user(db))
    test_student.is_test_student = True
    db.commit()
    make_asset(db, t1, bytes=1000)
    make_asset(db, t2, bytes=500)
    make_asset(db, oa, bytes=25)
    return school, dept, sub


def test_new_route_is_listed():
    assert ROUTE_POLICIES[("GET", "/api/v1/platform/organizations/{organization_id}/students")] == "platform_admin"


async def test_roots_only_and_counts_roll_up_departments(db, api):
    admin = make_user(db, platform_admin=True)
    school, dept, sub = _school_with_tree(db)
    r = await api.call(admin, "GET", P)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["id"] for i in items] == [str(school.id)]  # departments are inside their school, never rows
    row = items[0]
    assert (row["org_admins"], row["teachers"], row["courses"], row["students"], row["departments"]) == (1, 2, 3, 3, 2)
    assert row["storage_bytes"] == 1525 and row["kind"] == "school" and row["is_protected"] is False
    # the detail row: same counts; a department's own row counts its subtree only
    one = (await api.call(admin, "GET", f"{P}/{school.id}")).json()
    assert {k: one[k] for k in ("teachers", "courses", "students", "departments")} == {
        "teachers": 2, "courses": 3, "students": 3, "departments": 2}
    d = (await api.call(admin, "GET", f"{P}/{dept.id}")).json()
    assert (d["teachers"], d["courses"], d["students"], d["departments"], d["storage_bytes"]) == (2, 2, 3, 1, 1500)


async def test_kind_filter_and_department_refused(db, api):
    admin = make_user(db, platform_admin=True)
    school = make_org(db, "School")
    make_department(db, school)
    t = teacher(db)  # personal organization
    ensure_platform_org(db.connection())
    db.commit()

    async def ids(**params):
        r = await api.call(admin, "GET", P, params=params)
        assert r.status_code == 200, r.text
        return {i["id"] for i in r.json()["items"]}

    assert await ids(kind="school") == {str(school.id)}
    assert await ids(kind="personal") == {str(personal_org_id(t.id))}
    assert await ids(kind="platform") == {str(platform_org_id())}
    assert await ids() == {str(school.id), str(personal_org_id(t.id)), str(platform_org_id())}
    r = await api.call(admin, "GET", P, params={"kind": "department"})
    assert r.status_code == 422
    plat = (await api.call(admin, "GET", f"{P}/{platform_org_id()}")).json()
    assert plat["is_protected"] is True


async def test_name_asc_cursor_stable_on_ties(db, api):
    admin = make_user(db, platform_admin=True)
    orgs = [make_org(db, n) for n in ("beta", "Alpha", "alpha", "ALPHA", "gamma")]
    seen, cursor = [], None
    while True:
        params = {"sort": "name_asc", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = (await api.call(admin, "GET", P, params=params)).json()
        seen += [i["id"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    alphas = sorted((o for o in orgs if o.name.lower() == "alpha"), key=lambda o: o.id)
    expected = [o.id for o in alphas] + [orgs[0].id, orgs[4].id]
    assert seen == [str(i) for i in expected]
    assert (await api.call(admin, "GET", P, params={"sort": "name_asc", "cursor": "bad"})).status_code == 422


async def test_filters_q_and_status(db, api):
    admin = make_user(db, platform_admin=True)
    a, b = make_org(db, "Lyceum One"), make_org(db, "Gymnasium", status="suspended")
    ids = lambda r: [i["id"] for i in r.json()["items"]]  # noqa: E731
    assert ids(await api.call(admin, "GET", P, params={"q": "lyceum"})) == [str(a.id)]
    assert ids(await api.call(admin, "GET", P, params={"status": "suspended"})) == [str(b.id)]
    assert ids(await api.call(admin, "GET", P, params={"q": "%"})) == []


def test_exact_statement_count_per_page(db):
    """Five grouped statements for the counts, whatever the page size (no N+1)."""
    roots = [_school_with_tree(db, f"S{i}")[0] for i in range(3)]
    for page in (roots[:1], roots):
        db.expire_all()
        loaded = [db.get(type(r), r.id) for r in page]
        with count_statements() as stmts:
            rows = svc.admin_rows(db, loaded)
        assert len(stmts) == 5, stmts
        assert [r.courses for r in rows] == [3] * len(page)
    with count_statements() as stmts:
        assert svc.admin_rows(db, []) == []
    assert stmts == []


async def test_usage_is_the_subtree_rollup(db, api):
    admin = make_user(db, platform_admin=True)
    school, dept, sub = _school_with_tree(db)
    r = await api.call(admin, "GET", f"{P}/{school.id}/usage")
    assert r.status_code == 200, r.text
    u = r.json()
    assert (u["courses"], u["students"], u["teachers"]) == (3, 3, 2)
    assert {d["id"] for d in u["by_department"]} == {str(dept.id), str(sub.id)}
    assert "course_files_bytes" in u


async def test_courses_q_and_status(db, api):
    admin = make_user(db, platform_admin=True)
    org = make_org(db)
    t = make_user(db)
    c1 = make_course(db, t, organization_id=org.id, title={"en": "Algebra basics"}, status="published")
    c2 = make_course(db, t, organization_id=org.id, title={"en": "Geometry"}, status="draft")
    ids = lambda r: [i["id"] for i in r.json()["items"]]  # noqa: E731
    assert set(ids(await api.call(admin, "GET", f"{P}/{org.id}/courses"))) == {str(c1.id), str(c2.id)}
    assert ids(await api.call(admin, "GET", f"{P}/{org.id}/courses", params={"q": "algebra"})) == [str(c1.id)]
    assert ids(await api.call(admin, "GET", f"{P}/{org.id}/courses", params={"status": "draft"})) == [str(c2.id)]
    assert (await api.call(admin, "GET", f"{P}/{org.id}/courses", params={"status": "nope"})).status_code == 422
