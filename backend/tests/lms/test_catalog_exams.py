"""Step 3a S1 (STUDENT_IA_DESIGN 4, 6.3): `GET /catalog/exams` (the choose step: families of listed, published, open
platform courses, main courses first, then subjects in registry order, with `enrolled`; an allow-list; two statements
whatever the count; teachers read it, test students do not) and `GET /catalog/courses?exam=ort|nct|other` (one
family or none, main courses first, keyset pages that lose and repeat nothing)."""
from __future__ import annotations

import re
from datetime import timedelta

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.core.models import utcnow
from app.lms.courses.catalog_router import EXAM_COURSE_KEYS
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from tests.lms.factories import enroll, make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

TIMING = re.compile(r'desc="n=(\d+)"')
T0 = utcnow()


def queries(res) -> int:
    return int(TIMING.search(res.headers["server-timing"]).group(1))


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


class Clock:
    """Distinct publish times, newest last made."""
    n = 0

    @classmethod
    def next(cls):
        cls.n += 1
        return T0 + timedelta(seconds=cls.n)


def platform_course(db, owner, title, *, family="ort", subject=None, lang="ru", **kw):
    fields = dict(title={lang: title}, languages=[lang], default_language=lang, status="published",
                  visibility="catalog", enrollment_mode="open", organization_id=platform_org_id(),
                  published_at=Clock.next(), exam_family=family, subject=subject)
    fields.update(kw)
    return make_course(db, owner, **fields)


def setup(db):
    ensure_platform_org(db.connection())
    db.commit()
    return make_user(db, platform_admin=True, teacher_status="approved")


def catalog_world(db):
    admin = setup(db)
    c = {
        "ru": platform_course(db, admin, "ОРТ (рус)"),
        "physics": platform_course(db, admin, "Физика", subject="physics"),
        "math": platform_course(db, admin, "Математика", subject="math"),
        "ky": platform_course(db, admin, "ОРТ (кырг)", lang="ky"),
        "nct": platform_course(db, admin, "НЦТ", family="nct"),
        "plain": platform_course(db, admin, "Masterclass", family=None),
    }
    # never listed by /catalog/exams
    c["code"] = platform_course(db, admin, "Code", enrollment_mode="invite_code")  # in the catalog, not here
    platform_course(db, admin, "Private", visibility="private")
    platform_course(db, admin, "Unknown family", family="sat")
    teacher = make_user(db, teacher_status="approved")
    c["teacher"] = make_course(db, teacher, title={"en": "Teacher ORT"}, status="published", visibility="catalog",
                               enrollment_mode="open", published_at=Clock.next(), exam_family="ort")
    return admin, c


def test_routes_listed():
    assert ROUTE_POLICIES[("GET", "/api/v1/catalog/exams")] == "authenticated"
    assert ROUTE_POLICIES[("GET", "/api/v1/catalog/courses")] == "authenticated"


async def test_families_subjects_and_enrolled(db, api):
    _, c = catalog_world(db)
    s = make_user(db)
    enroll(db, c["math"], s)
    r = await api.call(s, "GET", "/catalog/exams")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [f["family"] for f in body] == ["ort", "nct"]
    ort = body[0]["courses"]
    # main courses first (newest first), then subjects in the registry's order (math before physics)
    assert [x["id"] for x in ort] == [str(c[k].id) for k in ("ky", "ru", "math", "physics")]
    assert [x["subject"] for x in ort] == [None, None, "math", "physics"]
    assert [x["enrolled"] for x in ort] == [False, False, True, False]
    assert all(set(x) == EXAM_COURSE_KEYS for f in body for x in f["courses"])
    assert EXAM_COURSE_KEYS == {"id", "title", "description", "default_language", "subject", "lessons_count",
                                "tests_count", "has_paid_tests", "enrolled"}
    assert ort[0]["default_language"] == "ky" and body[1]["courses"][0]["id"] == str(c["nct"].id)
    for secret in (c["ru"].join_code,):
        assert secret not in r.text


async def test_no_family_without_courses(db, api):
    admin = setup(db)
    platform_course(db, admin, "ОРТ (рус)")
    body = (await api.call(make_user(db), "GET", "/catalog/exams")).json()
    assert [f["family"] for f in body] == ["ort"]


async def test_two_statements_whatever_the_count(db, api):
    admin = setup(db)
    platform_course(db, admin, "One")
    s = make_user(db)
    await api.call(s, "GET", "/catalog/exams")
    few = queries(await api.call(s, "GET", "/catalog/exams"))
    for i in range(12):
        platform_course(db, admin, f"Subject {i}", subject="math" if i % 2 else "history",
                        family="ort" if i % 3 else "nct")
    many = queries(await api.call(s, "GET", "/catalog/exams"))
    assert few == many <= 3, (few, many)  # the user, the courses, their card extras


async def test_teachers_read_it_test_students_do_not(db, api):
    admin, c = catalog_world(db)
    for user in (make_user(db, teacher_status="approved"), admin):
        r = await api.call(user, "GET", "/catalog/exams")
        assert r.status_code == 200 and r.json()[0]["family"] == "ort"
    tester = make_user(db)
    tester.is_test_student = True
    enroll(db, c["ru"], tester).is_test_student = True
    db.commit()
    r = await api.call(tester, "GET", "/catalog/exams")
    assert r.status_code == 403 and code(r) == "test_student_forbidden"


async def test_catalog_exam_filter(db, api):
    _, c = catalog_world(db)
    s = make_user(db)

    async def ids(exam, limit=25):
        out, cursor = [], None
        while True:
            params = {"exam": exam, "limit": limit, **({"cursor": cursor} if cursor else {})}
            r = await api.call(s, "GET", "/catalog/courses", params=params)
            assert r.status_code == 200, r.text
            out += [x["id"] for x in r.json()["items"]]
            cursor = r.json()["next_cursor"]
            if not cursor:
                return out

    ort = [str(c[k].id) for k in ("teacher", "code", "ky", "ru", "math", "physics")]
    got = await ids("ort")
    # main courses first (the teacher's ORT-family course is newest), then subject courses, newest first in each
    assert got == ort  # math was published after physics
    for limit in (1, 2, 3):
        assert await ids("ort", limit) == got, limit  # pages lose and repeat nothing across the group boundary
    assert await ids("nct") == [str(c["nct"].id)]
    other = await ids("other")
    assert str(c["plain"].id) in other and not (set(other) & set(got))
    page = (await api.call(s, "GET", "/catalog/courses", params={"exam": "ort"})).json()["items"]
    assert {x["id"]: (x["exam_family"], x["subject"]) for x in page}[str(c["math"].id)] == ("ort", "math")
    # without the filter the catalog is unchanged: newest first over every family
    plain = (await api.call(s, "GET", "/catalog/courses", params={"limit": 50})).json()["items"]
    stamps = [x["id"] for x in plain]
    assert stamps.index(str(c["teacher"].id)) < stamps.index(str(c["nct"].id)) < stamps.index(str(c["ru"].id))
    assert (await api.call(s, "GET", "/catalog/courses", params={"exam": "sat"})).status_code == 422
    bad = await api.call(s, "GET", "/catalog/courses", params={"exam": "ort", "cursor": "e30"})
    assert bad.status_code == 422
