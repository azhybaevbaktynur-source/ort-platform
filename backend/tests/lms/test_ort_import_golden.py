"""ORT golden import fixtures (PHASE_6_DESIGN section 6, "Golden import fixtures"; rule 9: ORT must not change).

The repo's ORT CSV samples (`sample_ort_questions.csv` ky, `sample_ort_questions_ru.csv` ru) and the digitizer bundle
`tests/fixtures/bundles/tsoomo19.zip` are imported into the platform ORT courses exactly as production does (the
seeded `ORT (ky)` / `ORT (ru)` courses, a platform admin co-teacher, `POST /courses/{id}/imports` with
`exam_type=full_main`). The resulting banks, questions, versions, passages and assets are reduced to a deterministic
JSON table (no uuids, no timestamps) and compared with the frozen tables
`tests/lms/fixtures/ort_import_golden_{csv,zip}.json`, which were generated once from the pre-Phase-6 importer code.

Volatile values left out: row ids, timestamps, the stored WebP bytes/sha256 (they depend on the local libwebp build;
the source image sha256 is frozen instead). Image references inside versions are replaced by the source sha256 of
their asset; for versions that reference an asset, `content_hash` is recomputed with the asset id replaced by
uuid5(source sha256) (`content_hash_asset_normalized`), the stored hash is frozen as-is everywhere else.

Regenerate (only for a deliberate, owner-approved ORT change):
    ORT_GOLDEN_WRITE=1 pytest tests/lms/test_ort_import_golden.py
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.lms.content import service as csvc
from app.lms.content.importers import ImportOptions, parse_upload
from app.lms.content.models import BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion
from app.lms.files.models import Asset
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from app.main import app
from tests.lms.factories import auth, make_user
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FIXTURES = Path(__file__).parent / "fixtures"
CSV_SAMPLES = {"ky": REPO / "sample_ort_questions.csv", "ru": REPO / "sample_ort_questions_ru.csv"}
BUNDLE = BACKEND / "tests" / "fixtures" / "bundles" / "tsoomo19.zip"
WRITE = os.environ.get("ORT_GOLDEN_WRITE") == "1"
ASSET_NS = uuid.UUID("6f1d6c58-3f0e-5b8e-9a51-0c2b9f6a7d10")


# ------------------------------------------------------------------------------------------------ import (HTTP)

async def import_file(user, course_id: uuid.UUID, data: bytes, filename: str, language: str, *,
                      commit: bool = True) -> dict:
    h = auth(user)
    h["x-forwarded-for"] = "10.77.1.1, 10.255.255.1"
    path = f"/api/v1/courses/{course_id}/imports" + ("" if commit else "/preview")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(path, files={"file": (filename, data, "application/octet-stream")},
                         data={"language": language, "exam_type": "full_main"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def ort_teacher(db):
    """A platform admin, co-teacher of both ORT courses after the seed (the production import path)."""
    admin = make_user(db, platform_admin=True, teacher_status="approved")
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok, rep
    return admin


# ------------------------------------------------------------------------------------------------ snapshot

def _sha(text: Optional[str]) -> Optional[str]:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_ref(v: Any) -> bool:
    return isinstance(v, dict) and set(v) == {"asset_id", "sha256"}


def _norm_refs(value: Any, assets: dict[str, Asset]) -> Any:
    """ImageRefs -> {"asset_source_sha256": ...} (asset ids and WebP hashes are volatile)."""
    if _is_ref(value):
        a = assets[str(value["asset_id"])]
        assert value["sha256"] == a.sha256  # the ref points at the stored image
        return {"asset_source_sha256": a.source_sha256}
    if isinstance(value, dict):
        return {k: _norm_refs(v, assets) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm_refs(v, assets) for v in value]
    return value


def _stable_ids(value: Any, assets: dict[str, Asset]) -> Any:
    """ImageRefs with the asset id replaced by uuid5(source sha256): input for a run-independent content hash."""
    if _is_ref(value):
        a = assets[str(value["asset_id"])]
        return {"asset_id": str(uuid.uuid5(ASSET_NS, a.source_sha256)), "sha256": value["sha256"]}
    if isinstance(value, dict):
        return {k: _stable_ids(v, assets) for k, v in value.items()}
    if isinstance(value, list):
        return [_stable_ids(v, assets) for v in value]
    return value


def _has_ref(v: Any) -> bool:
    return bool(csvc.collect_refs(v))


def _question_version(v: QuestionVersion, lang: str, assets: dict[str, Asset]) -> dict:
    out = {
        "version_no": v.version_no, "language": v.language, "type": v.type, "schema_version": v.schema_version,
        "stem": v.stem, "data": _norm_refs(v.data, assets), "explanation": v.explanation,
        "default_points": str(v.default_points), "image": _norm_refs(v.image, assets), "origin": v.origin,
    }
    if _has_ref(v.data) or v.image:
        content = {"type": v.type, "stem": v.stem, "data": _stable_ids(v.data, assets), "explanation": v.explanation,
                   "default_points": v.default_points, "image": _stable_ids(v.image, assets)}
        out["content_hash"] = None
        out["content_hash_asset_normalized"] = csvc.question_content_hash(lang, content)
    else:
        out["content_hash"] = v.content_hash
    return out


def _passage_key(p: Passage, versions: list[PassageVersion]) -> str:
    return p.source_ref or ("body:" + _sha(versions[0].body))


def snapshot(db, course_ids: list[uuid.UUID]) -> dict:
    """Deterministic table of everything the importer wrote into these courses."""
    db.expire_all()
    banks = list(db.scalars(select(QuestionBank).where(QuestionBank.course_id.in_(course_ids))))
    lang_of = {course_id_for(lang): lang for lang in ("ky", "ru")}
    banks.sort(key=lambda b: (lang_of.get(b.course_id, ""), b.source_id or "", b.title, b.created_at))
    bank_ids = [b.id for b in banks]
    assets = {str(a.id): a for a in db.scalars(select(Asset).where(Asset.course_id.in_(course_ids)))}
    passages = list(db.scalars(select(Passage).where(Passage.bank_id.in_(bank_ids)))) if bank_ids else []
    pvers: dict[uuid.UUID, list[PassageVersion]] = {}
    for pv in db.scalars(select(PassageVersion).where(PassageVersion.passage_id.in_([p.id for p in passages]))):
        pvers.setdefault(pv.passage_id, []).append(pv)
    for lst in pvers.values():
        lst.sort(key=lambda x: x.version_no)
    pkey = {p.id: _passage_key(p, pvers[p.id]) for p in passages}
    pver_no = {pv.id: pv.version_no for lst in pvers.values() for pv in lst}

    out_banks = []
    for b in banks:
        qs = list(db.scalars(select(BankQuestion).where(BankQuestion.bank_id == b.id)))
        qs.sort(key=lambda q: (q.position, q.source_ref or ""))
        qvers: dict[uuid.UUID, list[QuestionVersion]] = {}
        for v in db.scalars(select(QuestionVersion).where(QuestionVersion.question_id.in_([q.id for q in qs]))):
            qvers.setdefault(v.question_id, []).append(v)
        bank_passages = sorted((p for p in passages if p.bank_id == b.id), key=lambda p: pkey[p.id])
        out_q = []
        for q in qs:
            vs = sorted(qvers[q.id], key=lambda x: x.version_no)
            by_id = {v.id: v.version_no for v in vs}
            out_q.append({
                "source_ref": q.source_ref, "position": q.position, "q_num": q.q_num, "section": q.section,
                "type": q.type, "language": q.language, "topic": q.topic, "difficulty": q.difficulty,
                "tags": list(q.tags or []), "source_meta": q.source_meta, "search_text_sha256": _sha(q.search_text),
                "passage": pkey[q.passage_id] if q.passage_id else None,
                "current_version_no": by_id.get(q.current_version_id),
                "imported_version_no": by_id.get(q.imported_version_id),
                "deleted": q.deleted_at is not None,
                "versions": [_question_version(v, q.language, assets) for v in vs],
            })
        out_p = []
        for p in bank_passages:
            vs = pvers[p.id]
            out_p.append({
                "key": pkey[p.id], "source_ref": p.source_ref, "language": p.language,
                "current_version_no": pver_no.get(p.current_version_id),
                "imported_version_no": pver_no.get(p.imported_version_id),
                "questions": sum(1 for q in qs if q.passage_id == p.id),
                "versions": [{"version_no": v.version_no, "language": v.language, "title": v.title,
                              "body_sha256": _sha(v.body), "body_chars": len(v.body),
                              "image": _norm_refs(v.image, assets), "content_hash": v.content_hash,
                              "origin": v.origin} for v in vs],
            })
        out_banks.append({
            "course_language": lang_of.get(b.course_id), "title": b.title, "source_id": b.source_id,
            "default_language": b.default_language, "description": b.description,
            "questions": out_q, "passages": out_p,
        })
    out_assets = sorted(({"source_sha256": a.source_sha256, "kind": a.kind, "visibility": a.visibility,
                          "mime": a.mime, "extension": a.extension, "width": a.width, "height": a.height,
                          "source_bytes": a.source_bytes, "original_filename": a.original_filename}
                         for a in assets.values()), key=lambda a: a["source_sha256"])
    n_q = sum(len(b["questions"]) for b in out_banks)
    counts = {
        "banks": len(out_banks), "questions": n_q,
        "question_versions": sum(len(q["versions"]) for b in out_banks for q in b["questions"]),
        "passages": sum(len(b["passages"]) for b in out_banks),
        "passage_versions": sum(len(p["versions"]) for b in out_banks for p in b["passages"]),
        "assets": len(out_assets),
        "max_question_version_no": db.scalar(select(func.max(QuestionVersion.version_no))) or 0,
        "by_section": {}, "by_type": {},
    }
    for b in out_banks:
        for q in b["questions"]:
            counts["by_section"][q["section"]] = counts["by_section"].get(q["section"], 0) + 1
            counts["by_type"][q["type"]] = counts["by_type"].get(q["type"], 0) + 1
    return {"counts": counts, "banks": out_banks, "assets": out_assets}


def report_view(rep: dict) -> dict:
    """The import report without ids."""
    banks = [{k: v for k, v in b.items() if k != "bank_id"} for b in rep.get("banks") or []]
    return {**{k: v for k, v in rep.items() if k != "banks"}, "banks": banks}


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def check_or_write(name: str, actual: dict) -> None:
    path = FIXTURES / name
    if WRITE:
        path.write_text(_dump(actual), encoding="utf-8")
        return
    frozen = json.loads(path.read_text(encoding="utf-8"))
    actual = json.loads(_dump(actual))
    for part in sorted(set(frozen) | set(actual)):
        assert actual.get(part) == frozen.get(part), f"{name}: '{part}' differs from the frozen ORT import"


# ------------------------------------------------------------------------------------------------ tests

async def test_csv_samples_import_like_frozen(db):
    admin = ort_teacher(db)
    cids = [course_id_for("ky"), course_id_for("ru")]
    out: dict = {"files": {}, "first": {}, "second": {}}
    for lang in ("ky", "ru"):
        data = CSV_SAMPLES[lang].read_bytes()
        out["files"][lang] = {"name": CSV_SAMPLES[lang].name, "sha256": hashlib.sha256(data).hexdigest()}
        out.setdefault("preview", {})[lang] = report_view(
            await import_file(admin, course_id_for(lang), data, CSV_SAMPLES[lang].name, lang, commit=False))
        out["first"][lang] = report_view(await import_file(admin, course_id_for(lang), data, CSV_SAMPLES[lang].name, lang))
    out["after_first"] = snapshot(db, cids)
    # today's behaviour: a plain CSV has no manifest/source_ref, so a second upload of the same file (no target bank)
    # makes a second bank with new questions; it is NOT an upsert (frozen as-is)
    for lang in ("ky", "ru"):
        data = CSV_SAMPLES[lang].read_bytes()
        out["second"][lang] = report_view(await import_file(admin, course_id_for(lang), data, CSV_SAMPLES[lang].name, lang))
    out["after_second"] = snapshot(db, cids)
    first, second = out["after_first"]["counts"], out["after_second"]["counts"]
    assert second["banks"] == 2 * first["banks"] and second["questions"] == 2 * first["questions"]
    assert first["questions"] == 50 and first["by_type"]["comparison"] == 14
    check_or_write("ort_import_golden_csv.json", out)


async def test_bundle_zip_import_like_frozen_and_reimport_is_noop(db):
    admin = ort_teacher(db)
    cid = course_id_for("ru")
    data = BUNDLE.read_bytes()
    out: dict = {"file": {"name": BUNDLE.name, "sha256": hashlib.sha256(data).hexdigest()}}
    out["preview"] = report_view(await import_file(admin, cid, data, BUNDLE.name, "ru", commit=False))
    out["first"] = report_view(await import_file(admin, cid, data, BUNDLE.name, "ru"))
    out["after_first"] = snapshot(db, [cid])
    # same zip again: an upsert by source_ref that changes nothing (no new banks, questions, versions or assets)
    out["second"] = report_view(await import_file(admin, cid, data, BUNDLE.name, "ru"))
    after_second = snapshot(db, [cid])
    assert after_second == out["after_first"]
    assert out["second"]["banks"][0]["created"] == {} and out["second"]["banks"][0]["updated"] == {}
    assert out["second"]["images_new"] == 0
    c = out["after_first"]["counts"]
    assert (c["banks"], c["questions"], c["question_versions"], c["passages"], c["assets"]) == (1, 150, 150, 3, 14)
    check_or_write("ort_import_golden_zip.json", out)


def test_importer_keeps_double_backslash_verbatim():
    """Freezes today's importer: CSV text is stored as written, a `\\\\frac` stays `\\\\frac` (the old dev samples had
    double backslashes; they were fixed in the sample files, never in the importer)."""
    csv_text = ("section,stem,option_a,option_b,option_c,option_d,correct_option\n"
                'math_2,"$\\\\frac{3}{4} + \\frac{1}{2}$",a,b,c,d,A\n')
    up = parse_upload(csv_text.encode("utf-8"), "x.csv", ImportOptions(exam_type="full_main", language="ru",
                                                                       allowed_languages=["ru"]))
    assert up.issues.errors == []
    assert up.bundles[0].items[0].stem == "$\\\\frac{3}{4} + \\frac{1}{2}$"
