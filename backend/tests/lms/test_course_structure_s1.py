"""Phase 8a S1 smoke checks (PHASE_8A_DESIGN 2, 5.5, 7, 9): the new models accept a full structure written by the
`modules_support` factories (and the isolation reset clears it on SQLite and PostgreSQL), courses keep today's home
layout, the ORT template locks the home kind and gating, `progress.record` is student-only, the shapes validate and the
S1 gate stubs behave as documented until S2 fills them."""
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.authz import A, decide
from app.lms.courses.models import Course
from app.lms.modules import gate
from app.lms.modules.models import ItemProgress, ItemRequirementStatus, ModuleProgress
from app.lms.modules.schemas import ItemIn, ModuleUpdateIn, RequirementIn
from app.lms.templates.base import ALL_LOCK_FIELDS, LOCK_GATING, LOCK_HOME_KIND
from app.lms.templates.general import GENERAL
from app.lms.templates.ort import ORT
from tests.lms.modules_support import (
    add_prerequisite, make_announcement, make_course_file, make_item, make_module, make_page, published_quiz,
    record_fact, structure_world,
)
from tests.lms.s3_support import db  # noqa: F401


def test_full_structure_rows(db):
    w = structure_world(db)
    assert db.get(Course, w.course.id).home_kind == "assignments" and w.course.home_page_id is None
    page = make_page(db, w.course, w.O)
    make_page(db, w.course, w.O, language="ru", group=page)
    pdf = make_course_file(db, w.course, w.O, folder="Lectures/Week 1")
    quiz = published_quiz(db, w.course, w.O)
    m1 = make_module(db, w.course, w.O)
    m2 = make_module(db, w.course, w.O, sequential=True, completion_mode="any")
    add_prerequisite(db, m2, m1)
    make_item(db, m1)
    viewed = make_item(db, m1, page, requirement=("view",))
    make_item(db, m1, pdf, requirement=("mark_done",))
    graded = make_item(db, m2, quiz, requirement=("min_percent", 80))
    make_item(db, m2, "https://example.org/reading", indent=1)
    make_announcement(db, w.course, w.O, pinned=True)
    record_fact(db, w.enr, viewed)
    record_fact(db, w.enr, viewed, "marked_done")
    db.add(ModuleProgress(enrollment_id=w.enr.id, module_id=m1.id, state="started", evaluated_rules_version=1,
                          evaluated_at=page.created_at))
    db.add(ItemRequirementStatus(enrollment_id=w.enr.id, item_id=graded.id, met=True))
    w.course.home_kind, w.course.home_page_id = "page", page.id
    db.commit()
    assert db.execute(select(func.count()).select_from(ItemProgress)).scalar() == 2
    assert [m1.position, m2.position] == [1, 2] and graded.position == 1 and m2.rules_version == 1


def test_course_out_defaults(db):
    from app.lms.courses.schemas import CourseStaffOut, course_student_out

    w = structure_world(db)
    out = course_student_out(w.course, w.enr, w.O)
    assert out.home_kind == "assignments" and out.home_page_id is None
    assert out.features.model_dump() == {"modules": False, "files": False, "announcements": False}
    assert {"home_kind", "home_page_id", "features"} <= set(CourseStaffOut.model_fields)


def test_templates_and_authz():
    assert {LOCK_HOME_KIND, LOCK_GATING} <= ALL_LOCK_FIELDS
    assert ORT.locks(LOCK_HOME_KIND) and ORT.locks(LOCK_GATING) and ORT.default_home_kind == "assignments"
    assert not GENERAL.locks(LOCK_GATING) and GENERAL.default_home_kind == "modules"
    assert ORT.default_structure is None and GENERAL.default_structure is None
    assert decide(role="student", course_status="published", action=A.PROGRESS_RECORD)
    assert not decide(role="student", course_status="draft", action=A.PROGRESS_RECORD)
    assert not decide(role="student", course_status="concluded", action=A.PROGRESS_RECORD)
    for role in ("teacher", "assistant"):
        assert not decide(role=role, course_status="published", action=A.PROGRESS_RECORD)
    assert not decide(role=None, course_status="published", action=A.PROGRESS_RECORD, org_admin=True)
    assert not decide(role=None, course_status="published", action=A.PROGRESS_RECORD, is_platform_admin=True)


def test_shapes():
    assert ItemIn(kind="header").kind == "header"
    assert RequirementIn(type="min_percent", threshold=80).threshold == 80
    bad = [
        lambda: ItemIn(kind="page"),
        lambda: ItemIn(kind="url", url="https://x.org", page_id="00000000-0000-4000-8000-000000000001"),
        lambda: ItemIn(kind="header", requirement={"type": "view"}),
        lambda: ItemIn(kind="header", indent=4),
        lambda: RequirementIn(type="min_score"),
        lambda: RequirementIn(type="view", threshold=1),
        lambda: RequirementIn(type="min_percent", threshold=101),
        lambda: ModuleUpdateIn(title=None),
    ]
    for fn in bad:
        with pytest.raises(ValidationError):
            fn()


def test_gate_stubs():
    assert gate.touch_assignment(None, []) == 0 and gate.touch_pages(None, []) == 0 and gate.touch_files(None, []) == 0
    with pytest.raises(NotImplementedError):
        gate.require_access(None, None, None)
    assert gate.ModuleLocked("x").status_code == 423 and gate.ModuleLocked("x").code == "module_locked"
