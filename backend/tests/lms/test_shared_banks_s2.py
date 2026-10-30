"""Phase 9 S2: organization-shared banks (PHASE_9_DESIGN 4.2, 5.1, invariants 1-3, P9-2, P9-3, P9-9; S1 open item 1,
architect L5).

School R (sharing on) ── D (teacher T, course C, shared bank B + private bank PB)
                      └─ D2 (teacher T2, course C2)
School X (sharing on; teacher TX, course CX); independents i1, i2 (personal organizations)."""
import uuid

from sqlalchemy import select

from app.lms.audit.models import AdminAuditLog
from app.lms.content.models import BankQuestion, Passage, QuestionBank, QuestionVersion, TranslationGroup
from app.lms.organizations import ids as org_ids
from app.lms.organizations.ids import personal_org_id
from tests.lms.factories import make_assessment, make_bank, make_passage, make_question
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

SHARING = {"bank_sharing_enabled": True}


class W:
    pass


def world(db) -> W:
    w = W()
    w.R, w.X = make_org(db, "R"), make_org(db, "X")
    w.R.settings, w.X.settings = dict(SHARING), dict(SHARING)
    db.commit()
    w.D, w.D2 = make_department(db, w.R, "D"), make_department(db, w.R, "D2")
    w.T, w.T2, w.TX, w.aR, w.aD, w.aD2, w.aX, w.stud = (make_user(db) for _ in range(8))
    add_member(db, w.D, w.T, "teacher")
    add_member(db, w.D2, w.T2, "teacher")
    add_member(db, w.X, w.TX, "teacher")
    for org, u in ((w.R, w.aR), (w.D, w.aD), (w.D2, w.aD2), (w.X, w.aX)):
        add_member(db, org, u, "org_admin")
    langs = dict(languages=["en", "ru"], default_language="en", status="published")
    w.C = make_course(db, w.T, organization_id=w.D.id, **langs)
    w.C2 = make_course(db, w.T2, organization_id=w.D2.id, **langs)
    w.CX = make_course(db, w.TX, organization_id=w.X.id, **langs)
    enroll(db, w.C, w.stud)
    w.B = make_bank(db, w.C, w.T, title="Algebra")
    w.PB = make_bank(db, w.C, w.T, title="Private")
    w.i1, w.i2 = teacher(db), teacher(db)
    w.pa = make_user(db, platform_admin=True)
    return w


def _code(r):
    return r.json()["error"]["code"]


async def _share(api, user, course, bank):
    return await api.call(user, "POST", f"/courses/{course.id}/banks/{bank.id}/share")


# ------------------------------------------------------------------ share / unshare

async def test_share_and_unshare(db, api):
    w = world(db)
    r = await api.call(w.T, "GET", f"/courses/{w.C.id}/bank-sharing")
    assert r.json() == {"enabled": True, "reason": None, "root_id": str(w.R.id), "root_name": "R", "can_copy": True}
    r = await _share(api, w.T, w.C, w.B)
    assert r.status_code == 200, r.text
    assert (r.json()["visibility"], r.json()["can_edit"], r.json()["can_delete"]) == ("organization", True, True)
    assert (await _share(api, w.T, w.C, w.B)).status_code == 200  # idempotent
    # outsiders, students, a sibling department's teacher
    for user, code in ((w.TX, 404), (w.T2, 404), (w.stud, 403)):
        assert (await _share(api, user, w.C, w.PB)).status_code == code, user.id
    # the org admin of the tree may unshare (can_edit_bank) but not share a private bank
    assert (await _share(api, w.aR, w.C, w.PB)).status_code == 403
    r = await api.call(w.aR, "DELETE", f"/courses/{w.C.id}/banks/{w.B.id}/share")
    assert r.status_code == 200 and r.json()["visibility"] == "private"
    db.expire_all()
    b = db.get(QuestionBank, w.B.id)
    assert (b.visibility, b.shared_at, b.shared_by_id) == ("private", None, None)
    actions = {a.action for a in db.execute(select(AdminAuditLog)).scalars()}
    assert {"bank.shared", "bank.unshared"} <= actions


async def test_share_refusals(db, api):
    w = world(db)
    w.R.settings = {}
    db.commit()
    r = await _share(api, w.T, w.C, w.B)
    assert (r.status_code, _code(r)) == (409, "sharing_disabled")
    assert (await api.call(w.T, "GET", f"/courses/{w.C.id}/bank-sharing")).json()["reason"] == "setting_off"
    w.R.settings = dict(SHARING)
    db.commit()
    # quiz bank (invariant 1)
    a = make_assessment(db, w.C, w.T)
    qb = make_bank(db, w.C, w.T, title="Quiz bank", assessment_id=a.id)
    r = await _share(api, w.T, w.C, qb)
    assert (r.status_code, _code(r)) == (422, "quiz_bank_not_shareable")
    # personal organization (invariant 2, P9-3), even with a stored setting
    pc = make_course(db, w.i1, organization_id=personal_org_id(w.i1.id))
    pb = make_bank(db, pc, w.i1)
    r = await _share(api, w.i1, pc, pb)
    assert (r.status_code, _code(r)) == (422, "sharing_disabled")
    assert (await api.call(w.i1, "GET", f"/courses/{pc.id}/bank-sharing")).json()["reason"] == "personal"
    # ORT course (P9-9)
    ort = make_course(db, w.T, organization_id=w.D.id, template_key="ort", template_version=1, template_locked=True)
    ob = make_bank(db, ort, w.T)
    r = await _share(api, w.T, ort, ob)
    assert (r.status_code, _code(r)) == (422, "template_locked")
    body = (await api.call(w.T, "GET", f"/courses/{ort.id}/bank-sharing")).json()
    assert (body["enabled"], body["reason"], body["can_copy"]) == (False, "template_locked", False)


# ------------------------------------------------------------------ the read scope (isolation matrix)

async def test_isolation_matrix(db, api):
    w = world(db)
    make_question(db, w.B, w.T)
    assert (await _share(api, w.T, w.C, w.B)).status_code == 200
    xb = make_bank(db, w.CX, w.TX, title="X bank")
    assert (await _share(api, w.TX, w.CX, xb)).status_code == 200
    readers = (w.T, w.T2, w.aR, w.aD, w.aD2)
    for user in readers:
        for org in (w.R, w.D, w.D2):
            r = await api.call(user, "GET", f"/org/{org.id}/shared-banks")
            assert r.status_code == 200, (user.id, org.name, r.text)
            assert [b["title"] for b in r.json()["items"]] == ["Algebra"], (user.id, org.name)
    row = (await api.call(w.T2, "GET", f"/org/{w.R.id}/shared-banks")).json()["items"][0]
    assert (row["question_count"], row["organization_name"], row["course_title"]) == (1, "D", {"en": "Test course"})
    for user in (w.TX, w.aX, w.i1, w.i2, w.stud, w.pa):
        for path in (f"/org/{w.R.id}/shared-banks", f"/org/{w.R.id}/shared-banks/{w.B.id}",
                     f"/org/{w.D.id}/shared-banks/{w.B.id}/questions"):
            assert (await api.call(user, "GET", path)).status_code == 404, (user.id, path)
    # school X sees its own bank only
    assert [b["title"] for b in (await api.call(w.TX, "GET", f"/org/{w.X.id}/shared-banks")).json()["items"]] == [
        "X bank"]
    # a bank of another tree through this tree's route is a 404
    assert (await api.call(w.T, "GET", f"/org/{w.R.id}/shared-banks/{xb.id}")).status_code == 404
    # two independents never see each other (personal organizations are never a reading tree)
    assert (await api.call(w.i1, "GET", f"/org/{personal_org_id(w.i1.id)}/shared-banks")).status_code == 404
    # q on title
    r = await api.call(w.T2, "GET", f"/org/{w.R.id}/shared-banks", params={"q": "alg"})
    assert len(r.json()["items"]) == 1
    r = await api.call(w.T2, "GET", f"/org/{w.R.id}/shared-banks", params={"q": "zzz"})
    assert r.json()["items"] == []
    # questions with answer keys for the readers of the tree
    r = await api.call(w.T2, "GET", f"/org/{w.R.id}/shared-banks/{w.B.id}/questions")
    assert r.status_code == 200
    assert r.json()["items"][0]["current_version"]["data"]["correct"] == "B"
    assert (await api.call(w.T2, "GET", f"/org/{w.R.id}/shared-banks/{w.B.id}/passages")).status_code == 200
    # unshared or deleted: gone from the scope
    await api.call(w.T, "DELETE", f"/courses/{w.C.id}/banks/{w.B.id}/share")
    assert (await api.call(w.T2, "GET", f"/org/{w.R.id}/shared-banks")).json()["items"] == []


# ------------------------------------------------------------------ copy into a course

async def test_copy_content_and_rules(db, api, monkeypatch):
    w = world(db)
    p = make_passage(db, w.B, w.T, body="Read me")
    q1 = make_question(db, w.B, w.T, stem="Q one", passage_id=p.id, source_ref="ext-1", topic="alg", tags=["x"])
    q2 = make_question(db, w.B, w.T, stem="Q two", source_ref="ext-2")
    q2ru = make_question(db, w.B, w.T, stem="Q два", language="ru")
    g = TranslationGroup(course_id=w.C.id)
    db.add(g)
    db.flush()
    q2.translation_group_id = q2ru.translation_group_id = g.id
    lone = TranslationGroup(course_id=w.C.id)
    db.add(lone)
    db.flush()
    q1.translation_group_id = lone.id
    deleted = make_question(db, w.B, w.T, stem="gone")
    deleted.deleted_at = deleted.created_at
    db.commit()
    await _share(api, w.T, w.C, w.B)
    r = await api.call(w.T2, "POST", f"/courses/{w.C2.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert r.status_code == 201, r.text
    out = r.json()
    assert (out["title"], out["visibility"], out["copied_from_bank_id"], out["question_count"],
            out["passage_count"]) == ("Algebra (copy)", "private", str(w.B.id), 3, 1)
    db.expire_all()
    new_id = uuid.UUID(out["id"])
    nb = db.get(QuestionBank, new_id)
    assert (nb.course_id, nb.organization_id, nb.source_id) == (w.C2.id, w.D2.id, None)
    rows = db.execute(select(BankQuestion, QuestionVersion).join(
        QuestionVersion, QuestionVersion.id == BankQuestion.current_version_id)
        .where(BankQuestion.bank_id == new_id).order_by(BankQuestion.position)).all()
    assert [v.stem for _, v in rows] == ["Q one", "Q two", "Q два"]
    assert [q.position for q, _ in rows] == [1, 2, 3]
    assert all(q.source_ref is None for q, _ in rows)
    assert [q.copied_from_question_id for q, _ in rows] == [q1.id, q2.id, q2ru.id]
    assert all(v.version_no == 1 and v.created_by_id == w.T2.id for _, v in rows)
    src_v = db.get(QuestionVersion, q1.current_version_id)
    assert (rows[0][1].data, rows[0][1].content_hash) == (src_v.data, src_v.content_hash)
    assert (rows[0][0].topic, rows[0][0].tags) == ("alg", ["x"])
    new_p = db.execute(select(Passage).where(Passage.bank_id == new_id)).scalar_one()
    assert rows[0][0].passage_id == new_p.id
    # translation groups re-created inside the copy only; a group with one copied member is dropped
    assert rows[0][0].translation_group_id is None
    assert rows[1][0].translation_group_id == rows[2][0].translation_group_id is not None
    assert rows[1][0].translation_group_id != g.id
    assert db.get(TranslationGroup, rows[1][0].translation_group_id).course_id == w.C2.id
    # the source is untouched
    assert db.get(BankQuestion, q1.id).source_ref == "ext-1"
    assert any(a.action == "bank.copied" for a in db.execute(select(AdminAuditLog)).scalars())
    # refusals: outsider (404), org admin without course staff (404 / 403), ORT target, languages, size
    r = await api.call(w.TX, "POST", f"/courses/{w.CX.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert r.status_code == 404
    r = await api.call(w.aR, "POST", f"/courses/{w.C2.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert r.status_code == 403
    ort = make_course(db, w.T2, organization_id=w.D2.id, template_key="ort", template_version=1, template_locked=True)
    r = await api.call(w.T2, "POST", f"/courses/{ort.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert (r.status_code, _code(r)) == (422, "template_locked")
    en_only = make_course(db, w.T2, organization_id=w.D2.id)
    r = await api.call(w.T2, "POST", f"/courses/{en_only.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert (r.status_code, _code(r)) == (422, "language_not_in_course")
    monkeypatch.setattr(org_ids, "BANK_COPY_MAX_QUESTIONS", 2)
    r = await api.call(w.T2, "POST", f"/courses/{w.C2.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert (r.status_code, _code(r)) == (422, "bank_too_large")
    # the private bank is never copyable
    r = await api.call(w.T2, "POST", f"/courses/{w.C2.id}/banks/copy-from", json={"bank_id": str(w.PB.id)})
    assert r.status_code == 404
    # unsharing keeps the copy
    await api.call(w.T, "DELETE", f"/courses/{w.C.id}/banks/{w.B.id}/share")
    db.expire_all()
    assert db.get(QuestionBank, new_id).deleted_at is None


async def test_copy_rate_limit(db, api, monkeypatch):
    w = world(db)
    await _share(api, w.T, w.C, w.B)
    monkeypatch.setattr(org_ids, "BANK_COPY_RATE_PER_HOUR", 1)
    path, body = f"/courses/{w.C2.id}/banks/copy-from", {"bank_id": str(w.B.id)}
    assert (await api.call(w.T2, "POST", path, json=body)).status_code == 201
    r = await api.call(w.T2, "POST", path, json=body)
    assert r.status_code == 429


# ------------------------------------------------------------------ org admin read path (open item 1, L5)

async def test_org_admin_reads_only_shared_banks(db, api):
    w = world(db)
    q = make_question(db, w.B, w.T)
    pq = make_question(db, w.PB, w.T)
    p = make_passage(db, w.B, w.T)
    await _share(api, w.T, w.C, w.B)
    C = f"/courses/{w.C.id}"
    for admin in (w.aR, w.aD):
        for path in (f"{C}/banks/{w.B.id}", f"{C}/banks/{w.B.id}/questions", f"{C}/questions/{q.id}",
                     f"{C}/questions/{q.id}/versions", f"{C}/questions/{q.id}/preview",
                     f"{C}/questions/{q.id}/translations", f"{C}/banks/{w.B.id}/passages", f"{C}/passages/{p.id}",
                     f"{C}/passages/{p.id}/versions"):
            r = await api.call(admin, "GET", path)
            assert r.status_code == 200, (admin.id, path, r.text)
        listed = (await api.call(admin, "GET", f"{C}/banks")).json()["items"]
        assert [(b["title"], b["can_edit"], b["can_delete"]) for b in listed] == [("Algebra", True, False)]
        assert (await api.call(admin, "GET", f"{C}/banks", params={"deleted": "true"})).json()["items"] == []
        # private bank and its answer keys stay staff-only (A13)
        for path in (f"{C}/banks/{w.PB.id}", f"{C}/banks/{w.PB.id}/questions", f"{C}/questions/{pq.id}"):
            assert (await api.call(admin, "GET", path)).status_code == 403, (admin.id, path)
    # admins of a sibling department or another school: unchanged 404
    for user in (w.aD2, w.aX):
        assert (await api.call(user, "GET", f"{C}/banks/{w.B.id}")).status_code == 404
    # unshared: the org admin loses the read
    await api.call(w.T, "DELETE", f"{C}/banks/{w.B.id}/share")
    assert (await api.call(w.aR, "GET", f"{C}/banks/{w.B.id}")).status_code == 403
    assert (await api.call(w.aR, "GET", f"{C}/banks")).status_code == 403
