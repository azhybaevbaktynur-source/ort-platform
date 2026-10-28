"""Phase 8a S2: module order (PHASE_8A_DESIGN 2.4, 5.2, 10): `reorder_modules` must list every live module
(`order_incomplete`), re-validates every prerequisite pair and refuses an order that would invert one
(`prerequisite_order`, listing the pairs; nothing changes), and `restore_module` puts a module back between its live
prerequisites and dependents or refuses when no such place exists."""
from sqlalchemy import select

from app.lms.modules.models import CourseModule
from tests.lms.modules_support import C, M, add_prerequisite, make_module, structure_world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _order(db, w) -> list:
    db.expire_all()
    return [m.id for m in db.scalars(select(CourseModule).where(CourseModule.course_id == w.course.id,
                                                                CourseModule.deleted_at.is_(None))
                                     .order_by(CourseModule.position)).all()]


async def _reorder(api, w, mods):
    return await api.call(w.O, "PUT", f"{C(w)}/modules/order", json={"ids": [str(m.id) for m in mods]})


async def test_reorder_dense_and_complete(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    assert (await _reorder(api, w, [c, a, b])).status_code == 204
    assert _order(db, w) == [c.id, a.id, b.id]
    assert [db.get(CourseModule, x).position for x in _order(db, w)] == [1, 2, 3]
    for bad in ([c, a], [c, a, b, b], [c, a, a]):
        r = await _reorder(api, w, bad)
        assert r.status_code == 422 and r.json()["error"]["code"] == "order_incomplete"
    other = make_module(db, structure_world(db).course, w.O)
    r = await _reorder(api, w, [c, a, other])
    assert r.status_code == 422 and r.json()["error"]["code"] == "order_incomplete"
    assert _order(db, w) == [c.id, a.id, b.id]


async def test_reorder_that_inverts_a_pair_is_refused(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    add_prerequisite(db, c, a)
    add_prerequisite(db, b, a)
    r = await _reorder(api, w, [b, c, a])
    assert r.status_code == 422 and r.json()["error"]["code"] == "prerequisite_order"
    pairs = {(p["module_id"], p["prerequisite_module_id"]) for p in r.json()["error"]["details"]["pairs"]}
    assert pairs == {(str(b.id), str(a.id)), (str(c.id), str(a.id))}
    assert _order(db, w) == [a.id, b.id, c.id]
    assert (await _reorder(api, w, [a, c, b])).status_code == 204  # keeps a first: allowed
    assert _order(db, w) == [a.id, c.id, b.id]


async def test_pairs_with_deleted_modules_do_not_block_reorder(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    add_prerequisite(db, c, a)
    assert (await api.call(w.O, "DELETE", M(w, a))).status_code == 204
    assert (await _reorder(api, w, [c, b])).status_code == 204


async def test_restore_goes_before_its_first_dependent(db, api):
    w = structure_world(db)
    a, b, c, d = (make_module(db, w.course, w.O) for _ in range(4))
    add_prerequisite(db, b, a)
    add_prerequisite(db, d, b)
    assert (await api.call(w.O, "DELETE", M(w, b))).status_code == 204
    assert _order(db, w) == [a.id, c.id, d.id]
    r = await api.call(w.O, "POST", M(w, b) + "/restore")
    assert r.status_code == 200 and r.json()["position"] == 3
    assert _order(db, w) == [a.id, c.id, b.id, d.id]


async def test_restore_refused_when_no_valid_place(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    add_prerequisite(db, b, a)
    add_prerequisite(db, c, b)
    assert (await api.call(w.O, "DELETE", M(w, b))).status_code == 204
    assert (await _reorder(api, w, [c, a])).status_code == 204  # allowed: the a <- b <- c pairs involve b
    r = await api.call(w.O, "POST", M(w, b) + "/restore")
    assert r.status_code == 422 and r.json()["error"]["code"] == "prerequisite_order"
    pairs = {(p["module_id"], p["prerequisite_module_id"]) for p in r.json()["error"]["details"]["pairs"]}
    assert pairs == {(str(c.id), str(b.id)), (str(b.id), str(a.id))}
    db.expire_all()
    assert db.get(CourseModule, b.id).deleted_at is not None
