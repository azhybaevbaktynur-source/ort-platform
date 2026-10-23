"""Scheme library services (PHASE_4_DESIGN 7.7, service part; 3.2; P4-4, P4-5, P4-6)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.db.session import SessionLocal
from app.lms.core.errors import Conflict, Forbidden, NotFound, RateLimited, ValidationFailed
from app.lms.grading import schemes as svc
from app.lms.grading import seeds
from app.lms.grading.models import (
    GradingScheme, GradingSchemeVersion, ImmutableGradingSchemeVersionError,
)
from app.lms.grading.registry import apply
from app.lms.grading.schemes import SchemeCreateIn
from tests.lms.factories import enroll, make_course, make_scheme, make_user


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def ctx_for(db, user):
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))


def create(db, user, type_="percent", params=None, title=None):
    return svc.create_scheme(db, ctx_for(db, user), SchemeCreateIn(
        title=title or {"en": "Mine"}, type=type_, params=params if params is not None else {}))


@pytest.fixture
def teachers(db):
    return make_user(db, teacher_status="approved"), make_user(db, teacher_status="approved")


# ------------------------------------------------------------------ seeds

def test_system_schemes_seeded_and_idempotent(db):
    rows = db.execute(select(GradingScheme).where(GradingScheme.owner_user_id.is_(None))).scalars().all()
    assert {r.key for r in rows} == {"ort_main", "ort_subject", "percent", "pass_fail"}
    assert {r.id for r in rows} == {s[0] for s in seeds.SYSTEM_SCHEMES}
    for scheme_id, version_id, key, type_, _, params in seeds.SYSTEM_SCHEMES:
        s = db.get(GradingScheme, scheme_id)
        assert s.current_version_id == version_id and s.type == type_ and s.last_version_no == 1
        v = db.get(GradingSchemeVersion, version_id)
        assert v.version_no == 1 and v.params == svc.validate_params(type_, params)
        assert v.params_hash == svc.params_hash(v.params)
    seeds.ensure_system_schemes(db)
    seeds.ensure_system_schemes(db)
    assert db.execute(select(func.count()).select_from(GradingSchemeVersion)).scalar_one() == 4
    assert str(seeds.ORT_MAIN_SCHEME_ID) == "00000000-0000-4000-8000-000000000401"
    assert str(seeds.PASS_FAIL_V1_ID) == "00000000-0000-4000-8000-000000000408"


def test_seeded_simple_schemes(db):
    pct = svc.get_version_data(db, seeds.PERCENT_V1_ID)
    assert apply(pct, 2, 3).display_value == Decimal("66.67")
    pf = svc.get_version_data(db, seeds.PASS_FAIL_V1_ID)
    assert apply(pf, 6, 10).label == "pass" and apply(pf, Decimal("5.99"), 10).label == "fail"


# ------------------------------------------------------------------ create / version / title / delete / restore

def test_create_scheme_sets_version_1(db, teachers):
    t, _ = teachers
    s = create(db, t, "bands", {"bands": [{"key": "ok", "min_percent": 0, "label": {"en": "OK"}, "passed": True}]})
    assert s.owner_user_id == t.id and s.key is None and s.last_version_no == 1
    v = db.get(GradingSchemeVersion, s.current_version_id)
    assert v.version_no == 1 and v.type == "bands" and v.created_by_id == t.id
    assert (v.scale_min, v.scale_max) == (Decimal("0.00"), Decimal("100.00"))


def test_create_requires_approved_teacher_and_valid_params(db, teachers):
    student = make_user(db)
    with pytest.raises(Forbidden) as ei:
        create(db, student)
    assert ei.value.code == "teacher_not_approved"
    with pytest.raises(ValidationFailed) as ei:
        create(db, teachers[0], "pass_fail", {})
    assert ei.value.code == "scheme_params_invalid"


def test_add_version_increments_and_rejects_unchanged(db, teachers):
    t, _ = teachers
    s = create(db, t, "pass_fail", {"pass_threshold_percent": 50})
    first = s.current_version_id
    with pytest.raises(Conflict) as ei:
        svc.add_version(db, ctx_for(db, t), s.id, {"pass_threshold_percent": 50.0, "schema": 1})
    assert ei.value.code == "version_unchanged"
    v2 = svc.add_version(db, ctx_for(db, t), s.id, {"pass_threshold_percent": 70})
    db.refresh(s)
    assert v2.version_no == 2 and s.current_version_id == v2.id and s.last_version_no == 2
    assert db.get(GradingSchemeVersion, first).params["pass_threshold_percent"] == 50.0  # old version kept
    with pytest.raises(ValidationFailed):
        svc.add_version(db, ctx_for(db, t), s.id, {"bands": []})


def test_title_delete_restore(db, teachers):
    t, _ = teachers
    s = create(db, t)
    svc.update_title(db, ctx_for(db, t), s.id, {"en": "Renamed", "ru": "Новое"})
    assert db.get(GradingScheme, s.id).title == {"en": "Renamed", "ru": "Новое"}
    svc.soft_delete(db, ctx_for(db, t), s.id)
    with pytest.raises(NotFound) as ei:
        svc.load_scheme(db, ctx_for(db, t), s.id)
    assert ei.value.code == "grading_scheme_not_found"
    assert s.id not in {x.id for x in svc.list_schemes(db, ctx_for(db, t), cursor=None, limit=100).items}
    restored = svc.restore(db, ctx_for(db, t), s.id)
    assert restored.deleted_at is None
    with pytest.raises(Conflict):
        svc.restore(db, ctx_for(db, t), s.id)


def test_system_and_foreign_schemes_are_read_only(db, teachers):
    ta, tb = teachers
    theirs = create(db, tb)
    for sid in (seeds.ORT_MAIN_SCHEME_ID, theirs.id):
        for call in (lambda: svc.add_version(db, ctx_for(db, ta), sid, {"pass_threshold_percent": 1}),
                     lambda: svc.update_title(db, ctx_for(db, ta), sid, {"en": "x"}),
                     lambda: svc.soft_delete(db, ctx_for(db, ta), sid),
                     lambda: svc.restore(db, ctx_for(db, ta), sid)):
            with pytest.raises(NotFound) as ei:
                call()
            assert ei.value.code == "grading_scheme_not_found"
    # system: readable by anyone; another teacher's: not even readable
    assert svc.load_scheme(db, ctx_for(db, ta), seeds.ORT_MAIN_SCHEME_ID).key == "ort_main"
    with pytest.raises(NotFound):
        svc.load_scheme(db, ctx_for(db, ta), theirs.id)
    with pytest.raises(NotFound):
        svc.load_scheme(db, ctx_for(db, ta), uuid.uuid4())


def test_list_is_system_union_mine(db, teachers):
    ta, tb = teachers
    mine, theirs = create(db, ta), create(db, tb)
    ids = [x.id for x in svc.list_schemes(db, ctx_for(db, ta), cursor=None, limit=100).items]
    assert set(ids) == {s[0] for s in seeds.SYSTEM_SCHEMES} | {mine.id}
    assert theirs.id not in ids
    only_mine = svc.list_schemes(db, ctx_for(db, ta), cursor=None, limit=100, include_system=False)
    assert [x.id for x in only_mine.items] == [mine.id]
    page = svc.list_schemes(db, ctx_for(db, ta), cursor=None, limit=2)
    rest = svc.list_schemes(db, ctx_for(db, ta), cursor=page.next_cursor, limit=100)
    assert [x.id for x in page.items + rest.items] == ids


def test_versions_are_immutable(db):
    v = db.get(GradingSchemeVersion, seeds.ORT_MAIN_V1_ID)
    v.params = {"schema": 1}
    with pytest.raises(ImmutableGradingSchemeVersionError):
        db.flush()
    db.rollback()
    v = db.get(GradingSchemeVersion, seeds.ORT_MAIN_V1_ID)
    db.delete(v)
    with pytest.raises(ImmutableGradingSchemeVersionError):
        db.flush()
    db.rollback()


def test_write_rate_limit(db, teachers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SCHEME_WRITE_RATE_PER_HOUR", 2)
    t, _ = teachers
    s = create(db, t)
    svc.update_title(db, ctx_for(db, t), s.id, {"en": "a"})
    with pytest.raises(RateLimited):
        svc.update_title(db, ctx_for(db, t), s.id, {"en": "b"})


# ------------------------------------------------------------------ usability in a course (P4-4)

def test_load_usable_version(db, teachers):
    ta, tb = teachers
    assistant = make_user(db, teacher_status="approved")
    course = make_course(db, ta)
    other_course = make_course(db, tb)
    enroll(db, course, assistant, role="assistant")
    mine = create(db, ta)
    theirs = create(db, tb)
    asst = create(db, assistant)
    ctx = ctx_for(db, ta)
    assert svc.load_usable_version(db, ctx, course, seeds.ORT_MAIN_V1_ID).id == seeds.ORT_MAIN_V1_ID
    assert svc.load_usable_version(db, ctx, course, mine.current_version_id).id == mine.current_version_id
    # owned by an active assistant of the course: usable there, not in another course
    assert svc.load_usable_version(db, ctx, course, asst.current_version_id)
    for course_, vid in ((course, theirs.current_version_id), (other_course, asst.current_version_id),
                         (course, uuid.uuid4())):
        with pytest.raises(NotFound) as ei:
            svc.load_usable_version(db, ctx, course_, vid)
        assert ei.value.code == "scheme_version_not_found"
    # older versions stay usable; a deleted scheme is not
    old = mine.current_version_id
    svc.add_version(db, ctx, mine.id, {"rounding": {"mode": "floor", "decimals": 0}})
    assert svc.load_usable_version(db, ctx, course, old).id == old
    svc.soft_delete(db, ctx, mine.id)
    with pytest.raises(NotFound):
        svc.load_usable_version(db, ctx, course, old)


def test_get_version_data_cache(db, teachers, monkeypatch):
    from app.core.config import settings

    t, _ = teachers
    s = make_scheme(db, t, "percent", {})
    data = svc.get_version_data(db, s.current_version_id)
    assert data.type == "percent" and data.scheme_id == s.id
    assert svc.get_version_data(db, s.current_version_id) is data
    monkeypatch.setattr(settings, "GRADING_VERSION_CACHE_SIZE", 1)
    svc.get_version_data(db, seeds.ORT_MAIN_V1_ID)
    assert svc.get_version_data(db, s.current_version_id) is not data  # evicted (LRU)
    svc.reset_version_cache()
    with pytest.raises(NotFound) as ei:
        svc.get_version_data(db, uuid.uuid4())
    assert ei.value.code == "scheme_version_not_found"
