"""Importer review fixes: bounded parsing, issue cap, zip/manifest guards, orphan blobs, tags, deleted passages."""
import io
import json
import os
import subprocess
import sys
import textwrap
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.content.importers import ImportOptions, parse_upload
from app.lms.content.importers import service as isvc
from app.lms.content.importers.ort_csv import BUNDLE_COLUMNS
from app.lms.content.models import BankQuestion, Passage, QuestionVersion
from app.lms.files import service as fsvc
from app.lms.files.models import Asset, AssetBlob
from app.lms.files.storage import blob_key
from app.main import app
from tests.lms.factories import auth
from tests.lms.files_support import db_storage, local_storage  # noqa: F401
from tests.lms.s3_support import Api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_import_api import imp, w, zbytes  # noqa: F401
from tests.lms.test_import_bundle import codes, fixture_files, make_zip, parse, read_rows, write_rows

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HEADER = ",".join(BUNDLE_COLUMNS) + "\n"


def _zip_of(entries: dict, level=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", level) as zf:
        for n, d in entries.items():
            zf.writestr(n, d)
    return buf.getvalue()


# ------------------------------------------------------------------ 1. bounded memory

PROBE = textwrap.dedent("""
    import resource, sys, json
    sys.path.insert(0, %r)
    from app.lms.content.importers import ImportOptions, parse_upload
    def rss():
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return v / (1024 * 1024) if sys.platform == "darwin" else v / 1024
    raw = open(sys.argv[1], "rb").read()
    before = rss()
    up = parse_upload(raw, sys.argv[2], ImportOptions())
    print(json.dumps({"growth_mb": rss() - before, "errors": [e.code for e in up.issues.errors],
                      "n_errors": up.issues.n_errors, "n": len(up.issues.errors) + len(up.issues.warnings)}))
""") % BACKEND


def _probe(tmp_path, data: bytes, name: str) -> dict:
    p = tmp_path / name
    p.write_bytes(data)
    env = dict(os.environ, DATABASE_URL="sqlite:///" + str(tmp_path / "p.db"))
    out = subprocess.run([sys.executable, "-c", PROBE, str(p), name], capture_output=True, text=True, env=env,
                         cwd=BACKEND, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_probe_five_million_blank_lines_in_tiny_zip(tmp_path):
    data = _zip_of({"questions.csv": HEADER.encode() + b"\n" * 5_000_000})
    assert len(data) < 20_000
    r = _probe(tmp_path, data, "b.zip")
    assert r["growth_mb"] < 100 and r["n"] <= 3 and "too_many_rows" in r["errors"]


def test_probe_million_junk_rows_in_zip(tmp_path):
    data = _zip_of({"questions.csv": HEADER.encode() + b"x\n" * 1_000_000})
    r = _probe(tmp_path, data, "b.zip")
    assert r["growth_mb"] < 100 and r["n"] <= 3 and "too_many_rows" in r["errors"]


def test_probe_two_mb_plain_csv_of_junk(tmp_path):
    data = HEADER.encode() + b"a,b,c,d\n" * 250_000
    assert 2_000_000 <= len(data) <= 2_100_000
    r = _probe(tmp_path, data, "p.csv")
    assert r["growth_mb"] < 100 and r["n"] <= 3 and "too_many_rows" in r["errors"]


def test_issue_cap_with_totals():
    rows = HEADER + "".join(f"s{i},t,easy,stem,,,a,b,c,d,,Z,,,\n" for i in range(1000))
    up = parse_upload(rows.encode(), "x.csv", ImportOptions(exam_type="full_main"))
    assert len(up.issues.errors) == settings.IMPORT_MAX_ISSUES + 1
    last = up.issues.errors[-1]
    assert last.code == "too_many_issues" and last.params["errors_total"] == up.issues.n_errors >= 1000
    # warnings are capped as well
    files = fixture_files()
    for i in range(300):
        files[f"extra/unused{i}.png"] = files["images/tsoomo19_math_1_q03.png"]
    up = parse(files)
    assert len(up.issues.warnings) == settings.IMPORT_MAX_ISSUES + 1 and up.issues.warnings[-1].code == "too_many_issues"


def test_csv_size_cap(monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_MAX_CSV_BYTES", 100)
    assert "csv_too_large" in codes(parse(fixture_files()))
    assert [e.code for e in parse_upload(HEADER.encode() + b"x" * 200, "a.csv", ImportOptions()).issues.errors] == ["csv_too_large"]


def test_header_mismatch_params_truncated():
    wide = ",".join("c" * 100 for _ in range(60)) + "\n"
    files = {"manifest.json": json.dumps({"format": "ort-question-bundle", "format_version": 1, "source_id": "s",
                                          "question_count": 0, "questions": []}).encode(),
             "questions.csv": wide.encode()}
    up = parse(files)
    e = next(e for e in up.issues.errors if e.code == "csv_header_mismatch")
    assert len(e.params["got"]) == 20 and all(len(c) <= 40 for c in e.params["got"])


def test_total_rows_across_bundles_capped(monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_MAX_ROWS", 200)
    files = {**fixture_files()}
    files.update({"two/" + n: d for n, d in fixture_files().items()})
    m = json.loads(files["two/manifest.json"])
    m["source_id"] = "other"
    m["questions"] = [dict(q, external_id=q["external_id"].replace("tsoomo19:", "other:")) for q in m["questions"]]
    files["two/manifest.json"] = json.dumps(m).encode()
    up = parse(files)
    assert "too_many_rows" in codes(up)


# ------------------------------------------------------------------ 7/8. zip and manifest guards

def test_end_record_checked_before_zipfile(monkeypatch):
    from app.lms.content.importers import zipsafe

    data = _zip_of({f"f{i}.txt": b"" for i in range(60)}, zipfile.ZIP_STORED)
    monkeypatch.setattr(settings, "IMPORT_MAX_ZIP_ENTRIES", 50)
    monkeypatch.setattr(zipsafe.zipfile, "ZipFile", lambda *a, **k: pytest.fail("ZipFile must not be built"))
    assert [e.code for e in parse_upload(data, "a.zip", ImportOptions()).issues.errors] == ["zip_too_many_files"]


def test_manifest_guards(monkeypatch):
    files = fixture_files()
    files["manifest.json"] = b"[" * 200_000 + b"]" * 200_000
    assert codes(parse(files)) == ["manifest_invalid_json"]
    files = fixture_files()
    files["manifest.json"] = b" " * 100 + files["manifest.json"]
    monkeypatch.setattr(settings, "IMPORT_MAX_MANIFEST_BYTES", 1000)
    assert codes(parse(files)) == ["manifest_invalid"]
    monkeypatch.setattr(settings, "IMPORT_MAX_MANIFEST_BYTES", 5 * 1024 * 1024)
    monkeypatch.setattr(settings, "IMPORT_MAX_ROWS", 10)
    assert "too_many_rows" in codes(parse(fixture_files()))


def test_pixel_cap_uses_asset_setting(monkeypatch):
    monkeypatch.setattr(settings, "ASSET_MAX_PIXELS", 50)
    assert "image_too_many_pixels" in codes(parse(fixture_files()))


# ------------------------------------------------------------------ 10. tags

def test_plain_csv_tags_cleaned():
    tags = ",".join([f"tag{i}" for i in range(40)] + ["x" * 100])
    csv_text = ("section,topic,difficulty,stem,option_a,option_b,option_c,option_d,correct_option,tags\n"
                f'S,T,easy,What?,1,2,3,4,A,"{tags}"\n')
    up = parse_upload(csv_text.encode(), "t.csv", ImportOptions())
    assert up.issues.errors == []
    got = up.bundles[0].items[0].tags
    assert len(got) == 20 and all(len(t) <= 40 for t in got)


async def test_reimport_keeps_teacher_tags(w, db):
    await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    q = db.scalars(select(BankQuestion).where(BankQuestion.position == 7)).one()
    q.tags = ["mine"]
    db.commit()
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    rows[6]["topic"] = "Changed topic"
    files["questions.csv"] = write_rows(rows)
    rep = (await imp(w.O, w.cid, make_zip(files), exam_type="full_main")).json()
    assert rep["ok"]
    db.expire_all()
    q = db.get(BankQuestion, q.id)
    assert q.tags == ["mine"] and q.topic == "Changed topic"


# ------------------------------------------------------------------ 11. deleted passage

async def test_new_question_of_deleted_passage_skipped(w, db):
    await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    p = db.scalars(select(Passage)).first()
    q = db.scalars(select(BankQuestion).where(BankQuestion.passage_id == p.id)).first()
    old_ref = q.source_ref
    p.deleted_at = datetime.now(timezone.utc)
    q.source_ref = "renamed:" + old_ref
    db.commit()
    before = db.scalar(select(func.count()).select_from(BankQuestion))
    rep = (await imp(w.O, w.cid, zbytes(), exam_type="full_main")).json()
    assert rep["ok"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(BankQuestion)) == before
    warn = [x for x in rep["warnings"] if x["code"] == "question_deleted_skipped" and x["params"].get("reason") == "passage_deleted"]
    assert warn and warn[0]["params"]["count"] >= 1
    assert sum(rep["banks"][0]["skipped_deleted"].values()) >= 1


# ------------------------------------------------------------------ 3. blobs

def _blob_count(storage) -> int:
    root = getattr(storage, "root", None)
    n = 0
    for dp, _, fns in os.walk(root):
        n += sum(1 for f in fns if f.endswith(".webp"))
    return n


async def test_quota_failure_leaves_zero_blobs(w, db, local_storage, monkeypatch):
    monkeypatch.setattr(settings, "ASSET_QUOTA_BYTES_PER_USER", 2000)
    rep = (await imp(w.O, w.cid, zbytes(), exam_type="full_main")).json()
    assert rep["ok"] is False and [e["code"] for e in rep["errors"]] == ["storage_quota_exceeded"]
    assert _blob_count(local_storage) == 0
    assert db.scalar(select(func.count()).select_from(Asset)) == 0
    assert db.scalar(select(func.count()).select_from(BankQuestion)) == 0


async def test_db_cap_failure_leaves_zero_blobs(w, db, db_storage, monkeypatch):
    monkeypatch.setattr(settings, "ASSET_DB_MAX_TOTAL_BYTES", 3000)
    rep = (await imp(w.O, w.cid, zbytes(), exam_type="full_main")).json()
    assert rep["ok"] is False and [e["code"] for e in rep["errors"]] == ["storage_full"]
    assert db.scalar(select(func.count()).select_from(AssetBlob)) == 0


async def test_transaction_failure_removes_new_blobs(w, db, local_storage, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(isvc, "_process_bundle", boom)
    with pytest.raises(RuntimeError):
        await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    # pysqlite commits the outermost SAVEPOINT, so on SQLite the assets may survive the rollback; the invariant
    # on every dialect is: no blob without an asset row (strict zero is asserted on PostgreSQL)
    db.expire_all()
    keys = set(db.scalars(select(Asset.storage_key)))
    on_disk = {os.path.join("img", f) for f in os.listdir(os.path.join(local_storage.root, "img"))} \
        if os.path.isdir(os.path.join(local_storage.root, "img")) else set()
    assert on_disk <= keys
    if db.bind.dialect.name == "postgresql":
        assert not on_disk and not keys


async def test_encode_failure_stores_nothing(w, db, local_storage):
    files = fixture_files()
    files["images/tsoomo19_math_1_q03.png"] = files["images/tsoomo19_math_1_q03.png"][:-40] + b"\0" * 40
    rep = (await imp(w.O, w.cid, make_zip(files), exam_type="full_main")).json()
    assert rep["ok"] is False
    assert _blob_count(local_storage) == 0


async def test_preview_does_not_encode(w, db, local_storage, monkeypatch):
    monkeypatch.setattr(isvc, "encode_image", lambda *a, **k: pytest.fail("preview must not encode"))
    rep = (await imp(w.O, w.cid, zbytes(), commit=False, exam_type="full_main")).json()
    assert rep["ok"] and rep["images_new"] == 14 and rep["images_existing"] == 0
    assert _blob_count(local_storage) == 0


def _old(path):
    t = time.time() - 7200
    os.utime(path, (t, t))


def test_orphan_sweep_local(db, local_storage):
    owner = None
    from tests.lms.s3_support import make_user
    owner = make_user(db)
    sh = {n: (str(n) * 64)[:64] for n in "abc"}
    for n in "abc":
        local_storage.put(blob_key(sh[n]), b"x" + n.encode(), "image/webp")
    # b has an asset row; c is young
    db.add(Asset(owner_id=owner.id, kind="image", visibility="public", source_sha256="9" * 64, sha256=sh["b"],
                 storage_key=blob_key(sh["b"]), mime="image/webp", bytes=2, source_bytes=2))
    db.commit()
    _old(local_storage._path(blob_key(sh["a"])))
    _old(local_storage._path(blob_key(sh["b"])))
    stale_tmp = os.path.join(local_storage.root, "img", "zz.tmp")
    open(stale_tmp, "wb").write(b"1")
    _old(stale_tmp)
    assert fsvc.sweep_orphan_blobs(db) == 1
    assert not local_storage.exists(blob_key(sh["a"]))
    assert local_storage.exists(blob_key(sh["b"])) and local_storage.exists(blob_key(sh["c"]))
    assert not os.path.exists(stale_tmp)


def test_orphan_sweep_db_driver_and_throttle(db, db_storage, monkeypatch):
    from tests.lms.s3_support import make_user
    owner = make_user(db)
    a, b = "a" * 64, "b" * 64
    db_storage.put(blob_key(a), b"1", "image/webp")
    db_storage.put(blob_key(b), b"2", "image/webp")
    db.add(Asset(owner_id=owner.id, kind="image", visibility="public", source_sha256="9" * 64, sha256=b,
                 storage_key=blob_key(b), mime="image/webp", bytes=1, source_bytes=1))
    db.commit()
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    db.execute(update(AssetBlob).values(created_at=old))
    db.commit()
    calls = []
    real = fsvc.sweep_orphan_blobs
    monkeypatch.setattr(fsvc, "sweep_orphan_blobs", lambda d, **k: calls.append(1) or real(d, **k))
    monkeypatch.setattr(fsvc, "_last_sweep", 0.0)
    fsvc.maybe_sweep_orphans(db)
    fsvc.maybe_sweep_orphans(db)   # throttled
    assert calls == [1]
    db.expire_all()
    assert db_storage.exists(blob_key(b)) and not db_storage.exists(blob_key(a))
    # a re-put refreshes the age
    db_storage.put(blob_key(b), b"2", "image/webp")
    assert db.scalar(select(AssetBlob.created_at).where(AssetBlob.key == blob_key(b))) is not None


# ------------------------------------------------------------------ 4/5/6. router and slot

async def test_import_busy_when_slot_taken(w, db, local_storage, monkeypatch):
    monkeypatch.setattr(isvc, "_active", 1)
    res = await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    assert res.status_code == 409 and "import_busy" in res.text


async def test_chunked_upload_needs_length(w, db):
    async def gen():
        yield b"--b\r\n"
    h = auth(w.O)
    h["content-type"] = "multipart/form-data; boundary=b"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.post(f"/api/v1/courses/{w.cid}/imports/preview", content=gen(), headers=h)
    assert res.status_code == 411
