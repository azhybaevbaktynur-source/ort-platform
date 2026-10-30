"""Phase 8c S1: `POST _C/modules/{mid}/duplicate` (PHASE_8C_DESIGN 7, P8C-9).

A draft copy right after the original: title + " (copy)" in every language, `unlock_at`/`sequential`/`completion_mode`
copied, live items and requirements copied with the same targets, prerequisites not copied; caps (422
`limit_reached`); the modules moved down get `rules_version += 1`; staff only (students and org admins 403, outsiders
404); concluded courses refuse it like every content write. PG race with a reorder: test_pg_concurrency_modules.py."""
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.lms.core.models import utcnow
from app.lms.modules import ids
from app.lms.modules.models import CourseModule, ItemCompletionRequirement, ModuleItem, ModulePrerequisite
from tests.lms.factories import make_user, set_status
from tests.lms.modules_support import (
    C, M, add_prerequisite, make_assignment, make_course_file, make_item, make_module, make_page, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _items(db, module_id):
    db.expire_all()
    return list(db.execute(select(ModuleItem).where(ModuleItem.module_id == module_id,
                                                    ModuleItem.deleted_at.is_(None))
                           .order_by(ModuleItem.position)).scalars())


def _rv(db, mid) -> int:
    db.expire_all()
    return db.get(CourseModule, mid).rules_version


async def test_copy_semantics(db, api):
    w = structure_world(db)
    first = make_module(db, w.course, w.O, title={"en": "Intro"})
    unlock = utcnow() + timedelta(days=3)
    src = make_module(db, w.course, w.O, title={"en": "Week 1", "ru": "Неделя 1", "ky": "1-апта"},
                      unlock_at=unlock, sequential=True, completion_mode="any")
    after = make_module(db, w.course, w.O, title={"en": "Week 2"})
    add_prerequisite(db, src, first)
    page, f = make_page(db, w.course, w.O), make_course_file(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O)
    make_item(db, src, None, title_override={"en": "Read first"})
    make_item(db, src, page, indent=1, requirement=("view", None))
    make_item(db, src, a, requirement=("min_score", 5), published=False)
    gone = make_item(db, src, "https://example.org")
    gone.deleted_at = utcnow()
    db.commit()
    make_item(db, src, f)
    rv_after = _rv(db, after.id)

    r = await api.call(w.T, "POST", f"{M(w, src)}/duplicate")  # assistants may
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["title"] == {"en": "Week 1 (copy)", "ru": "Неделя 1 (копия)", "ky": "1-апта (көчүрмө)"}
    assert out["published"] is False and out["sequential"] is True and out["completion_mode"] == "any"
    assert out["unlock_at"] and out["position"] == 3 and out["prerequisites"] == [] and out["rules_version"] == 1
    assert [i["kind"] for i in out["items"]] == ["header", "page", "assignment", "file"]
    assert [i["position"] for i in out["items"]] == [1, 2, 3, 4]
    assert out["items"][0]["title_override"] == {"en": "Read first"} and out["items"][1]["indent"] == 1
    assert out["items"][1]["page_id"] == str(page.id) and out["items"][2]["assignment_id"] == str(a.id)
    assert out["items"][2]["published"] is False
    assert out["items"][1]["requirement"] == {"type": "view", "threshold": None}
    assert out["items"][2]["requirement"] == {"type": "min_score", "threshold": 5.0}
    # positions: original 2, copy 3, the next module moved to 4 (rules_version bumped)
    db.expire_all()
    assert db.get(CourseModule, src.id).position == 2 and db.get(CourseModule, after.id).position == 4
    assert _rv(db, after.id) == rv_after + 1
    # the original is untouched; requirements are new rows; prerequisites stay on the original only
    assert len(_items(db, src.id)) == 4
    copy_id = uuid.UUID(out["id"])
    assert len(db.execute(select(ItemCompletionRequirement).join(ModuleItem, ModuleItem.id ==
                                                                 ItemCompletionRequirement.item_id)
                          .where(ModuleItem.module_id == copy_id)).all()) == 2
    assert db.execute(select(ModulePrerequisite).where(ModulePrerequisite.module_id == copy_id)).first() is None
    outline = (await api.call(w.O, "GET", f"{C(w)}/modules")).json()["modules"]
    assert [m["title"]["en"] for m in outline] == ["Intro", "Week 1", "Week 1 (copy)", "Week 2"]


async def test_title_length_and_caps(db, api, monkeypatch):
    w = structure_world(db)
    long = "x" * ids.MODULE_TITLE_MAX
    m = make_module(db, w.course, w.O, title={"en": long})
    r = await api.call(w.O, "POST", f"{M(w, m)}/duplicate")
    assert r.status_code == 201 and len(r.json()["title"]["en"]) == ids.MODULE_TITLE_MAX
    assert r.json()["title"]["en"].endswith(" (copy)")
    monkeypatch.setattr(ids, "MODULES_PER_COURSE_MAX", 2)
    r = await api.call(w.O, "POST", f"{M(w, m)}/duplicate")
    assert r.status_code == 422 and r.json()["error"]["code"] == "limit_reached"


async def test_duplicate_access_matrix(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    for user in (w.S, w.OA):
        assert (await api.call(user, "POST", f"{M(w, m)}/duplicate")).status_code == 403
    assert (await api.call(w.X, "POST", f"{M(w, m)}/duplicate")).status_code == 404
    admin = make_user(db, platform_admin=True)
    assert (await api.call(admin, "POST", f"{M(w, m)}/duplicate")).status_code == 404
    other = structure_world(db)
    om = make_module(db, other.course, other.O)
    assert (await api.call(w.O, "POST", f"{C(w)}/modules/{om.id}/duplicate")).status_code == 404
    assert (await api.call(w.O, "POST", f"{C(w)}/modules/{uuid.uuid4()}/duplicate")).status_code == 404
    m.deleted_at = utcnow()
    db.commit()
    assert (await api.call(w.O, "POST", f"{M(w, m)}/duplicate")).status_code == 404
    m2 = make_module(db, w.course, w.O)
    set_status(db, w.course, "concluded")
    assert (await api.call(w.O, "POST", f"{M(w, m2)}/duplicate")).status_code == 403
