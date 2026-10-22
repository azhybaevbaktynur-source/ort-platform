"""Importer writer: preview (read-only plan) and commit (one transaction per upload). Design 3.7, P2-17..P2-25.

Flow: parse (pure) -> encode every new image (commit only; only encoded bytes are kept) -> summed quota/cap check
-> put blobs -> one transaction: per bundle lock the bank, then its questions, then its passages (in that order),
plan every row against the LOCKED rows (matched by source_ref), write versions. Any error found before the blobs
are put returns `ok=false` with nothing written (zero blobs); a failure after the puts deletes the blobs just
written that no asset references.
"""
from __future__ import annotations

import logging
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.content import service as csvc
from app.lms.content.models import BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion
from app.lms.core.errors import Conflict, LMSError
from app.lms.files.images import EncodedImage, encode_image
from app.lms.files.models import Asset
from app.lms.files.storage import blob_key, get_blob_storage

from .bundle import MAX_IMAGE_BYTES, display_root
from .parse import parse_upload
from .parsed import Issues, ParsedBundle, ParsedItem, ParsedUpload
from .report import build_report
from .schemas import ImportBankSummary, ImportOptions, ImportReport

log = logging.getLogger(__name__)
CHUNK = 500


class FileTooLarge(LMSError):
    status_code = 413
    code = "file_too_large"


def _sec(it: ParsedItem) -> str:
    return it.section or "other"


def _bump(d: dict, key: str) -> None:
    d[key] = d.get(key, 0) + 1


def _chunks(items: list, n: int = CHUNK):
    for i in range(0, len(items), n):
        yield items[i:i + n]


# --------------------------------------------------------------------------------------------- images

@dataclass
class ImageInfo:
    source_sha: str
    stored_sha: str
    existing: Optional[Asset] = None          # actor's asset with this source sha (live or deleted)
    encoded: Optional[EncodedImage] = None    # commit only: encoded WebP, not stored yet
    asset: Optional[Asset] = None             # commit only: after ingest


def _existing_assets(db: Session, actor_id: str, shas: list[str]) -> dict[str, Asset]:
    out: dict[str, Asset] = {}
    for part in _chunks(shas):
        for a in db.execute(select(Asset).where(
                Asset.owner_id == actor_id, Asset.visibility == "public", Asset.source_sha256.in_(part))).scalars():
            out[a.source_sha256] = a
    return out


_ENCODE_CODES = {"too_many_pixels": "image_too_many_pixels", "too_large": "image_too_large",
                 "too_large_after_encode": "image_too_large"}


def prepare_images(db: Session, actor_id: str, up: ParsedUpload, *, encode: bool) -> dict[str, ImageInfo]:
    """Decide new/existing per distinct image by source sha. With `encode` (commit) every new image is encoded
    to WebP, one at a time; nothing is stored here. The source bytes of every image are dropped afterwards.
    Without it (preview) new images are only counted (the parser already checked header and pixel count)."""
    distinct: dict[str, tuple[Any, str]] = {}
    for b in up.bundles:
        for img in b.images.values():
            distinct.setdefault(img.source_sha256, (img, display_root(b.root)))
    existing = _existing_assets(db, actor_id, list(distinct))
    infos: dict[str, ImageInfo] = {}
    for sha, (img, broot) in distinct.items():
        ex = existing.get(sha)
        if ex is not None:
            infos[sha] = ImageInfo(sha, ex.sha256, existing=ex)
            continue
        if not encode:
            infos[sha] = ImageInfo(sha, sha)
            continue
        try:
            enc = encode_image(img.content, max_bytes=MAX_IMAGE_BYTES)
        except ValueError as e:
            up.issues.error(_ENCODE_CODES.get(str(e), "image_invalid"), f"Image '{img.path}' cannot be converted ({e}).",
                            bundle=broot, file=img.path)
            continue
        infos[sha] = ImageInfo(sha, enc.sha256, encoded=enc)
    for b in up.bundles:
        for img in b.images.values():
            img.content = b""
    return infos


def store_new_blobs(db: Session, actor_id: str, up: ParsedUpload, infos: dict[str, ImageInfo]) -> list[str]:
    """Summed quota / cap check, then put the blobs. Returns the keys this call newly created. On any problem an
    error issue is recorded and no blob is left behind."""
    from app.lms.files import service as fsvc

    new = [i for i in infos.values() if i.encoded is not None]
    if not new:
        return []
    blobs: dict[str, EncodedImage] = {}
    for i in new:
        blobs.setdefault(blob_key(i.encoded.sha256, "public"), i.encoded)
    try:
        fsvc.check_import_caps(db, actor_id, {k: len(e.data) for k, e in blobs.items()},
                               sum(len(i.encoded.data) for i in new))
    except LMSError as e:
        up.issues.error(e.code, e.message)
        return []
    storage = get_blob_storage()
    written: list[str] = []
    try:
        for key, enc in blobs.items():
            existed = storage.exists(key)
            storage.put(key, enc.data, "image/webp")
            if not existed:
                written.append(key)
    except Exception:
        log.exception("blob put failed")
        fsvc.delete_unreferenced_blobs(db, written)
        up.issues.error("storage_error", "Could not store an image.")
        return []
    return written


# --------------------------------------------------------------------------------------------- planning

@dataclass
class _Ctx:
    db: Session
    actor_id: str
    course: Any
    opts: ImportOptions
    write: bool
    images: dict[str, ImageInfo]
    issues: Issues
    kind: str = "zip"


def _ref_for(info: ImageInfo, prev: Optional[dict]) -> dict:
    """ImageRef for a stored image. Reuse the previous version's asset when it is the same stored image."""
    if prev and prev.get("sha256") == info.stored_sha:
        return {"asset_id": prev["asset_id"], "sha256": prev["sha256"]}
    asset = info.asset or info.existing
    if asset is not None:
        return {"asset_id": str(asset.id), "sha256": asset.sha256}
    # preview of an image that has no asset yet: any id differs from every stored one
    return {"asset_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "preview:" + info.stored_sha)), "sha256": info.stored_sha}


def _question_content(c: _Ctx, it: ParsedItem, prev: Optional[dict]) -> dict:
    image = None
    if it.image is not None:
        image = _ref_for(c.images[it.image.source_sha256], prev)
    return {"type": it.type, "stem": it.stem, "data": it.payload, "explanation": it.explanation,
            "default_points": 1, "image": image}


def _find_bank(db: Session, c: _Ctx, b: ParsedBundle, lock: bool) -> tuple[Optional[QuestionBank], bool]:
    """(bank, created_now). Manifest bundle -> source bank; else target_bank_id or a new bank."""
    from app.lms.content import repository as repo

    course = c.course
    if b.has_manifest:
        stmt = select(QuestionBank).where(QuestionBank.course_id == course.id, QuestionBank.source_id == b.source_id,
                                          QuestionBank.deleted_at.is_(None))
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return db.execute(stmt).scalar_one_or_none(), False
    if c.opts.target_bank_id:
        bank = repo.load_bank(db, course.id, uuid.UUID(c.opts.target_bank_id), for_update=lock)
        return bank, False
    return None, False


def _create_bank(c: _Ctx, b: ParsedBundle) -> QuestionBank:
    bank = QuestionBank(owner_id=c.actor_id, course_id=c.course.id, title=(b.title or "Import")[:200],
                        source_id=b.source_id if b.has_manifest else None, default_language=b.language)
    try:
        with c.db.begin_nested():
            c.db.add(bank)
            c.db.flush()
    except IntegrityError:
        raise Conflict("Another import of this source is running", code="import_busy") from None
    return bank


def _meta_changed(q: BankQuestion, it: ParsedItem, meta: Optional[dict], base: int) -> bool:
    return (q.position, q.q_num, q.section, q.topic, q.difficulty, q.source_meta) != \
           (base + it.position, (it.q_num[:16] if it.q_num else None), (it.section[:40] if it.section else None), (it.topic[:200] or None), it.difficulty, meta)


def _apply_meta(q: BankQuestion, it: ParsedItem, meta: Optional[dict], base: int) -> None:
    q.position = base + it.position
    q.q_num = it.q_num[:16] if it.q_num else None
    q.section = it.section[:40] if it.section else None
    q.topic = it.topic[:200] or None
    q.difficulty = it.difficulty
    q.source_meta = meta   # tags are never refreshed: the teacher owns them after the first import


def _source_meta(it: ParsedItem) -> Optional[dict]:
    if it.source_ref is None:
        return None
    m: dict = {"fixed": it.fixed}
    if it.source_page is not None:
        m["source_page"] = it.source_page
    return m


def _process_bundle(c: _Ctx, b: ParsedBundle) -> ImportBankSummary:
    db = c.db
    secs: dict[str, int] = {}
    for it in b.items:
        _bump(secs, _sec(it))
    summary = ImportBankSummary(
        root=display_root(b.root) if c.kind == "zip" else "",
        source_id=b.source_id, has_manifest=b.has_manifest, language=b.language, bank_title=b.title,
        question_count=len(b.items), sections=secs,
        images=len({i.source_sha256 for i in b.images.values()}),
    )
    bank, _ = _find_bank(db, c, b, lock=c.write)
    if bank is None and c.write:
        bank = _create_bank(c, b)
        if b.has_manifest:  # lock the row we just created (also makes the later reads see a stable bank)
            db.refresh(bank, with_for_update=True)
    summary.bank_exists = bank is not None
    summary.bank_id = str(bank.id) if bank is not None else None
    if bank is not None:
        summary.bank_title = bank.title
    created, updated, unchanged, conflicts, skipped = {}, {}, {}, {}, {}
    broot = display_root(b.root) if b.root else ("/" if b.has_manifest else "")

    # ---- existing rows: lock order bank -> questions (by id) -> passages (by id), before any write
    refs = [it.source_ref for it in b.items if it.source_ref]
    existing_q: dict[str, BankQuestion] = {}
    existing_p: dict[str, Passage] = {}
    base = 0
    if bank is not None:
        qstmt = select(BankQuestion).where(BankQuestion.bank_id == bank.id, BankQuestion.source_ref.is_not(None))
        pstmt = select(Passage).where(Passage.bank_id == bank.id, Passage.source_ref.is_not(None))
        if c.write:
            qstmt = qstmt.with_for_update(of=BankQuestion).execution_options(populate_existing=True)
            pstmt = pstmt.with_for_update(of=Passage).execution_options(populate_existing=True)
        for q in db.execute(qstmt.order_by(BankQuestion.id)).scalars():
            existing_q[q.source_ref] = q
        for p in db.execute(pstmt.order_by(Passage.id)).scalars():
            existing_p[p.source_ref] = p
        if not b.has_manifest:
            base = db.execute(select(func.max(BankQuestion.position)).where(BankQuestion.bank_id == bank.id)).scalar() or 0
    vids = [q.current_version_id for q in existing_q.values() if q.current_version_id]
    vids += [q.imported_version_id for q in existing_q.values() if q.imported_version_id]
    from app.lms.content import repository as repo

    qver = repo.load_versions(db, vids)
    pvids = [p.current_version_id for p in existing_p.values() if p.current_version_id]
    pvids += [p.imported_version_id for p in existing_p.values() if p.imported_version_id]
    pver = repo.load_passage_versions(db, pvids)

    # ---- passages first
    passage_by_key: dict[str, Optional[Passage]] = {}
    deleted_keys: set[str] = set()
    p_conf = p_del = 0
    for pp in b.passages:
        content = {"title": None, "body": pp.text, "image": None}
        phash = csvc.passage_content_hash(b.language, content)
        ex = existing_p.get(pp.source_ref) if pp.source_ref else None
        if ex is not None and ex.deleted_at is not None:
            p_del += 1
            passage_by_key[pp.key] = None
            deleted_keys.add(pp.key)
            continue
        if ex is None:
            if c.write:
                ex = Passage(bank_id=bank.id, language=b.language, source_ref=pp.source_ref)
                db.add(ex)
                db.flush()
                v = csvc.new_passage_version(db, ex, content, actor_id=c.actor_id, origin="import")
                ex.imported_version_id = v.id
            passage_by_key[pp.key] = ex
            continue
        cur = pver.get(ex.current_version_id)
        imp = pver.get(ex.imported_version_id) if ex.imported_version_id else None
        if cur is not None and cur.content_hash == phash:
            pass
        elif imp is not None and imp.content_hash == phash:
            pass
        elif ex.current_version_id == ex.imported_version_id or c.opts.on_conflict == "overwrite":
            if c.write:
                v = csvc.new_passage_version(db, ex, content, actor_id=c.actor_id, origin="import")
                ex.imported_version_id = v.id
        else:
            p_conf += 1
        passage_by_key[pp.key] = ex
    if p_conf:
        c.issues.warning("question_edited_locally", f"{p_conf} passage(s) were edited in the platform and kept.",
                         bundle=broot, params={"count": p_conf, "kind": "passage"})
    if p_del:
        c.issues.warning("question_deleted_skipped", f"{p_del} deleted passage(s) were skipped.",
                         bundle=broot, params={"count": p_del, "kind": "passage"})

    # ---- questions
    edited_rows: list[int] = []
    deleted_rows: list[int] = []
    passage_skipped: list[int] = []
    for it in b.items:
        sec = _sec(it)
        meta = _source_meta(it)
        ex = existing_q.get(it.source_ref) if it.source_ref else None
        passage = passage_by_key.get(it.passage_key) if it.passage_key else None
        if ex is not None and ex.deleted_at is not None:
            _bump(skipped, sec)
            deleted_rows.append(it.row)
            continue
        if ex is None and it.passage_key and it.passage_key in deleted_keys:
            _bump(skipped, sec)
            passage_skipped.append(it.row)
            continue
        if ex is None:
            _bump(created, sec)
            if c.write:
                q = BankQuestion(
                    bank_id=bank.id, passage_id=passage.id if passage is not None else None, type=it.type,
                    language=b.language, tags=list(it.tags), position=base + it.position, source_ref=it.source_ref,
                    search_text="",
                )
                _apply_meta(q, it, meta, base)
                db.add(q)
                db.flush()
                v = csvc.new_question_version(db, q, _question_content(c, it, None), actor_id=c.actor_id,
                                              origin="import")
                q.imported_version_id = v.id
            continue
        cur = qver.get(ex.current_version_id)
        imp = qver.get(ex.imported_version_id) if ex.imported_version_id else None
        content = _question_content(c, it, cur.image if cur is not None else None)
        new_hash = csvc.question_content_hash(ex.language, content)
        if cur is not None and cur.content_hash == new_hash:
            action = "unchanged"
        elif imp is not None and cur is not None and imp.id != cur.id and imp.content_hash == new_hash:
            action = "unchanged"   # the source did not change; the teacher's edit stays
        elif ex.current_version_id == ex.imported_version_id:
            action = "updated"
        elif c.opts.on_conflict == "overwrite":
            action = "updated"
        else:
            action = "conflict"
        if action == "conflict":
            _bump(conflicts, sec)
            edited_rows.append(it.row)
            continue
        _bump(updated if action == "updated" else unchanged, sec)
        if c.write:
            if action == "updated":
                v = csvc.new_question_version(db, ex, content, actor_id=c.actor_id, origin="import")
                ex.imported_version_id = v.id
            if passage is not None and ex.passage_id != passage.id:
                ex.passage_id = passage.id
            if _meta_changed(ex, it, meta, base):
                _apply_meta(ex, it, meta, base)
                cv = qver.get(ex.current_version_id) if action == "unchanged" else None
                ver = cv or db.get(QuestionVersion, ex.current_version_id)
                ex.search_text = csvc.build_search_text(ver.stem, ver.type, ver.data, ex.topic, ex.q_num)
    if edited_rows:
        c.issues.warning("question_edited_locally",
                         f"{len(edited_rows)} question(s) were edited in the platform since the last import and were kept.",
                         bundle=broot, params={"count": len(edited_rows), "rows": edited_rows[:50]})
    if deleted_rows:
        c.issues.warning("question_deleted_skipped", f"{len(deleted_rows)} deleted question(s) were skipped.",
                         bundle=broot, params={"count": len(deleted_rows), "rows": deleted_rows[:50]})
    if passage_skipped:
        c.issues.warning("question_deleted_skipped",
                         f"{len(passage_skipped)} question(s) linked to a deleted passage were skipped.",
                         bundle=broot, params={"count": len(passage_skipped), "rows": passage_skipped[:50],
                                               "kind": "passage", "reason": "passage_deleted"})
    if b.has_manifest and bank is not None:
        in_bundle = set(refs)
        missing = sorted(r for r, q in existing_q.items() if q.deleted_at is None and r not in in_bundle)
        if missing:
            c.issues.warning("questions_missing_from_bundle",
                             f"{len(missing)} question(s) of source '{b.source_id}' imported earlier are not in this "
                             f"bundle; they are kept unchanged.", bundle=broot,
                             params={"count": len(missing), "source_id": b.source_id, "external_ids": missing[:50]})
    summary.created, summary.updated, summary.unchanged = created, updated, unchanged
    summary.conflicts, summary.skipped_deleted = conflicts, skipped
    return summary


_active = 0
_active_lock = threading.Lock()


@contextmanager
def _import_slot():
    """Process-wide limit on concurrent imports (preview or commit); non-blocking."""
    global _active
    with _active_lock:
        if _active >= max(1, settings.IMPORT_MAX_CONCURRENT):
            raise Conflict("Another import is running; try again in a moment", code="import_busy")
        _active += 1
    try:
        yield
    finally:
        with _active_lock:
            _active -= 1


def _take(raw: Any) -> bytes:
    """The router passes a one-item list so the caller's reference can be released while we work."""
    return raw.pop() if isinstance(raw, list) else raw


def _ingest_all(db: Session, actor_id: str, course: Any, images: dict[str, ImageInfo]) -> None:
    from app.lms.files import service as fsvc
    from app.models.user import User

    actor = db.get(User, actor_id)
    for info in images.values():
        if info.existing is not None:
            if info.existing.deleted_at is not None:
                info.existing.restore()  # its bytes were never released from the quota
                db.flush()
            info.asset = info.existing
        else:
            info.asset, _ = fsvc.ingest_image(db, actor, b"", course_id=course.id, encoded=info.encoded,
                                              precheck_done=True)
        info.encoded = None


def _run(db: Session, actor_id: str, course: Any, raw: Any, filename: str, opts: ImportOptions,
         write: bool) -> ImportReport:
    with _import_slot():
        raw = _take(raw)
        if opts.allowed_languages is None:
            opts = opts.model_copy(update={"allowed_languages": list(course.languages or [])})
        up = parse_upload(raw, filename, opts)
        del raw
        if up.issues.errors:
            return build_report(up)
        images = prepare_images(db, actor_id, up, encode=write)
        up.issues.finalize()
        if up.issues.errors:
            return build_report(up)
        written: list[str] = []
        if write:
            from app.lms.files import service as fsvc

            fsvc.maybe_sweep_orphans(db)
            written = store_new_blobs(db, actor_id, up, images)
            up.issues.finalize()
            if up.issues.errors:
                return build_report(up)
        c = _Ctx(db, actor_id, course, opts, write, images, up.issues, up.kind)
        summaries: list[ImportBankSummary] = []
        try:
            if write:
                _ingest_all(db, actor_id, course, images)
            for b in up.bundles:
                summaries.append(_process_bundle(c, b))
            if write:
                db.commit()
        except BaseException as exc:
            db.rollback()
            # not after a lost race with another importer of the same source: it may hold the same blobs; the
            # hourly orphan sweep removes them if nothing references them
            if written and not isinstance(exc, (IntegrityError, Conflict)):
                from app.lms.files import service as fsvc

                fsvc.delete_unreferenced_blobs(db, written)
            if isinstance(exc, IntegrityError):
                raise Conflict("Another import of this source is running", code="import_busy") from None
            raise
        up.issues.finalize()
        rep = build_report(up, committed=write)
        rep.banks = summaries
        new = sum(1 for i in images.values() if i.existing is None)
        rep.images_total, rep.images_new, rep.images_existing = len(images), new, len(images) - new
        return rep


def preview(db: Session, ctx: Any, course: Any, raw: Any, filename: str, opts: ImportOptions) -> ImportReport:
    """Parse + validate + read-only plan: no locks, no encoding, nothing written."""
    rep = _run(db, ctx.user.id, course, raw, filename, opts, write=False)
    db.rollback()
    return rep


def commit(db: Session, ctx: Any, course: Any, raw: Any, filename: str, opts: ImportOptions) -> ImportReport:
    """Any error -> report.ok false and nothing written (zero blobs); otherwise one transaction."""
    return _run(db, ctx.user.id, course, raw, filename, opts, write=True)
