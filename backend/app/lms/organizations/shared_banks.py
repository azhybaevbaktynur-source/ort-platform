"""Phase 9 S2: organization-shared question banks (PHASE_9_DESIGN 4.2, invariants 1-3, P9-2, P9-3, P9-9).

- `share_bank` / `unshare_bank`: the home course's staff or an org admin of the tree (`can_edit_bank`, checked by
  the router); never a quiz bank (`quiz_bank_not_shareable`), never an ORT or sandbox course (`template_locked`),
  never a personal organization (`sharing_disabled`, 422), and only while the root setting `bank_sharing_enabled`
  is on (`sharing_disabled`, 409). Unsharing leaves copies untouched.
- Reads: a teacher or org admin of a tree reads every bank shared inside that whole tree
  (`content.repository.shared_banks_visible_to`, the one SQL scope); anyone else gets the 404 of a missing org.
- `copy_bank`: copy only (no cross-course linking): a new private bank in the target course, passages and questions
  in `position` order with one new version each (content as is, assets referenced by id), `source_ref` dropped,
  translation groups re-created inside the copy only; <= 2,000 questions (`bank_too_large`), flushed in chunks of
  200; rate `bank_copy_1h` per actor."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.lms.audit import service as audit
from app.lms.content import repository as repo
from app.lms.content.models import (
    BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion, TranslationGroup,
)
from app.lms.core import ratelimit
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.organizations import ids
from app.lms.organizations import service as org_svc
from app.lms.organizations import tree
from app.lms.organizations.models import Organization
from app.models.user import User

E_TEMPLATE_LOCKED = "template_locked"   # reused 6a code: ORT template and exam-template sandbox courses
COPY_SUFFIX = " (copy)"
TITLE_MAX = 200


def copy_limit() -> ratelimit.Limit:
    return ratelimit.Limit("bank_copy_1h", ids.BANK_COPY_RATE_PER_HOUR, 3600)


def bank_not_found() -> NotFound:
    return NotFound("Bank not found", code="bank_not_found")


# ------------------------------------------------------------------ sharing state

def sharing_state(db: Session, course) -> tuple[bool, Optional[str], Organization]:
    """(sharing available for this course's banks, refusal reason or None, root organization). Reasons:
    `template_locked` (ORT or sandbox course), `personal` (personal organization), `setting_off` (root setting)."""
    from app.lms.organizations.settings import effective_settings

    org = db.get(Organization, course.organization_id)
    root = tree.load_root(db, org)
    if course.template_key == "ort" or course.sandbox_for_template_id is not None:
        return False, "template_locked", root
    if root.kind == "personal" or org.kind == "personal":
        return False, "personal", root
    if not effective_settings(root.settings, root.kind).bank_sharing_enabled:
        return False, "setting_off", root
    return True, None, root


def _assert_can_share(db: Session, course, bank: QuestionBank) -> None:
    from app.lms.quiz_editor.quiz_banks import assert_shareable

    assert_shareable(bank)
    ok, reason, _root = sharing_state(db, course)
    if ok:
        return
    if reason == "template_locked":
        raise ValidationFailed("Banks of this course cannot be shared", code=E_TEMPLATE_LOCKED,
                               details=[{"loc": ["course_id"], "msg": E_TEMPLATE_LOCKED}])
    if reason == "personal":
        raise ValidationFailed("Personal organizations cannot share banks", code=ids.E_SHARING_DISABLED,
                               details=[{"loc": ["bank_id"], "msg": ids.E_SHARING_DISABLED}])
    raise Conflict("Bank sharing is turned off in this organization", code=ids.E_SHARING_DISABLED)


def share_bank(db: Session, ctx: AuthzContext, course, bank_id: uuid.UUID, request: Optional[Request]) -> None:
    bank = repo.load_bank(db, course.id, bank_id, for_update=True)
    if bank.visibility == "organization":
        db.commit()
        return  # idempotent
    _assert_can_share(db, course, bank)
    bank.visibility, bank.shared_at, bank.shared_by_id = "organization", utcnow(), ctx.user.id
    audit.record(db, actor=ctx.user, action="bank.shared", target_type="course", target_id=str(course.id),
                 details={"organization_id": str(bank.organization_id), "course_id": str(course.id),
                          "bank_id": str(bank.id)},
                 request=request)
    db.commit()


def unshare_bank(db: Session, ctx: AuthzContext, course, bank_id: uuid.UUID, request: Optional[Request]) -> None:
    """Back to private (refusals are never needed: anyone allowed to edit may stop sharing). Copies stay."""
    bank = repo.load_bank(db, course.id, bank_id, for_update=True)
    if bank.visibility == "private":
        db.commit()
        return
    bank.visibility, bank.shared_at, bank.shared_by_id = "private", None, None
    audit.record(db, actor=ctx.user, action="bank.unshared", target_type="course", target_id=str(course.id),
                 details={"organization_id": str(bank.organization_id), "course_id": str(course.id),
                          "bank_id": str(bank.id)},
                 request=request)
    db.commit()


# ------------------------------------------------------------------ reads (members of the tree)

def reader_root(db: Session, user: User, organization_id: uuid.UUID) -> Organization:
    """The root of `organization_id`'s tree when the caller has an active membership somewhere in that tree
    (teacher or org admin); everyone else, the platform admin included, gets the 404 of a missing organization."""
    org = db.execute(select(Organization).where(
        Organization.id == organization_id, Organization.deleted_at.is_(None))).scalar_one_or_none()
    if org is None or org.kind == "personal":
        raise org_svc.org_not_found()
    rid = tree.root_id(org.path)
    if rid not in tree.member_tree_roots(db, user.id):
        raise org_svc.org_not_found()
    return tree.load_root(db, org)


def visible_banks_stmt(db: Session, user: User, root: Organization, q: Optional[str] = None):
    stmt = repo.shared_banks_visible_to(db, user.id, root_ids=[root.id])
    needle = (q or "").strip().lower()
    if needle:
        stmt = stmt.where(func.lower(QuestionBank.title).like(f"%{repo.like_escape(needle)}%", escape="\\"))
    return stmt


def load_visible_bank(db: Session, user: User, root: Organization, bank_id: uuid.UUID):
    row = db.execute(visible_banks_stmt(db, user, root).where(QuestionBank.id == bank_id)).first()
    if row is None:
        raise bank_not_found()
    return row


# ------------------------------------------------------------------ copy into a course

def copy_bank(db: Session, ctx: AuthzContext, course, source_bank_id: uuid.UUID,
              request: Optional[Request]) -> QuestionBank:
    """One transaction (design 4.2). The caller holds `course:content.manage` on the target course (router)."""
    from app.lms.courses import service as course_svc

    if course.template_key == "ort" or course.sandbox_for_template_id is not None:
        raise ValidationFailed("Banks cannot be copied into this course", code=E_TEMPLATE_LOCKED,
                               details=[{"loc": ["course_id"], "msg": E_TEMPLATE_LOCKED}])
    actor = ctx.user
    db.commit()  # the rate limiter needs a session without uncommitted writes
    ratelimit.enforce(f"bank_copy:{actor.id}", copy_limit())
    row = db.execute(repo.shared_banks_visible_to(db, actor.id).where(QuestionBank.id == source_bank_id)).first()
    if row is None:
        raise bank_not_found()
    src: QuestionBank = row[0]
    # Phase 9 fix 2 (Info): copies stay inside the source's tree (design 4.2); another tree's bank is not found
    paths = dict(db.execute(select(Organization.id, Organization.path).where(
        Organization.id.in_([src.organization_id, course.organization_id]))).all())
    src_path, dst_path = paths.get(src.organization_id), paths.get(course.organization_id)
    if not src_path or not dst_path or tree.root_id(src_path) != tree.root_id(dst_path):
        raise bank_not_found()
    q_ids = list(db.execute(select(BankQuestion.id).where(
        BankQuestion.bank_id == src.id, BankQuestion.deleted_at.is_(None))
        .order_by(BankQuestion.position, BankQuestion.id).limit(ids.BANK_COPY_MAX_QUESTIONS + 1)).scalars())
    if len(q_ids) > ids.BANK_COPY_MAX_QUESTIONS:
        raise ValidationFailed("The bank is too large to copy", code=ids.E_BANK_TOO_LARGE,
                               details={"max_questions": ids.BANK_COPY_MAX_QUESTIONS})
    languages = set(db.execute(select(BankQuestion.language).where(
        BankQuestion.bank_id == src.id, BankQuestion.deleted_at.is_(None)).distinct()).scalars())
    languages |= set(db.execute(select(Passage.language).where(
        Passage.bank_id == src.id, Passage.deleted_at.is_(None)).distinct()).scalars())
    missing = sorted(languages - set(course.languages or []))
    if missing:
        raise ValidationFailed("The bank has questions in languages this course does not use",
                               code="language_not_in_course", details={"languages": missing})
    course_svc.lock_course(db, course)
    if course.deleted_at is not None:
        raise course_svc.not_found_course()
    now = utcnow()
    title = src.title[:TITLE_MAX - len(COPY_SUFFIX)] + COPY_SUFFIX
    bank = QuestionBank(
        owner_id=actor.id, course_id=course.id, organization_id=course.organization_id, title=title,
        description=src.description,
        default_language=src.default_language if src.default_language in (course.languages or []) else None,
        visibility="private", copied_from_bank_id=src.id,
    )
    db.add(bank)
    db.flush()

    # passages (live ones, current version), old id -> new id
    passage_map: dict[uuid.UUID, uuid.UUID] = {}
    p_rows = db.execute(select(Passage, PassageVersion).join(
        PassageVersion, PassageVersion.id == Passage.current_version_id).where(
        Passage.bank_id == src.id, Passage.deleted_at.is_(None)).order_by(Passage.created_at, Passage.id)).all()
    for start in range(0, len(p_rows), ids.BANK_COPY_CHUNK):
        chunk = p_rows[start:start + ids.BANK_COPY_CHUNK]
        new_ps = []
        for p, _pv in chunk:
            np = Passage(id=uuid.uuid4(), bank_id=bank.id, language=p.language)
            passage_map[p.id] = np.id
            new_ps.append(np)
        db.add_all(new_ps)
        db.flush()
        new_vs = []
        for (p, pv), np in zip(chunk, new_ps):
            nv = PassageVersion(id=uuid.uuid4(), passage_id=np.id, version_no=1, language=pv.language,
                                title=pv.title, body=pv.body, image=pv.image, content_hash=pv.content_hash,
                                origin="create", created_by_id=actor.id, created_at=now)
            new_vs.append(nv)
        db.add_all(new_vs)
        db.flush()  # versions first: the FK `current_version_id` is not deferred on PostgreSQL (service pattern)
        for nv, np in zip(new_vs, new_ps):
            np.current_version_id = nv.id
        db.flush()

    # translation groups: re-created inside the copy for groups with at least two copied members
    group_counts = dict(db.execute(select(BankQuestion.translation_group_id, func.count()).where(
        BankQuestion.bank_id == src.id, BankQuestion.deleted_at.is_(None),
        BankQuestion.translation_group_id.is_not(None)).group_by(BankQuestion.translation_group_id)).all())
    group_map: dict[uuid.UUID, uuid.UUID] = {}
    for gid, n in group_counts.items():
        if n >= 2:
            g = TranslationGroup(id=uuid.uuid4(), course_id=course.id, created_by_id=actor.id)
            db.add(g)
            group_map[gid] = g.id
    db.flush()

    position = 0
    for start in range(0, len(q_ids), ids.BANK_COPY_CHUNK):
        part = q_ids[start:start + ids.BANK_COPY_CHUNK]
        rows = db.execute(select(BankQuestion, QuestionVersion).join(
            QuestionVersion, QuestionVersion.id == BankQuestion.current_version_id)
            .where(BankQuestion.id.in_(part))).all()
        by_id = {r[0].id: r for r in rows}
        pairs = [by_id[i] for i in part if i in by_id]
        new_qs = []
        for q, _v in pairs:
            position += 1
            nq = BankQuestion(
                id=uuid.uuid4(), bank_id=bank.id, passage_id=passage_map.get(q.passage_id) if q.passage_id else None,
                translation_group_id=group_map.get(q.translation_group_id) if q.translation_group_id else None,
                type=q.type, language=q.language, topic=q.topic, difficulty=q.difficulty, section=q.section,
                tags=list(q.tags or []), position=position, q_num=q.q_num, source_ref=None,
                source_meta=q.source_meta, search_text=q.search_text or "", copied_from_question_id=q.id,
            )
            new_qs.append(nq)
        db.add_all(new_qs)
        db.flush()
        new_vs = []
        for (q, v), nq in zip(pairs, new_qs):
            nv = QuestionVersion(
                id=uuid.uuid4(), question_id=nq.id, version_no=1, language=v.language, type=v.type,
                schema_version=v.schema_version, stem=v.stem, data=v.data, explanation=v.explanation,
                default_points=v.default_points, image=v.image, content_hash=v.content_hash, origin="create",
                created_by_id=actor.id, created_at=now,
            )
            new_vs.append(nv)
        db.add_all(new_vs)
        db.flush()  # versions first, then point the questions at them (as for passages)
        for nv, nq in zip(new_vs, new_qs):
            nq.current_version_id = nv.id
        db.flush()

    audit.record(db, actor=actor, action="bank.copied", target_type="course", target_id=str(course.id),
                 details={"organization_id": str(course.organization_id), "course_id": str(course.id),
                          "bank_id": str(bank.id),
                          "source_bank_id": str(src.id), "source_organization_id": str(src.organization_id),
                          "questions": position, "passages": len(passage_map)}, request=request)
    db.commit()
    return bank
