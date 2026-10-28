"""Phase 8a S2: prerequisites (PHASE_8A_DESIGN 2.4, 5.2, 10): same course, earlier only, never self, never deleted
(422 `prerequisite_invalid` with the reason, nothing written), replace-set semantics, a kept deleted entry with the
staff warning, and chain completion through the API."""
import uuid

from sqlalchemy import select

from app.lms.modules.models import ModulePrerequisite
from tests.lms.modules_support import C, I, M, add_prerequisite, make_item, make_module, make_page, structure_world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _prereqs(db, m) -> set:
    db.expire_all()
    return set(db.scalars(select(ModulePrerequisite.prerequisite_module_id)
                          .where(ModulePrerequisite.module_id == m.id)).all())


async def _put(api, w, m, ids):
    return await api.call(w.O, "PUT", M(w, m) + "/prerequisites", json={"module_ids": [str(i) for i in ids]})


async def test_valid_set_replace_and_clear(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    r = await _put(api, w, c, [a.id, b.id, a.id])
    assert r.status_code == 200 and set(r.json()["prerequisites"]) == {str(a.id), str(b.id)}
    assert _prereqs(db, c) == {a.id, b.id}
    assert (await _put(api, w, c, [b.id])).status_code == 200 and _prereqs(db, c) == {b.id}
    assert (await _put(api, w, c, [])).status_code == 200 and _prereqs(db, c) == set()


async def test_invalid_prerequisites_are_refused_with_reason(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    gone = make_module(db, w.course, w.O, position=0)
    gone.soft_delete(w.O.id)
    db.commit()
    other = structure_world(db)
    foreign = make_module(db, other.course, other.O, position=1)
    add_prerequisite(db, b, a)
    cases = [
        (b, b.id, "not_earlier"),       # self
        (b, c.id, "not_earlier"),       # later
        (a, b.id, "not_earlier"),       # would also be a cycle
        (c, foreign.id, "not_same_course"),
        (c, uuid.uuid4(), "not_same_course"),
        (c, gone.id, "deleted"),
    ]
    for module, pid, reason in cases:
        r = await _put(api, w, module, [pid])
        assert r.status_code == 422, (reason, r.text)
        err = r.json()["error"]
        assert err["code"] == "prerequisite_invalid"
        assert err["details"] == {"module_id": str(module.id), "prerequisite_module_id": str(pid), "reason": reason}
    assert _prereqs(db, b) == {a.id}  # nothing changed, never a silent drop
    r = await _put(api, w, c, [a.id, c.id])
    assert r.status_code == 422 and _prereqs(db, c) == set()


async def test_kept_deleted_prerequisite_and_warnings(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    add_prerequisite(db, c, a)
    add_prerequisite(db, c, b)
    assert (await api.call(w.O, "PATCH", M(w, b), json={"published": False})).status_code == 200
    assert (await api.call(w.O, "DELETE", M(w, a))).status_code == 204
    out = (await api.call(w.O, "GET", f"{C(w)}/modules")).json()["modules"]
    mc = next(m for m in out if m["id"] == str(c.id))
    assert {(x["code"], x["module_id"]) for x in mc["warnings"]} == {
        ("prerequisite_deleted", str(a.id)), ("prerequisite_unpublished", str(b.id))}
    # re-sending the set with the deleted entry keeps it; adding it anew elsewhere is refused
    assert (await _put(api, w, c, [a.id, b.id])).status_code == 200 and _prereqs(db, c) == {a.id, b.id}
    assert (await _put(api, w, c, [b.id])).status_code == 200 and _prereqs(db, c) == {b.id}
    assert (await _put(api, w, c, [a.id, b.id])).json()["error"]["details"]["reason"] == "deleted"
    # students: the unpublished prerequisite is skipped, c opens
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()["modules"]
    assert [(m["id"], m["state"]) for m in out] == [(str(c.id), "completed")]


async def test_chain_completion_through_the_api(db, api):
    w = structure_world(db)
    a, b, c = (make_module(db, w.course, w.O) for _ in range(3))
    first = make_item(db, a, make_page(db, w.course, w.O), requirement=("view",))
    second = make_item(db, b, make_page(db, w.course, w.O), requirement=("mark_done",))
    make_item(db, c, make_page(db, w.course, w.O), requirement=("view",))
    assert (await _put(api, w, b, [a.id])).status_code == 200
    assert (await _put(api, w, c, [b.id])).status_code == 200

    async def states():
        return [m["state"] for m in (await api.call(w.S, "GET", f"{C(w)}/modules")).json()["modules"]]

    assert await states() == ["unlocked", "locked", "locked"]
    assert (await api.call(w.S, "POST", I(w, b, second) + "/done", json={"done": True})).status_code == 423
    assert (await api.call(w.S, "POST", I(w, a, first) + "/view")).json()["state"] == "completed"
    assert await states() == ["completed", "unlocked", "locked"]
    assert (await api.call(w.S, "POST", I(w, b, second) + "/done", json={"done": True})).status_code == 200
    assert await states() == ["completed", "completed", "unlocked"]
