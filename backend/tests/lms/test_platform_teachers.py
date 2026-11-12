"""Step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2): `GET /platform/teachers`, one row per person who teaches
(independent, school, both), counts without test students, disabled accounts or deleted courses, five statements per
page, `q`, `kind` and `status` filters, platform admin only; the person page's `teaching` card."""
import uuid
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import event

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.core.models import utcnow
from app.lms.platform_admin import teachers as svc
from app.lms.teachers.models import TeacherRequest
from app.models.user import User
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

P = "/platform/teachers"


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


def _tag() -> str:
    return "t" + uuid.uuid4().hex[:8]


def _people(db, tag):
    """independent (approved, personal courses), revoked, school-only (org admin of a department), both (approved and
    a school teacher), a student (no row), a pending applicant (no row), a test student teacher (no row)."""
    school = make_org(db, f"Школа {tag}")
    dept = make_department(db, school, "Dept")
    other = make_org(db, f"Гимназия {tag}")
    indep = teacher(db, display_name=f"Айбек {tag}")
    revoked = make_user(db, teacher_status="revoked", display_name=f"Бакыт {tag}")
    school_only = make_user(db, display_name=f"Гуля {tag}")
    add_member(db, dept, school_only, "org_admin")
    both = teacher(db, display_name=f"Динара {tag}")
    add_member(db, school, both, "teacher")
    add_member(db, other, both, "teacher")
    student = make_user(db, display_name=f"Ученик {tag}")
    pending = make_user(db, teacher_status="pending", display_name=f"Заявка {tag}")
    removed = make_user(db, display_name=f"Ушла {tag}")
    add_member(db, school, removed, "teacher", state="removed")
    ghost = make_user(db, teacher_status="approved", display_name=f"Тест {tag}")
    ghost.is_test_student = True
    db.commit()
    return dict(school=school, dept=dept, other=other, indep=indep, revoked=revoked, school_only=school_only,
                both=both, student=student, pending=pending, removed=removed, ghost=ghost)


def test_route_is_listed():
    assert ROUTE_POLICIES[("GET", "/api/v1/platform/teachers")] == "platform_admin"


async def test_rows_per_person_kind(db, api):
    admin = make_user(db, platform_admin=True)
    tag = _tag()
    p = _people(db, tag)
    r = await api.call(admin, "GET", P, params={"q": tag})
    assert r.status_code == 200, r.text
    rows = {i["user"]["id"]: i for i in r.json()["items"]}
    assert set(rows) == {p["indep"].id, p["revoked"].id, p["school_only"].id, p["both"].id}
    assert [i["user"]["display_name"] for i in r.json()["items"]] == [
        f"Айбек {tag}", f"Бакыт {tag}", f"Гуля {tag}", f"Динара {tag}"]  # by name
    assert (rows[p["indep"].id]["kind"], rows[p["indep"].id]["schools"]) == ("independent", [])
    assert (rows[p["revoked"].id]["kind"], rows[p["revoked"].id]["teacher_status"]) == ("independent", "revoked")
    assert rows[p["school_only"].id]["kind"] == "school"
    assert rows[p["school_only"].id]["schools"] == [f"Школа {tag}"]  # the department's school
    assert rows[p["both"].id]["kind"] == "both"
    assert rows[p["both"].id]["schools"] == [f"Гимназия {tag}", f"Школа {tag}"]
    assert rows[p["both"].id]["school_count"] == 2
    assert rows[p["school_only"].id]["since"] is not None


async def test_schools_capped_at_three(db, api):
    admin = make_user(db, platform_admin=True)
    tag = _tag()
    t = make_user(db, display_name=f"Много {tag}")
    for i in range(5):
        add_member(db, make_org(db, f"S{i} {tag}"), t, "teacher")
    item = (await api.call(admin, "GET", P, params={"q": tag})).json()["items"][0]
    assert item["schools"] == [f"S0 {tag}", f"S1 {tag}", f"S2 {tag}"] and item["school_count"] == 5


async def test_counts_exclude_test_students_disabled_and_deleted_courses(db, api):
    admin = make_user(db, platform_admin=True)
    tag = _tag()
    t = teacher(db, display_name=f"Счёт {tag}")
    other_owner = teacher(db)
    c1 = make_course(db, t, status="published", listing="listed")
    c2 = make_course(db, t, status="draft")
    staffed = make_course(db, other_owner, status="published", listing="listed")
    enroll(db, staffed, t, role="assistant")
    gone = make_course(db, t, status="published", listing="listed", deleted_at=utcnow())
    s1, s2, s3 = make_user(db), make_user(db), make_user(db)
    enroll(db, c1, s1)
    enroll(db, c2, s1)  # one student in two courses counts once
    enroll(db, staffed, s2)
    enroll(db, c1, s3, state="removed")
    enroll(db, gone, make_user(db))  # a deleted course's student
    enroll(db, c1, make_user(db, disabled=True))  # a disabled account
    test_enr = enroll(db, c1, make_user(db))
    test_enr.is_test_student = True
    db.commit()
    item = (await api.call(admin, "GET", P, params={"q": tag})).json()["items"][0]
    assert (item["courses"], item["students"], item["listed_courses"]) == (3, 2, 2)


async def test_filters_and_since(db, api):
    admin = make_user(db, platform_admin=True)
    tag = _tag()
    p = _people(db, tag)
    approved_at = utcnow() - timedelta(days=30)
    db.add(TeacherRequest(user_id=p["indep"].id, status="approved", decided_at=approved_at))
    db.commit()

    async def ids(**params):
        r = await api.call(admin, "GET", P, params={"q": tag, **params})
        assert r.status_code == 200, r.text
        return {i["user"]["id"] for i in r.json()["items"]}

    assert await ids(kind="independent") == {p["indep"].id, p["revoked"].id}
    assert await ids(kind="school") == {p["school_only"].id, p["both"].id}
    assert await ids(status="revoked") == {p["revoked"].id}
    assert await ids(status="approved", kind="school") == {p["both"].id}
    assert await ids(q=p["indep"].email.upper()) == {p["indep"].id}  # email, case-insensitive
    assert await ids(q="%") == set()
    for bad in ({"kind": "personal"}, {"kind": "both"}, {"status": "pending"}):
        assert (await api.call(admin, "GET", P, params=bad)).status_code == 422
    row = (await api.call(admin, "GET", P, params={"q": p["indep"].email})).json()["items"][0]
    assert row["since"].startswith(approved_at.date().isoformat())


async def test_cursor_pages_by_name(db, api):
    admin = make_user(db, platform_admin=True)
    tag = _tag()
    made = [teacher(db, display_name=f"{n} {tag}") for n in ("beta", "Alpha", "alpha", "gamma")]
    seen, cursor = [], None
    while True:
        params = {"q": tag, "limit": 2, **({"cursor": cursor} if cursor else {})}
        body = (await api.call(admin, "GET", P, params=params)).json()
        seen += [i["user"]["id"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    alphas = sorted((u for u in made if u.display_name.lower().startswith("alpha")), key=lambda u: u.id)
    assert seen == [u.id for u in alphas] + [made[0].id, made[3].id]
    assert (await api.call(admin, "GET", P, params={"cursor": "bad"})).status_code == 422


def test_five_statements_per_page(db):
    """The page plus four grouped statements, whatever the page size (no N+1)."""
    tag = _tag()
    for i in range(3):
        p = _people(db, f"{tag}{i}")
        make_course(db, p["indep"], status="published")
        make_course(db, p["both"], status="published", listing="listed")
    from app.lms.platform_admin.organizations_service import paginate_by_text

    for limit in (1, 12):
        db.expire_all()
        with count_statements() as stmts:
            rows, _ = paginate_by_text(db, svc.teachers_query(tag, None, None), sort_expr=svc.sort_expr(),
                                       id_col=User.id, id_of=lambda r: r[0].id, cursor=None, limit=limit)
            out = svc.teacher_rows(db, rows)
        assert len(out) == min(limit, 12)
        assert len(stmts) == 5, stmts
    with count_statements() as stmts:
        assert svc.teacher_rows(db, []) == []
    assert stmts == []


async def test_platform_admin_only(db, api):
    tag = _tag()
    p = _people(db, tag)
    for who in (p["indep"], p["school_only"], p["student"], None):
        r = await api.call(who, "GET", P)
        assert r.status_code in ((401,) if who is None else (403,)), r.text


async def test_person_page_teaching_card(db, api):
    admin = make_user(db, platform_admin=True)
    tag = _tag()
    p = _people(db, tag)
    make_course(db, p["both"], status="published", listing="listed")
    card = (await api.call(admin, "GET", f"/platform/users/{p['both'].id}")).json()["teaching"]
    assert card["kind"] == "both" and card["courses"] == 1 and card["listed_courses"] == 1
    assert card["schools"] == [f"Гимназия {tag}", f"Школа {tag}"]
    indep = (await api.call(admin, "GET", f"/platform/users/{p['indep'].id}")).json()["teaching"]
    assert indep["kind"] == "independent" and indep["schools"] == []
    assert (await api.call(admin, "GET", f"/platform/users/{p['student'].id}")).json()["teaching"] is None


async def test_audit_viewer_gets_the_organization_kind(db, api):
    """The audit log labels a personal organization target (the viewer says «личное пространство преподавателя»)."""
    from app.lms.audit import service as audit
    from app.lms.organizations.ids import personal_org_id

    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    school = make_org(db, "Audit School")
    tag = _tag()
    for target in (str(personal_org_id(t.id)), str(school.id), "not-a-uuid"):
        audit.record(db, actor=admin, action=f"organization.{tag}", target_type="organization", target_id=target)
    audit.record(db, actor=admin, action=f"organization.{tag}", target_type="user", target_id=t.id)
    db.commit()
    r = await api.call(admin, "GET", "/platform/audit-log", params={"action": f"organization.{tag}"})
    kinds = {i["target_id"]: i["target_kind"] for i in r.json()["items"]}
    assert kinds == {str(personal_org_id(t.id)): "personal", str(school.id): "school", "not-a-uuid": None, t.id: None}
