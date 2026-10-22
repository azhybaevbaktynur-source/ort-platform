"""Importer writer + routes (C5 step 2): acceptance cases at DB level, conflict rules, isolation, authz, rate limit."""
import io
import uuid
import json

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.content.models import BankQuestion, Passage, QuestionBank, QuestionVersion
from app.lms.files.models import Asset, AssetBlob
from app.lms.files.storage import get_blob_storage
from app.main import app
from tests.lms.content_support import world
from tests.lms.factories import auth
from tests.lms.files_support import local_storage  # noqa: F401
from tests.lms.s3_support import Api, api, clean_rate_limits, db, make_course, make_user, teacher  # noqa: F401
from tests.lms.test_import_bundle import FIXTURE, Q3_IMAGE, SECTIONS, fixture_files, make_zip, prefixed, read_rows, write_rows

pytestmark = pytest.mark.usefixtures("local_storage")


async def imp(user, cid, data: bytes, filename="b.zip", commit=True, ip="10.9.9.9", **form):
    form.setdefault("language", "ru")
    form = {k: v for k, v in form.items() if v is not None}
    h = auth(user)
    h["x-forwarded-for"] = f"{ip}, 10.255.255.1"
    path = f"/api/v1/courses/{cid}/imports" + ("" if commit else "/preview")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(path, files={"file": (filename, data, "application/octet-stream")}, data=form, headers=h)


def zbytes():
    return open(FIXTURE, "rb").read()


def counts(db, bank_id=None):
    db.expire_all()
    q = select(func.count()).select_from(BankQuestion)
    if bank_id:
        q = q.where(BankQuestion.bank_id == uuid.UUID(str(bank_id)))
    return db.scalar(q)


@pytest.fixture
def w(db):
    return world(db, languages=("ru", "ky", "en"))


async def test_case1_db_level_and_case9_idempotent(w, db):
    res = await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    assert res.status_code == 200, res.text
    rep = res.json()
    assert rep["ok"] and rep["committed"] and rep["errors"] == []
    b = rep["banks"][0]
    assert b["created"] == SECTIONS and b["source_id"] == "tsoomo19" and b["images"] == 14
    assert rep["images_total"] == 14 and rep["images_new"] == 14

    banks = db.scalars(select(QuestionBank)).all()
    assert len(banks) == 1 and banks[0].source_id == "tsoomo19" and banks[0].default_language == "ru"
    qs = db.scalars(select(BankQuestion).order_by(BankQuestion.position)).all()
    assert len(qs) == 150
    assert qs[0].source_ref == "tsoomo19:math_1:1" and qs[0].position == 1 and qs[-1].source_ref == "tsoomo19:grammar:30"
    assert qs[-1].position == 150 and all(q.language == "ru" for q in qs)
    assert db.scalar(select(func.count()).select_from(Asset)) == 14
    # invariant: current version belongs to the question, types match
    for q in qs:
        v = db.get(QuestionVersion, q.current_version_id)
        assert v.question_id == q.id and v.type == q.type and q.imported_version_id == v.id and v.origin == "import"

    q3 = next(q for q in qs if q.source_ref == "tsoomo19:math_1:3")
    v3 = db.get(QuestionVersion, q3.current_version_id)
    assert q3.type == "comparison" and v3.data["column_a"] and v3.data["column_b"] and v3.image
    asset = db.get(Asset, uuid.UUID(v3.image["asset_id"]))
    stored = Image.open(io.BytesIO(get_blob_storage().get(asset.storage_key))).convert("RGBA")
    src = Image.open(io.BytesIO(fixture_files()["images/" + Q3_IMAGE])).convert("RGBA")
    assert stored.size == src.size and stored.tobytes() == src.tobytes()

    # case 12: reading passages byte-exact, <u> and $ kept
    rows = read_rows(fixture_files()["questions.csv"])
    bodies = {r["passage_text"].strip() for r in rows if r["passage_text"].strip()}
    stored_p = set()
    from app.lms.content.models import PassageVersion
    for p in db.scalars(select(Passage)).all():
        stored_p.add(db.get(PassageVersion, p.current_version_id).body)
    assert stored_p == {x.replace("\r\n", "\n") for x in bodies}
    assert any("[5]" in x and "\n" in x for x in stored_p)

    # case 9: same zip again -> everything unchanged, no new versions, no new assets/blobs
    res = await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    rep = res.json()
    assert rep["ok"] and rep["banks"][0]["unchanged"] == SECTIONS and rep["banks"][0]["created"] == {}
    assert rep["images_new"] == 0 and rep["images_existing"] == 14
    db.expire_all()
    assert counts(db) == 150 and db.scalar(select(func.count()).select_from(Asset)) == 14
    assert db.scalar(select(func.max(QuestionVersion.version_no))) == 1
    assert db.scalar(select(func.count()).select_from(QuestionBank)) == 1

    # corrected re-upload -> exactly one v2
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    rows[40]["stem"] = rows[40]["stem"] + " (corrected)"
    files["questions.csv"] = write_rows(rows)
    rep = (await imp(w.O, w.cid, make_zip(files), exam_type="full_main")).json()
    assert sum(rep["banks"][0]["updated"].values()) == 1 and sum(rep["banks"][0]["unchanged"].values()) == 149
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(QuestionVersion).where(QuestionVersion.version_no == 2)) == 1
    assert db.scalar(select(func.count()).select_from(QuestionVersion)) == 151


async def test_preview_writes_nothing_and_matches_commit(w, db):
    rep = (await imp(w.O, w.cid, zbytes(), commit=False, exam_type="full_main")).json()
    assert rep["ok"] and not rep["committed"] and rep["banks"][0]["created"] == SECTIONS
    assert rep["banks"][0]["bank_exists"] is False and rep["images_new"] == 14
    assert counts(db) == 0 and db.scalar(select(func.count()).select_from(QuestionBank)) == 0
    assert db.scalar(select(func.count()).select_from(Asset)) == 0
    await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    rep = (await imp(w.O, w.cid, zbytes(), commit=False, exam_type="full_main")).json()
    assert rep["banks"][0]["unchanged"] == SECTIONS and rep["banks"][0]["bank_exists"] is True
    assert rep["images_existing"] == 14
    db.expire_all()
    assert db.scalar(select(func.max(QuestionVersion.version_no))) == 1


async def test_errors_save_nothing(w, db):
    files = fixture_files()
    del files["images/" + Q3_IMAGE]
    res = await imp(w.O, w.cid, make_zip(files), exam_type="full_main")
    rep = res.json()
    assert res.status_code == 200 and rep["ok"] is False and rep["committed"] is False
    assert [e["code"] for e in rep["errors"]] == ["image_missing"] and rep["errors"][0]["row"] == 3
    assert counts(db) == 0 and db.scalar(select(func.count()).select_from(Asset)) == 0


async def test_conflict_rules(w, db):
    await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    q = db.scalars(select(BankQuestion).where(BankQuestion.position == 35)).one()
    qid = str(q.id)
    # teacher edits the question
    v0 = db.get(QuestionVersion, q.current_version_id)
    content = {"type": v0.type, "stem": "Edited locally", "data": v0.data, "explanation": v0.explanation}
    res = await Api().call(w.O, "PATCH", f"/courses/{w.cid}/questions/{qid}",
                           json={"base_version_id": str(q.current_version_id), "content": content})
    assert res.status_code == 200, res.text
    # source changes the same question -> conflict, skipped by default
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    idx = next(i for i, r in enumerate(rows) if i + 1 == 30 + 5)
    rows[idx]["stem"] = rows[idx]["stem"] + " (source fix)"
    files["questions.csv"] = write_rows(rows)
    zb = make_zip(files)
    rep = (await imp(w.O, w.cid, zb, exam_type="full_main")).json()
    assert rep["ok"] and sum(rep["banks"][0]["conflicts"].values()) == 1
    assert [x["code"] for x in rep["warnings"]] == ["question_edited_locally"]
    db.expire_all()
    cur = db.get(QuestionVersion, db.get(BankQuestion, q.id).current_version_id)
    assert cur.stem == "Edited locally" and cur.version_no == 2
    # original bundle again: the source did not change since the import -> teacher's edit is not a conflict
    rep = (await imp(w.O, w.cid, zbytes(), exam_type="full_main")).json()
    assert rep["warnings"] == [] and sum(rep["banks"][0]["conflicts"].values()) == 0
    # overwrite adds an import version, history keeps both
    rep = (await imp(w.O, w.cid, zb, exam_type="full_main", on_conflict="overwrite")).json()
    assert sum(rep["banks"][0]["updated"].values()) == 1
    db.expire_all()
    cur = db.get(QuestionVersion, db.get(BankQuestion, q.id).current_version_id)
    assert cur.version_no == 3 and cur.origin == "import" and cur.stem.endswith("(source fix)")
    # soft-deleted question is skipped
    res = await Api().call(w.O, "DELETE", f"/courses/{w.cid}/questions/{qid}")
    assert res.status_code in (200, 204)
    rep = (await imp(w.O, w.cid, zbytes(), exam_type="full_main")).json()
    assert sum(rep["banks"][0]["skipped_deleted"].values()) == 1
    assert [x["code"] for x in rep["warnings"]] == ["question_deleted_skipped"]
    db.expire_all()
    assert db.get(BankQuestion, q.id).deleted_at is not None


async def test_missing_from_reupload_kept_and_warned(w, db):
    await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    files = fixture_files()
    rows = read_rows(files["questions.csv"])[:-1]
    m = json.loads(files["manifest.json"])
    m["questions"] = m["questions"][:-1]
    m["question_count"] = 149
    files["questions.csv"] = write_rows(rows)
    files["manifest.json"] = json.dumps(m, ensure_ascii=False).encode()
    rep = (await imp(w.O, w.cid, make_zip(files), exam_type="full_main")).json()
    assert rep["ok"] and [x["code"] for x in rep["warnings"]] == ["questions_missing_from_bundle"]
    assert rep["warnings"][0]["params"]["external_ids"] == ["tsoomo19:grammar:30"]
    assert counts(db) == 150


async def test_two_bundles_and_wrapper_folder(w, db):
    a = fixture_files()
    b = dict(a)
    m = json.loads(b["manifest.json"])
    m["source_id"] = "other"
    m["questions"] = [dict(q, external_id=q["external_id"].replace("tsoomo19:", "other:")) for q in m["questions"]]
    b["manifest.json"] = json.dumps(m).encode()
    rep = (await imp(w.O, w.cid, make_zip({**prefixed(a, "one/"), **prefixed(b, "two/")}), exam_type="full_main")).json()
    assert rep["ok"] and len(rep["banks"]) == 2
    assert db.scalar(select(func.count()).select_from(QuestionBank)) == 2 and counts(db) == 300
    assert db.scalar(select(func.count()).select_from(Asset)) == 14   # images shared by sha


async def test_plain_csv_general_mode_append_and_target_bank(w, db):
    text = ("section,stem,option_a,option_b,option_c,option_d,correct_option\n"
            "unit,Q1,1,2,3,4,A\nunit,Q2,1,2,3,4,B\n")
    rep = (await imp(w.O, w.cid, text.encode(), "My set.csv", language="ru")).json()
    assert rep["ok"] and rep["banks"][0]["bank_title"] == "My set" and rep["banks"][0]["created"] == {"unit": 2}
    bank_id = rep["banks"][0]["bank_id"]
    rep = (await imp(w.O, w.cid, text.encode(), "again.csv", language="ru", target_bank_id=bank_id)).json()
    assert rep["ok"]
    db.expire_all()
    pos = db.scalars(select(BankQuestion.position).order_by(BankQuestion.position)).all()
    assert pos == [1, 2, 3, 4] and counts(db, bank_id) == 4
    # target bank of another course is a 404
    other = make_course(db, w.O, languages=["ru"], default_language="ru")
    res = await imp(w.O, str(other.id), text.encode(), "x.csv", language="ru", target_bank_id=bank_id)
    assert res.status_code == 404


async def test_csv_external_and_bare_image_names(w):
    rows = read_rows(fixture_files()["questions.csv"])
    rep = (await imp(w.O, w.cid, write_rows(rows), "q.csv", exam_type="full_main")).json()
    assert not rep["ok"] and [e["code"] for e in rep["errors"]].count("image_not_included") == 14


async def test_cross_course_isolation(w, db):
    other = make_course(db, w.T, languages=["ru"], default_language="ru")
    await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    rep = (await imp(w.T, str(other.id), zbytes(), exam_type="full_main")).json()
    assert rep["ok"] and rep["banks"][0]["created"] == SECTIONS     # second course: independent bank
    db.expire_all()
    banks = db.scalars(select(QuestionBank)).all()
    assert len(banks) == 2 and {b.course_id for b in banks} == {w.course.id, other.id}
    # edit in course B via re-import does not touch course A
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    rows[0]["explanation"] = "changed"
    files["questions.csv"] = write_rows(rows)
    await imp(w.T, str(other.id), make_zip(files), exam_type="full_main")
    db.expire_all()
    a_bank = next(b for b in banks if b.course_id == w.course.id)
    assert db.scalar(select(func.max(QuestionVersion.version_no)).join(BankQuestion, BankQuestion.id == QuestionVersion.question_id)
                     .where(BankQuestion.bank_id == a_bank.id)) == 1


async def test_authz(w, db):
    for user, want in ((w.S, 403), (w.X, 404)):
        for commit in (False, True):
            res = await imp(user, w.cid, zbytes(), commit=commit)
            assert res.status_code == want, (user.id, commit, res.status_code)
    # staff: teachers and assistants hold content.manage in this design
    assert (await imp(w.AS, w.cid, zbytes(), commit=False, exam_type="full_main")).status_code == 200
    assert (await imp(w.T, w.cid, zbytes(), commit=False, exam_type="full_main")).status_code == 200
    res = await AsyncClient(transport=ASGITransport(app=app), base_url="http://test").post(
        f"/api/v1/courses/{w.cid}/imports", files={"file": ("a.zip", b"x")}, data={"language": "ru"})
    assert res.status_code in (401, 403)


async def test_validation_and_limits(w, monkeypatch):
    assert (await imp(w.O, w.cid, zbytes(), language="de")).status_code == 422
    assert (await imp(w.O, w.cid, zbytes(), exam_type="bogus")).status_code == 422
    assert (await imp(w.O, w.cid, zbytes(), target_bank_id="nope")).status_code == 422
    monkeypatch.setattr(settings, "IMPORT_MAX_UPLOAD_BYTES", 1000)
    res = await imp(w.O, w.cid, zbytes())
    assert res.status_code == 413 and res.json()["error"]["code"] == "file_too_large"


async def test_rate_limit(w, monkeypatch):
    monkeypatch.setattr(settings, "CONTENT_IMPORT_RATE_PER_HOUR", 2)
    for _ in range(2):
        assert (await imp(w.O, w.cid, b"not a zip", commit=False)).status_code == 200
    res = await imp(w.O, w.cid, b"not a zip", commit=False)
    assert res.status_code == 429


async def test_general_mode_comparison_zip_without_exam_type(w, db):
    rep = (await imp(w.O, w.cid, zbytes())).json()    # general mode: free sections, math_1 rows are comparisons by columns
    assert rep["ok"], rep["errors"][:3]
    assert counts(db) == 150
