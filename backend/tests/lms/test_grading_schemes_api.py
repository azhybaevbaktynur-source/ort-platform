"""Scheme library API (PHASE_4_DESIGN 7.7 API part, 7.8 scheme part): contracts, ownership, matrix, limits."""
from __future__ import annotations

import uuid

import pytest

from app.lms.grading import seeds
from app.lms.grading.models import GradingScheme
from tests.lms.content_support import world
from tests.lms.factories import make_assessment, make_scheme, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

S = "/grading-schemes"
PF = {"pass_threshold_percent": 50}


def code(res):
    return res.json()["error"]["code"]


async def create(api, user, type_="percent", params=None, title=None):
    res = await api.call(user, "POST", S, json={"title": title or {"en": "Mine"}, "type": type_,
                                                "params": params if params is not None else {}})
    assert res.status_code == 201, res.text
    return res.json()


async def test_create_get_list_contract(db, api):
    w = world(db)
    out = await create(api, w.O, "pass_fail", PF)
    assert out["is_mine"] is True and out["is_system"] is False and out["key"] is None
    assert out["deleted_at"] is None and out["type"] == "pass_fail"
    cv = out["current_version"]
    assert cv["version_no"] == 1 and set(cv) == {"id", "version_no", "scale_min", "scale_max", "created_at"}
    (v,) = out["versions"]
    assert v["id"] == cv["id"] and v["in_use_count"] == 0
    assert set(v) == {"id", "version_no", "type", "scale_min", "scale_max", "params", "labels", "created_at",
                      "in_use_count"}
    got = await api.call(w.O, "GET", f"{S}/{out['id']}")
    assert got.status_code == 200 and got.json() == out
    page = (await api.call(w.O, "GET", S)).json()
    ids = {i["id"] for i in page["items"]}
    assert out["id"] in ids and str(seeds.ORT_MAIN_SCHEME_ID) in ids
    assert set(page) == {"items", "next_cursor"}
    sysitem = next(i for i in page["items"] if i["id"] == str(seeds.ORT_MAIN_SCHEME_ID))
    assert sysitem["is_system"] is True and sysitem["is_mine"] is False and sysitem["key"]
    assert sysitem["current_version"]["scale_min"] == 60.0 and sysitem["current_version"]["scale_max"] == 245.0


async def test_list_is_system_union_mine_and_include_system(db, api):
    w = world(db)
    mine = await create(api, w.O)
    other = await create(api, w.T)
    items = (await api.call(w.O, "GET", S)).json()["items"]
    ids = {i["id"] for i in items}
    assert mine["id"] in ids and other["id"] not in ids
    assert any(i["is_system"] for i in items)
    only = (await api.call(w.O, "GET", S, params={"include_system": "false"})).json()["items"]
    assert [i["id"] for i in only] == [mine["id"]]


async def test_list_pagination(db, api):
    w = world(db)
    for _ in range(3):
        await create(api, w.O)
    p1 = (await api.call(w.O, "GET", S, params={"include_system": "false", "limit": 2})).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = (await api.call(w.O, "GET", S, params={"include_system": "false", "limit": 2,
                                                 "cursor": p1["next_cursor"]})).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert not {i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]}


async def test_versions_title_delete_restore(db, api):
    w = world(db)
    s = await create(api, w.O, "pass_fail", PF)
    same = await api.call(w.O, "POST", f"{S}/{s['id']}/versions", json={"params": PF})
    assert same.status_code == 409 and code(same) == "version_unchanged"
    bad = await api.call(w.O, "POST", f"{S}/{s['id']}/versions", json={"params": {"pass_threshold_percent": 500}})
    assert bad.status_code == 422 and code(bad) == "scheme_params_invalid"
    v2 = await api.call(w.O, "POST", f"{S}/{s['id']}/versions", json={"params": {"pass_threshold_percent": 60}})
    assert v2.status_code == 201 and v2.json()["version_no"] == 2
    got = (await api.call(w.O, "GET", f"{S}/{s['id']}")).json()
    assert [v["version_no"] for v in got["versions"]] == [2, 1]
    assert got["current_version"]["id"] == v2.json()["id"]

    t = await api.call(w.O, "PATCH", f"{S}/{s['id']}", json={"title": {"en": "Renamed"}})
    assert t.status_code == 200 and t.json()["title"] == {"en": "Renamed"}

    nd = await api.call(w.O, "POST", f"{S}/{s['id']}/restore")
    assert nd.status_code == 409 and code(nd) == "not_deleted"
    d = await api.call(w.O, "DELETE", f"{S}/{s['id']}")
    assert d.status_code == 204 and d.content == b""
    assert (await api.call(w.O, "GET", f"{S}/{s['id']}")).status_code == 404
    assert s["id"] not in {i["id"] for i in (await api.call(w.O, "GET", S)).json()["items"]}
    r = await api.call(w.O, "POST", f"{S}/{s['id']}/restore")
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    assert (await api.call(w.O, "GET", f"{S}/{s['id']}")).status_code == 200


async def test_create_validation_errors(db, api):
    w = world(db)
    bad = await api.call(w.O, "POST", S, json={"title": {"en": "x"}, "type": "pass_fail",
                                               "params": {"pass_threshold_percent": 101}})
    assert bad.status_code == 422 and code(bad) == "scheme_params_invalid"
    missing = await api.call(w.O, "POST", S, json={"type": "percent", "params": {}})
    assert missing.status_code == 422 and code(missing) == "validation_failed"
    extra = await api.call(w.O, "POST", S, json={"title": {"en": "x"}, "type": "percent", "params": {},
                                                 "owner_user_id": "x"})
    assert extra.status_code == 422


async def test_in_use_count(db, api):
    w = world(db)
    s = await create(api, w.O, "pass_fail", PF)
    a = make_assessment(db, w.course, w.O)
    a.grading_scheme_version_id = uuid.UUID(s["current_version"]["id"])
    db.commit()
    got = (await api.call(w.O, "GET", f"{S}/{s['id']}")).json()
    assert got["versions"][0]["in_use_count"] == 1


async def test_system_and_foreign_schemes_are_read_only_and_hidden(db, api):
    w = world(db)
    mine_t = await create(api, w.T)
    sid = str(seeds.ORT_MAIN_SCHEME_ID)
    assert (await api.call(w.O, "GET", f"{S}/{sid}")).status_code == 200
    for method, path, body in [
        ("PATCH", f"{S}/{sid}", {"title": {"en": "x"}}), ("DELETE", f"{S}/{sid}", None),
        ("POST", f"{S}/{sid}/restore", None), ("POST", f"{S}/{sid}/versions", {"params": {}}),
        ("GET", f"{S}/{mine_t['id']}", None), ("PATCH", f"{S}/{mine_t['id']}", {"title": {"en": "x"}}),
        ("DELETE", f"{S}/{mine_t['id']}", None), ("POST", f"{S}/{mine_t['id']}/restore", None),
        ("POST", f"{S}/{mine_t['id']}/versions", {"params": PF}),
    ]:
        res = await api.call(w.O, method, path, json=body)
        assert res.status_code == 404 and code(res) == "grading_scheme_not_found", (method, path)
    unknown = await api.call(w.O, "GET", f"{S}/{uuid.uuid4()}")
    assert unknown.status_code == 404 and code(unknown) == "grading_scheme_not_found"


async def test_preview(db, api):
    w = world(db)
    res = await api.call(w.S, "POST", f"{S}/preview", json={
        "type": "pass_fail", "params": PF, "possible": "10", "raws": ["0", "5", "10"]})
    assert res.status_code == 200, res.text
    rows = res.json()["rows"]
    assert [r["raw"] for r in rows] == [0.0, 5.0, 10.0]
    assert [r["passed"] for r in rows] == [False, True, True]
    assert set(rows[0]) == {"raw", "display_value", "label", "percentile", "passed", "thresholds"}
    # system schemes can be previewed with their own params
    bad = await api.call(w.S, "POST", f"{S}/preview", json={
        "type": "pass_fail", "params": {"pass_threshold_percent": -1}, "possible": "10", "raws": ["1"]})
    assert bad.status_code == 422 and code(bad) == "scheme_params_invalid"


async def test_preview_caps_and_shape(db, api):
    w = world(db)
    body = {"type": "percent", "params": {}, "possible": "100"}
    ok = await api.call(w.S, "POST", f"{S}/preview", json={**body, "raws": ["1"] * 1001})
    assert ok.status_code == 200 and len(ok.json()["rows"]) == 1001
    big = await api.call(w.S, "POST", f"{S}/preview", json={**body, "raws": ["1"] * 1002})
    assert big.status_code == 422 and code(big) == "too_many_rows"
    nostep = await api.call(w.S, "POST", f"{S}/preview", json={**body, "raws": ["1"], "step": "1"})
    assert nostep.status_code == 422
    noraws = await api.call(w.S, "POST", f"{S}/preview", json=body)
    assert noraws.status_code == 422


async def test_preview_rate_limit(db, api, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SCHEME_PREVIEW_RATE_PER_MIN", 2)
    w = world(db)
    body = {"type": "percent", "params": {}, "possible": "100", "raws": ["1"]}
    for _ in range(2):
        assert (await api.call(w.S, "POST", f"{S}/preview", json=body)).status_code == 200
    third = await api.call(w.S, "POST", f"{S}/preview", json=body)
    assert third.status_code == 429 and code(third) == "rate_limited"


async def test_write_rate_limit_is_enforced_by_service(db, api, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SCHEME_WRITE_RATE_PER_HOUR", 2)
    w = world(db)
    await create(api, w.O)
    await create(api, w.O)
    res = await api.call(w.O, "POST", S, json={"title": {"en": "x"}, "type": "percent", "params": {}})
    assert res.status_code == 429


# ------------------------------------------------------------------ matrix (7.8 scheme part)

async def test_matrix_unauthenticated_and_non_teacher(db, api):
    w = world(db)
    mine = await create(api, w.O)
    base = f"{S}/{mine['id']}"
    reqs = [("GET", S, None), ("POST", S, {"title": {"en": "x"}, "type": "percent", "params": {}}),
            ("POST", f"{S}/preview", {"type": "percent", "params": {}, "possible": "1", "raws": ["1"]}),
            ("GET", base, None), ("PATCH", base, {"title": {"en": "x"}}), ("DELETE", base, None),
            ("POST", f"{base}/restore", None), ("POST", f"{base}/versions", {"params": PF})]
    for method, path, body in reqs:
        res = await api.call(None, method, path, json=body)
        assert res.status_code == 401, (method, path)
    writes = {("POST", S), ("PATCH", base), ("DELETE", base), ("POST", f"{base}/restore"),
              ("POST", f"{base}/versions")}
    for actor in (w.S, w.AS, w.X):  # approved-teacher check lives in the write services
        for method, path, body in reqs:
            res = await api.call(actor, method, path, json=body)
            if (method, path) in writes:
                assert res.status_code in (403, 404), (actor.id, method, path, res.text)
                assert res.status_code != 404 or path != S
            else:
                assert res.status_code in (200, 404), (method, path, res.status_code)
    pending = make_user(db, teacher_status="pending")
    res = await api.call(pending, "POST", S, json={"title": {"en": "x"}, "type": "percent", "params": {}})
    assert res.status_code == 403 and code(res) == "teacher_not_approved"


async def test_user_cannot_read_non_owner_schemes_via_any_route(db, api):
    w = world(db)
    secret = make_scheme(db, w.T, "pass_fail", PF, title={"en": "SENTINEL_SCHEME"})
    for actor in (w.O, w.S, w.X):
        assert (await api.call(actor, "GET", f"{S}/{secret.id}")).status_code == 404
        listed = (await api.call(actor, "GET", S)).json()["items"]
        assert str(secret.id) not in {i["id"] for i in listed}
    assert db.get(GradingScheme, secret.id).deleted_at is None
