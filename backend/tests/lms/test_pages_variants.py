"""Phase 8a S3: page language variants (PHASE_8A_DESIGN 2.2, 5.1): translation groups, one live page per group and
language, the student resolution order (`?lang`, enrollment content language, course default, the page itself) and
the module gate on the resolved variant."""
from __future__ import annotations

from app.lms.pages.models import Page
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage  # noqa: F401
from tests.lms.modules_support import C, make_page, structure_world
from tests.lms.structure_content_support import gate_calls, open_gate  # noqa: F401


def P(w, page) -> str:
    return f"{C(w)}/pages/{page.id}"


def tri(db, w):
    w.course.languages, w.course.default_language = ["en", "ru", "ky"], "en"
    db.commit()
    return w


async def test_add_variant_and_unique_language(api, db):
    w = tri(db, structure_world(db))
    en = (await api.call(w.O, "POST", f"{C(w)}/pages", json={"title": "Intro", "language": "en"})).json()
    res = await api.call(w.O, "POST", f"{C(w)}/pages", json={"title": "Введение", "language": "ru",
                                                              "translation_group_id": en["translation_group_id"]})
    assert res.status_code == 201, res.text
    ru = res.json()
    assert ru["translation_group_id"] == en["id"]
    assert [(v["language"], v["title"]) for v in ru["variants"]] == [("en", "Intro")]
    dup = await api.call(w.O, "POST", f"{C(w)}/pages", json={"title": "Again", "language": "ru",
                                                              "translation_group_id": en["id"]})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "page_variant_exists"
    staff = (await api.call(w.O, "GET", f"{C(w)}/pages/{en['id']}")).json()
    assert [v["language"] for v in staff["variants"]] == ["ru"]


async def test_deleted_variant_frees_language_and_restore_conflicts(api, db):
    w = tri(db, structure_world(db))
    en = make_page(db, w.course, w.O)
    ru = make_page(db, w.course, w.O, language="ru", group=en)
    assert (await api.call(w.O, "DELETE", P(w, ru))).status_code == 204
    res = await api.call(w.O, "POST", f"{C(w)}/pages", json={"title": "RU 2", "language": "ru",
                                                              "translation_group_id": str(en.id)})
    assert res.status_code == 201
    res = await api.call(w.O, "POST", P(w, ru) + "/restore")
    assert res.status_code == 409 and res.json()["error"]["code"] == "page_variant_exists"


async def test_group_must_have_a_live_page(api, db):
    w = tri(db, structure_world(db))
    en = make_page(db, w.course, w.O)
    en.soft_delete(w.O.id)
    db.commit()
    res = await api.call(w.O, "POST", f"{C(w)}/pages", json={"title": "x", "language": "ru",
                                                              "translation_group_id": str(en.id)})
    assert res.status_code == 404 and res.json()["error"]["code"] == "page_not_found"


async def test_resolution_order(api, db, gate_calls):
    w = tri(db, structure_world(db))
    en = make_page(db, w.course, w.O, title="EN")
    ru = make_page(db, w.course, w.O, title="RU", language="ru", group=en)
    ky = make_page(db, w.course, w.O, title="KY", language="ky", group=en, published=False)

    async def title(user, page, **params):
        res = await api.call(user, "GET", P(w, page), params=params or None)
        assert res.status_code == 200, res.text
        return res.json()

    # no content language: course default (en), whichever variant id was requested
    assert (await title(w.S, ru))["title"] == "EN"
    w.enr.content_language = "ru"
    db.commit()
    b = await title(w.S, en)
    assert b["title"] == "RU" and [v["language"] for v in b["variants"]] == ["en"]  # unpublished ky not listed
    # explicit ?lang wins (variant switcher)
    assert (await title(w.S, en, lang="en"))["title"] == "EN"
    # unpublished variant is never served: falls back to the course default
    w.enr.content_language = "ky"
    db.commit()
    assert (await title(w.S, ru))["title"] == "EN"
    assert (await api.call(w.S, "GET", P(w, ky))).status_code == 404
    # course default missing in the group: the requested page itself
    en.published = False
    db.commit()
    assert (await title(w.S, ru, lang="ky"))["title"] == "RU"
    # gate: requested page and the resolved variant when different
    gate_calls.clear()
    en.published = True
    db.commit()
    await title(w.S, en, lang="ru")
    assert [c["page"] for c in gate_calls] == [en.id, ru.id]


async def test_org_admin_resolves_course_default_without_gate(api, db, gate_calls):
    w = tri(db, structure_world(db))
    en = make_page(db, w.course, w.O, title="EN")
    ru = make_page(db, w.course, w.O, title="RU", language="ru", group=en)
    res = await api.call(w.OA, "GET", P(w, ru))
    assert res.status_code == 200 and res.json()["title"] == "EN" and gate_calls == []


async def test_student_list_groups_variants_adjacent(api, db):
    w = tri(db, structure_world(db))
    a = make_page(db, w.course, w.O, title="A-en")
    b = make_page(db, w.course, w.O, title="B-en")
    make_page(db, w.course, w.O, title="A-ru", language="ru", group=a)
    make_page(db, w.course, w.O, title="B-ru", language="ru", group=b)
    items = (await api.call(w.S, "GET", f"{C(w)}/pages")).json()["items"]
    groups = [i["translation_group_id"] for i in items]
    assert len(items) == 4 and groups == sorted(groups)


async def test_variants_rows_share_group(db, api):
    w = tri(db, structure_world(db))
    en = make_page(db, w.course, w.O)
    res = await api.call(w.T, "POST", f"{C(w)}/pages", json={"title": "KY", "language": "ky",
                                                              "translation_group_id": str(en.id)})
    assert res.status_code == 201
    db.expire_all()
    rows = db.query(Page).filter(Page.translation_group_id == en.id).all()
    assert sorted(p.language for p in rows) == ["en", "ky"]
