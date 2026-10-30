"""Banks, questions, passages, versions, translations (prefix /courses). Policies: content/policies.py."""
from __future__ import annotations

import uuid
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, can, get_authz
from app.lms.content import repository as repo
from app.lms.content.permissions import can_edit_bank  # Phase 9 S1
from app.lms.content import schemas as sch
from app.lms.content import service as svc
from app.lms.content.models import BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.models.user import User

router = APIRouter()


# ------------------------------------------------------------------ helpers

def _course(ctx: AuthzContext, course_id: uuid.UUID, action: str):
    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, action, course)
    return course


def _read(ctx: AuthzContext, course_id: uuid.UUID):
    return _course(ctx, course_id, A.CONTENT_READ_ADMIN)


def _manage(ctx: AuthzContext, course_id: uuid.UUID):
    return _course(ctx, course_id, A.CONTENT_MANAGE)


# --- Phase 9 S1 begin --- (PHASE_9_DESIGN 4.2: policy strings unchanged, "+ org admin on shared banks")
BanksOf = Callable[[Session, object], list]


def _manage_bank(ctx: AuthzContext, course_id: uuid.UUID, banks_of: BanksOf):
    """`course:content.manage`, or `can_edit_bank` on every bank the write touches (an org admin of the tree on
    organization-shared banks). Course staff take exactly the `_manage` path; only a refusal looks at the banks:
    `banks_of(db, course)` returns their ids (None for a row that is not found, and the usual refusal follows)."""
    course = course_svc.load_course(ctx.db, course_id)
    if not can(ctx, A.CONTENT_MANAGE, course):
        ids = banks_of(ctx.db, course)
        if ids and None not in ids:
            found = ctx.db.execute(select(QuestionBank).where(
                QuestionBank.id.in_(set(ids)), QuestionBank.course_id == course.id)).scalars().all()
            if len(found) == len(set(ids)) and all(can_edit_bank(ctx, course, b) for b in found):
                return course
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    return course


def _banks(*bank_ids) -> BanksOf:
    return lambda db, course: list(bank_ids)


def _row_banks(model, *row_ids, extra_bank: Optional[uuid.UUID] = None) -> BanksOf:
    """Banks of these questions / passages (live rows in live banks of the course), plus `extra_bank`."""
    def banks_of(db: Session, course) -> list:
        found = dict(db.execute(
            select(model.id, model.bank_id).join(QuestionBank, QuestionBank.id == model.bank_id)
            .where(model.id.in_(list(row_ids)), QuestionBank.course_id == course.id,
                   QuestionBank.deleted_at.is_(None))
        ).all())
        return [found.get(i) for i in row_ids] + ([extra_bank] if extra_bank is not None else [])
    return banks_of


def _group_banks(*question_ids: uuid.UUID) -> BanksOf:
    """Unlink touches the question and possibly the last other member of its translation group; link joins two
    groups (Phase 9 fix 1, L2): every bank of every group involved must be editable (the questions' own banks when
    they have no group)."""
    def banks_of(db: Session, course) -> list:
        own = _row_banks(BankQuestion, *question_ids)(db, course)
        if None in own:
            return own
        gids = {g for g in db.execute(select(BankQuestion.translation_group_id).where(
            BankQuestion.id.in_(list(question_ids)))).scalars() if g is not None}
        if not gids:
            return own
        return own + list(db.execute(select(BankQuestion.bank_id).where(
            BankQuestion.translation_group_id.in_(gids)).distinct()).scalars())
    return banks_of
# --- Phase 9 S1 end ---


# --- Phase 9 S2 begin --- (S1 open item 1 / architect L5: org admins read the banks they may edit, never the course)
def _read_bank(ctx: AuthzContext, course_id: uuid.UUID, banks_of: BanksOf):
    """`course:content.read_admin`, or `can_edit_bank` on every bank the read touches (an org admin of the tree on an
    organization-shared bank). The rest of the course (private banks, answer keys) stays staff-only (A13)."""
    course = course_svc.load_course(ctx.db, course_id)
    if not can(ctx, A.CONTENT_READ_ADMIN, course):
        ids = banks_of(ctx.db, course)
        if ids and None not in ids:
            found = ctx.db.execute(select(QuestionBank).where(
                QuestionBank.id.in_(set(ids)), QuestionBank.course_id == course.id)).scalars().all()
            if len(found) == len(set(ids)) and all(can_edit_bank(ctx, course, b) for b in found):
                return course
    course_svc.require_course(ctx, A.CONTENT_READ_ADMIN, course)
    return course
def _shared_listing_allowed(ctx: AuthzContext, course) -> bool:
    """The course has a live organization-shared bank and `can_edit_bank` says yes for it (otherwise the usual
    `content.read_admin` refusal stands, so an org admin of a course without shared banks sees no change)."""
    bank = ctx.db.execute(select(QuestionBank).where(
        QuestionBank.course_id == course.id, QuestionBank.visibility == "organization",
        QuestionBank.deleted_at.is_(None)).limit(1)).scalar_one_or_none()
    return bank is not None and can_edit_bank(ctx, course, bank)
# --- Phase 9 S2 end ---


def _name(u: Optional[User]) -> Optional[str]:
    return (u.display_name or u.email) if u else None


def _image_out(image: Optional[dict]) -> Optional[sch.ImageOut]:
    if not image:
        return None
    return sch.ImageOut(asset_id=image["asset_id"], url=_media(image["sha256"]))


def _media(sha: str) -> str:
    from app.lms.content.types import media_url

    return media_url(sha)


def _version_out(v: QuestionVersion, author: Optional[str]) -> sch.VersionOut:
    return sch.VersionOut(
        id=v.id, version_no=v.version_no, type=v.type, language=v.language, stem=v.stem,
        data=repo.expand_images(v.data), explanation=v.explanation, default_points=float(v.default_points),
        image=_image_out(v.image), origin=v.origin, created_at=v.created_at, created_by_name=author,
    )


def _passage_summary_by_id(db: Session, passage_id: uuid.UUID) -> Optional[sch.PassageSummaryOut]:
    qc = select(func.count()).select_from(BankQuestion).where(
        BankQuestion.passage_id == Passage.id, BankQuestion.deleted_at.is_(None)).correlate(Passage).scalar_subquery()
    row = db.execute(
        select(Passage, PassageVersion.version_no, PassageVersion.title, PassageVersion.body, qc)
        .join(PassageVersion, PassageVersion.id == Passage.current_version_id)
        .where(Passage.id == passage_id)
    ).first()
    return _passage_summary(row) if row else None


def _passage_summary(row) -> sch.PassageSummaryOut:
    p, version_no, title, body, qc = row
    return sch.PassageSummaryOut(
        id=p.id, language=p.language, title=title, body_excerpt=sch.excerpt(body), question_count=qc or 0,
        version_no=version_no, updated_at=p.updated_at, deleted_at=p.deleted_at,
    )


def _translations(db: Session, course_id: uuid.UUID, q: BankQuestion) -> list[sch.TranslationRef]:
    if q.translation_group_id is None:
        return []
    rows = db.execute(
        select(BankQuestion.id, BankQuestion.language, BankQuestion.bank_id)
        .join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
        .where(BankQuestion.translation_group_id == q.translation_group_id, BankQuestion.id != q.id,
               BankQuestion.deleted_at.is_(None), QuestionBank.deleted_at.is_(None),
               QuestionBank.course_id == course_id)
        .order_by(BankQuestion.language)
    ).all()
    return [sch.TranslationRef(question_id=r[0], language=r[1], bank_id=r[2]) for r in rows]


def _staff_fields(db: Session, course, q: BankQuestion) -> dict:
    v = db.get(QuestionVersion, q.current_version_id)
    author = _name(db.get(User, v.created_by_id)) if v.created_by_id else None
    summary = sch.question_summary(q, v.stem, v.version_no, v.image)
    return {
        **summary.model_dump(),
        "current_version": _version_out(v, author),
        "passage": _passage_summary_by_id(db, q.passage_id) if q.passage_id else None,
        "translations": _translations(db, course.id, q),
    }


def _staff_out(db: Session, course, q: BankQuestion) -> sch.QuestionStaffOut:
    return sch.QuestionStaffOut(**_staff_fields(db, course, q))


def _summary_of(db: Session, q: BankQuestion) -> sch.QuestionSummaryOut:
    v = db.get(QuestionVersion, q.current_version_id)
    return sch.question_summary(q, v.stem, v.version_no, v.image)


def _passage_out(db: Session, course, p: Passage, *, unchanged: Optional[bool] = None):
    pv = db.get(PassageVersion, p.current_version_id)
    summary = _passage_summary_by_id(db, p.id)
    stmt = repo.question_list_stmt(p.bank_id, repo.QuestionFilter(passage_id=p.id))
    rows = db.execute(stmt.order_by(BankQuestion.position, BankQuestion.id).limit(200)).all()
    fields = {
        **summary.model_dump(),
        "bank_id": p.bank_id,
        "current_version": _passage_version_out(pv, _name(db.get(User, pv.created_by_id)) if pv.created_by_id else None),
        "questions": [sch.question_summary(r[0], r[1], r[2], r[3]) for r in rows],
    }
    if unchanged is None:
        return sch.PassageOut(**fields)
    return sch.PassagePatchOut(**fields, unchanged=unchanged)


def _passage_version_out(pv: PassageVersion, author: Optional[str]) -> sch.PassageVersionOut:
    return sch.PassageVersionOut(
        id=pv.id, version_no=pv.version_no, origin=pv.origin, created_at=pv.created_at, created_by_name=author,
        language=pv.language, title=pv.title, body=pv.body, image=_image_out(pv.image),
    )


def _bank_out(ctx: AuthzContext, course, bank_id: uuid.UUID) -> sch.BankOut:
    row = ctx.db.execute(repo.bank_rows_stmt(course.id, bank_id=bank_id)).first()
    return sch.bank_out(row, can_edit=can_edit_bank(ctx, course, row[0]),  # Phase 9 S1: `can_edit`
                        can_delete=can(ctx, A.CONTENT_MANAGE, course))  # Phase 9 S2: staff only


# ------------------------------------------------------------------ banks

@router.get("/{course_id}/banks", response_model=PageOut[sch.BankOut])
def list_banks(course_id: uuid.UUID, deleted: bool = False, cursor: Optional[str] = None, limit: int = 25,
               kind: Literal["all", "shared", "quiz"] = "all",  # --- Phase 7c S1 --- (PHASE_7C_DESIGN 6.1)
               ctx: AuthzContext = Depends(get_authz)):
    # --- Phase 9 S2 --- (L5): without content.read_admin, an org admin of the tree lists the organization-shared
    # banks of the course (exactly those `can_edit_bank` allows; every one has the course's organization)
    course = course_svc.load_course(ctx.db, course_id)
    stmt = repo.bank_rows_stmt(course.id, deleted=deleted, kind=kind)
    if not can(ctx, A.CONTENT_READ_ADMIN, course) and _shared_listing_allowed(ctx, course):
        stmt = stmt.where(QuestionBank.visibility == "organization", QuestionBank.assessment_id.is_(None))
        if deleted:
            stmt = stmt.where(false())
    else:
        course = _read(ctx, course_id)
    rows, nxt = course_svc.paginate_rows(
        ctx.db, stmt, sort_col=QuestionBank.created_at,
        id_col=QuestionBank.id, entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    staff = can(ctx, A.CONTENT_MANAGE, course)  # Phase 9 S2: `can_delete` (delete / restore are staff only)
    items = [sch.bank_out(r, can_edit=can_edit_bank(ctx, course, r[0]), can_delete=staff)  # Phase 9 S1: `can_edit`
             for r in rows]
    return PageOut[sch.BankOut](items=items, next_cursor=nxt)


@router.post("/{course_id}/banks", status_code=201, response_model=sch.BankOut)
def create_bank(course_id: uuid.UUID, data: sch.BankCreateIn, ctx: AuthzContext = Depends(get_authz)):
    course = _manage(ctx, course_id)
    bank = svc.create_bank(ctx.db, ctx, course, data)
    return _bank_out(ctx, course, bank.id)


@router.get("/{course_id}/banks/{bank_id}", response_model=sch.BankOut)
def get_bank(course_id: uuid.UUID, bank_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _banks(bank_id))  # Phase 9 S2
    repo.load_bank(ctx.db, course.id, bank_id, include_deleted=True)
    return _bank_out(ctx, course, bank_id)


@router.patch("/{course_id}/banks/{bank_id}", response_model=sch.BankOut)
def update_bank(course_id: uuid.UUID, bank_id: uuid.UUID, data: sch.BankUpdateIn,
                ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _banks(bank_id))
    svc.update_bank(ctx.db, ctx, course, bank_id, data)
    return _bank_out(ctx, course, bank_id)


@router.delete("/{course_id}/banks/{bank_id}", status_code=204, response_class=Response)
def delete_bank(course_id: uuid.UUID, bank_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _manage(ctx, course_id)  # Phase 9 fix 1 (L3): staff only, the org-admin branch never deletes a bank
    svc.soft_delete_bank(ctx.db, ctx, course, bank_id)
    return Response(status_code=204)


@router.post("/{course_id}/banks/{bank_id}/restore", response_model=sch.BankOut)
def restore_bank(course_id: uuid.UUID, bank_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _manage(ctx, course_id)  # Phase 9 fix 1 (L3): staff only, like delete
    svc.restore_bank(ctx.db, ctx, course, bank_id)
    return _bank_out(ctx, course, bank_id)


# ------------------------------------------------------------------ questions

@router.get("/{course_id}/banks/{bank_id}/questions", response_model=PageOut[sch.QuestionSummaryOut])
def list_questions(
    course_id: uuid.UUID, bank_id: uuid.UUID, q: Optional[str] = Query(None, max_length=200),
    type: Optional[str] = None, language: Optional[str] = None, section: Optional[str] = None,
    topic: Optional[str] = None, difficulty: Optional[str] = None, tag: Optional[str] = None,
    passage_id: Optional[uuid.UUID] = None, deleted: bool = False, cursor: Optional[str] = None,
    limit: int = 25, ctx: AuthzContext = Depends(get_authz),
):
    course = _read_bank(ctx, course_id, _banks(bank_id))  # Phase 9 S2
    bank = repo.load_bank(ctx.db, course.id, bank_id)
    f = repo.QuestionFilter(q=q, type=type, language=language, section=section, topic=topic,
                            difficulty=difficulty, tag=tag, passage_id=passage_id, deleted=deleted)
    rows, nxt = course_svc.paginate_rows(
        ctx.db, repo.question_list_stmt(bank.id, f), sort_col=BankQuestion.position, id_col=BankQuestion.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False,
    )
    return PageOut[sch.QuestionSummaryOut](
        items=[sch.question_summary(r[0], r[1], r[2], r[3]) for r in rows], next_cursor=nxt)


@router.post("/{course_id}/banks/{bank_id}/questions", status_code=201, response_model=sch.QuestionStaffOut)
def create_question(course_id: uuid.UUID, bank_id: uuid.UUID, data: sch.QuestionCreateIn,
                    ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _banks(bank_id))
    bank = repo.load_bank(ctx.db, course.id, bank_id)
    q = svc.create_question(ctx.db, ctx, course, bank, data)
    return _staff_out(ctx.db, course, q)


@router.get("/{course_id}/questions/{question_id}", response_model=sch.QuestionStaffOut)
def get_question(course_id: uuid.UUID, question_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _row_banks(BankQuestion, question_id))  # Phase 9 S2
    q = repo.load_question(ctx.db, course.id, question_id, include_deleted=True)
    return _staff_out(ctx.db, course, q)


@router.patch("/{course_id}/questions/{question_id}", response_model=sch.QuestionPatchOut)
def update_question(course_id: uuid.UUID, question_id: uuid.UUID, data: sch.QuestionUpdateIn,
                    ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(BankQuestion, question_id))
    q, unchanged = svc.update_question(ctx.db, ctx, course, question_id, data)
    return sch.QuestionPatchOut(**_staff_fields(ctx.db, course, q), unchanged=unchanged)


@router.delete("/{course_id}/questions/{question_id}", status_code=204, response_class=Response)
def delete_question(course_id: uuid.UUID, question_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(BankQuestion, question_id))
    svc.soft_delete_question(ctx.db, ctx, course, question_id)
    return Response(status_code=204)


@router.post("/{course_id}/questions/{question_id}/restore", response_model=sch.QuestionStaffOut)
def restore_question(course_id: uuid.UUID, question_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(BankQuestion, question_id))
    q = svc.restore_question(ctx.db, ctx, course, question_id)
    return _staff_out(ctx.db, course, q)


@router.post("/{course_id}/questions/{question_id}/move", response_model=sch.QuestionSummaryOut)
def move_question(course_id: uuid.UUID, question_id: uuid.UUID, data: sch.MoveIn,
                  ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(BankQuestion, question_id))
    q = svc.move_question(ctx.db, ctx, course, question_id, data.direction)
    return _summary_of(ctx.db, q)


# ------------------------------------------------------------------ question versions

@router.get("/{course_id}/questions/{question_id}/versions", response_model=PageOut[sch.VersionSummaryOut])
def list_question_versions(course_id: uuid.UUID, question_id: uuid.UUID, cursor: Optional[str] = None,
                           limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _row_banks(BankQuestion, question_id))  # Phase 9 S2
    q = repo.load_question(ctx.db, course.id, question_id, include_deleted=True)
    stmt = (
        select(QuestionVersion, User.display_name, User.email)
        .outerjoin(User, User.id == QuestionVersion.created_by_id)
        .where(QuestionVersion.question_id == q.id)
    )
    rows, nxt = course_svc.paginate_rows(
        ctx.db, stmt, sort_col=QuestionVersion.version_no, id_col=QuestionVersion.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    items = [
        sch.VersionSummaryOut(id=v.id, version_no=v.version_no, type=v.type, origin=v.origin,
                              created_at=v.created_at, created_by_name=dn or em)
        for v, dn, em in rows
    ]
    return PageOut[sch.VersionSummaryOut](items=items, next_cursor=nxt)


@router.get("/{course_id}/questions/{question_id}/versions/{version_id}", response_model=sch.VersionOut)
def get_question_version(course_id: uuid.UUID, question_id: uuid.UUID, version_id: uuid.UUID,
                         ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _row_banks(BankQuestion, question_id))  # Phase 9 S2
    q = repo.load_question(ctx.db, course.id, question_id, include_deleted=True)
    v = repo.load_question_version(ctx.db, q.id, version_id)
    author = _name(ctx.db.get(User, v.created_by_id)) if v.created_by_id else None
    return _version_out(v, author)


@router.post("/{course_id}/questions/{question_id}/versions/{version_id}/revert",
             response_model=sch.QuestionStaffOut)
def revert_question(course_id: uuid.UUID, question_id: uuid.UUID, version_id: uuid.UUID, data: sch.RevertIn,
                    ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(BankQuestion, question_id))
    q = svc.revert_question(ctx.db, ctx, course, question_id, version_id, data.base_version_id)
    return _staff_out(ctx.db, course, q)


@router.get("/{course_id}/questions/{question_id}/preview", response_model=sch.QuestionPreviewOut)
def preview_question(course_id: uuid.UUID, question_id: uuid.UUID, version_id: Optional[uuid.UUID] = None,
                     ctx: AuthzContext = Depends(get_authz)):
    """What a student would see: built only through the allowlisted student serializers."""
    course = _read_bank(ctx, course_id, _row_banks(BankQuestion, question_id))  # Phase 9 S2
    db = ctx.db
    q = repo.load_question(db, course.id, question_id, include_deleted=True)
    v = repo.load_question_version(db, q.id, version_id) if version_id else db.get(QuestionVersion, q.current_version_id)
    payload = repo.student_question(v)
    passage = None
    if q.passage_id:
        p = db.get(Passage, q.passage_id)
        if p is not None and p.current_version_id:
            passage = repo.student_passage(db.get(PassageVersion, p.current_version_id))
    return sch.QuestionPreviewOut(**payload, passage=passage)


# ------------------------------------------------------------------ translations

@router.get("/{course_id}/questions/{question_id}/translations", response_model=list[sch.QuestionSummaryOut])
def list_translations(course_id: uuid.UUID, question_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _row_banks(BankQuestion, question_id))  # Phase 9 S2
    q = repo.load_question(ctx.db, course.id, question_id, include_deleted=True)
    if q.translation_group_id is None:
        return []
    rows = ctx.db.execute(
        select(BankQuestion, QuestionVersion.stem, QuestionVersion.version_no, QuestionVersion.image)
        .join(QuestionVersion, QuestionVersion.id == BankQuestion.current_version_id)
        .join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
        .where(BankQuestion.translation_group_id == q.translation_group_id, BankQuestion.id != q.id,
               BankQuestion.deleted_at.is_(None), QuestionBank.deleted_at.is_(None),
               QuestionBank.course_id == course.id)
        .order_by(BankQuestion.language)
    ).all()
    return [sch.question_summary(r[0], r[1], r[2], r[3]) for r in rows]


@router.post("/{course_id}/questions/{question_id}/translations", status_code=201,
             response_model=sch.QuestionStaffOut)
def add_translation(course_id: uuid.UUID, question_id: uuid.UUID, data: sch.TranslationCreateIn,
                    ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(BankQuestion, question_id, extra_bank=data.bank_id))
    q = svc.add_translation(ctx.db, ctx, course, question_id, data)
    return _staff_out(ctx.db, course, q)


@router.post("/{course_id}/questions/{question_id}/translation-link", status_code=204, response_class=Response)
def link_translation(course_id: uuid.UUID, question_id: uuid.UUID, data: sch.TranslationLinkIn,
                     ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _group_banks(question_id, data.question_id))  # Phase 9 fix 1 (L2)
    svc.link_translation(ctx.db, ctx, course, question_id, data.question_id)
    return Response(status_code=204)


@router.delete("/{course_id}/questions/{question_id}/translation-link", status_code=204, response_class=Response)
def unlink_translation(course_id: uuid.UUID, question_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _group_banks(question_id))
    svc.unlink_translation(ctx.db, ctx, course, question_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ passages

@router.get("/{course_id}/banks/{bank_id}/passages", response_model=PageOut[sch.PassageSummaryOut])
def list_passages(course_id: uuid.UUID, bank_id: uuid.UUID, deleted: bool = False, cursor: Optional[str] = None,
                  limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _banks(bank_id))  # Phase 9 S2
    bank = repo.load_bank(ctx.db, course.id, bank_id)
    rows, nxt = course_svc.paginate_rows(
        ctx.db, repo.passage_rows_stmt(bank.id, deleted=deleted), sort_col=Passage.created_at, id_col=Passage.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    return PageOut[sch.PassageSummaryOut](items=[_passage_summary(r) for r in rows], next_cursor=nxt)


@router.post("/{course_id}/banks/{bank_id}/passages", status_code=201, response_model=sch.PassageOut)
def create_passage(course_id: uuid.UUID, bank_id: uuid.UUID, data: sch.PassageCreateIn,
                   ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _banks(bank_id))
    bank = repo.load_bank(ctx.db, course.id, bank_id)
    p = svc.create_passage(ctx.db, ctx, course, bank, data)
    return _passage_out(ctx.db, course, p)


@router.get("/{course_id}/passages/{passage_id}", response_model=sch.PassageOut)
def get_passage(course_id: uuid.UUID, passage_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _row_banks(Passage, passage_id))  # Phase 9 S2
    p = repo.load_passage(ctx.db, course.id, passage_id, include_deleted=True)
    return _passage_out(ctx.db, course, p)


@router.patch("/{course_id}/passages/{passage_id}", response_model=sch.PassagePatchOut)
def update_passage(course_id: uuid.UUID, passage_id: uuid.UUID, data: sch.PassageUpdateIn,
                   ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(Passage, passage_id))
    p, unchanged = svc.update_passage(ctx.db, ctx, course, passage_id, data)
    return _passage_out(ctx.db, course, p, unchanged=unchanged)


@router.delete("/{course_id}/passages/{passage_id}", status_code=204, response_class=Response)
def delete_passage(course_id: uuid.UUID, passage_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(Passage, passage_id))
    svc.soft_delete_passage(ctx.db, ctx, course, passage_id)
    return Response(status_code=204)


@router.post("/{course_id}/passages/{passage_id}/restore", response_model=sch.PassageOut)
def restore_passage(course_id: uuid.UUID, passage_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(Passage, passage_id))
    p = svc.restore_passage(ctx.db, ctx, course, passage_id)
    return _passage_out(ctx.db, course, p)


@router.get("/{course_id}/passages/{passage_id}/versions", response_model=PageOut[sch.PassageVersionSummaryOut])
def list_passage_versions(course_id: uuid.UUID, passage_id: uuid.UUID, cursor: Optional[str] = None,
                          limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _row_banks(Passage, passage_id))  # Phase 9 S2
    p = repo.load_passage(ctx.db, course.id, passage_id, include_deleted=True)
    stmt = (
        select(PassageVersion, User.display_name, User.email)
        .outerjoin(User, User.id == PassageVersion.created_by_id)
        .where(PassageVersion.passage_id == p.id)
    )
    rows, nxt = course_svc.paginate_rows(
        ctx.db, stmt, sort_col=PassageVersion.version_no, id_col=PassageVersion.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    items = [sch.PassageVersionSummaryOut(id=v.id, version_no=v.version_no, origin=v.origin,
                                          created_at=v.created_at, created_by_name=dn or em)
             for v, dn, em in rows]
    return PageOut[sch.PassageVersionSummaryOut](items=items, next_cursor=nxt)


@router.get("/{course_id}/passages/{passage_id}/versions/{version_id}", response_model=sch.PassageVersionOut)
def get_passage_version(course_id: uuid.UUID, passage_id: uuid.UUID, version_id: uuid.UUID,
                        ctx: AuthzContext = Depends(get_authz)):
    course = _read_bank(ctx, course_id, _row_banks(Passage, passage_id))  # Phase 9 S2
    p = repo.load_passage(ctx.db, course.id, passage_id, include_deleted=True)
    pv = repo.load_passage_version(ctx.db, p.id, version_id)
    return _passage_version_out(pv, _name(ctx.db.get(User, pv.created_by_id)) if pv.created_by_id else None)


@router.post("/{course_id}/passages/{passage_id}/versions/{version_id}/revert", response_model=sch.PassageOut)
def revert_passage(course_id: uuid.UUID, passage_id: uuid.UUID, version_id: uuid.UUID, data: sch.RevertIn,
                   ctx: AuthzContext = Depends(get_authz)):
    course = _manage_bank(ctx, course_id, _row_banks(Passage, passage_id))
    p = svc.revert_passage(ctx.db, ctx, course, passage_id, version_id, data.base_version_id)
    return _passage_out(ctx.db, course, p)
