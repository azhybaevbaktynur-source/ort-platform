"""Test factories for Phase 1 (users with teacher status, courses with an owner enrollment, enrollments)."""
from __future__ import annotations

import secrets
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.models.user import User

_JOIN_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_PASSWORD_HASH: Optional[str] = None


def _hash() -> str:
    global _PASSWORD_HASH
    if _PASSWORD_HASH is None:
        _PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))
    return _PASSWORD_HASH


def new_join_code() -> str:
    return "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(8))


def make_user(
    db: Session, *, teacher_status: str = "none", platform_admin: bool = False, disabled: bool = False,
    email: Optional[str] = None, display_name: Optional[str] = None,
) -> User:
    uid = f"usr_{uuid.uuid4().hex[:12]}"
    user = User(
        id=uid, email=email or f"{uid}@test.example", password_hash=_hash(),
        display_name=display_name, email_verified=True, teacher_status=teacher_status,
        is_platform_admin=platform_admin, disabled_at=utcnow() if disabled else None,
    )
    db.add(user)
    db.commit()
    return user


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}


def make_course(db: Session, owner: User, **overrides) -> Course:
    """Course plus the owner's teacher/active enrollment (S3 may swap this for services.create_course)."""
    fields = dict(
        owner_id=owner.id, title={"en": "Test course"}, languages=["en"], default_language="en",
        status="draft", visibility="private", enrollment_mode="invite_code", join_code=new_join_code(),
    )
    fields.update(overrides)
    course = Course(**fields)
    db.add(course)
    db.flush()
    enr = Enrollment(
        course_id=course.id, user_id=owner.id, role="teacher", state="active", source="owner",
        activated_at=utcnow(),
    )
    db.add(enr)
    db.flush()
    db.add(EnrollmentEvent(enrollment_id=enr.id, course_id=course.id, actor_id=owner.id, event="created",
                           to_role="teacher", to_state="active"))
    db.commit()
    return course


def enroll(db: Session, course: Course, user: User, role: str = "student", state: str = "active",
           source: str = "join_code") -> Enrollment:
    enr = Enrollment(
        course_id=course.id, user_id=user.id, role=role, state=state, source=source,
        activated_at=utcnow() if state == "active" else None,
    )
    db.add(enr)
    db.commit()
    return enr


def set_status(db: Session, course: Course, status: str) -> Course:
    course.status = status
    db.commit()
    return course


# --- Phase 2: banks, questions, passages, assets ---------------------------------------------

import hashlib  # noqa: E402
import io  # noqa: E402
from decimal import Decimal  # noqa: E402

from app.lms.content.models import (  # noqa: E402
    BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion,
)
from app.lms.files.models import Asset  # noqa: E402


def png_bytes(w: int = 8, h: int = 8, color=(200, 30, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def jpeg_with_exif(w: int = 16, h: int = 8, orientation: int = 6) -> bytes:
    """JPEG carrying an EXIF orientation tag and a GPS IFD."""
    from PIL import Image

    img = Image.new("RGB", (w, h), (10, 120, 200))
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif.get_ifd(0x8825)[1] = "N"  # GPSLatitudeRef
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def make_bank(db: Session, course: Optional[Course], owner: User, **overrides) -> QuestionBank:
    fields = dict(owner_id=owner.id, course_id=course.id if course else None, title="Test bank")
    fields.update(overrides)
    bank = QuestionBank(**fields)
    db.add(bank)
    db.commit()
    return bank


def _next_position(db: Session, bank: QuestionBank) -> int:
    from sqlalchemy import func, select

    return (db.execute(select(func.max(BankQuestion.position)).where(BankQuestion.bank_id == bank.id)).scalar() or 0) + 1


def make_question(db: Session, bank: QuestionBank, actor: User, type: str = "single_choice",
                  **overrides) -> BankQuestion:
    """Inserts a question plus its version 1 directly (the C4 service replaces this once it exists)."""
    language = overrides.pop("language", "en")
    stem = overrides.pop("stem", "What is 2 + 2?")
    data = overrides.pop("data", None) or {
        "choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": "B",
    }
    explanation = overrides.pop("explanation", None)
    points = overrides.pop("default_points", Decimal("1"))
    image = overrides.pop("image", None)
    q = BankQuestion(
        bank_id=bank.id, type=type, language=language, position=overrides.pop("position", _next_position(db, bank)),
        search_text=stem.lower(), **overrides,
    )
    db.add(q)
    db.flush()
    v = QuestionVersion(
        question_id=q.id, version_no=1, language=language, type=type, stem=stem, data=data,
        explanation=explanation, default_points=points, image=image,
        content_hash=hashlib.sha256(f"{q.id}:{stem}".encode()).hexdigest(), origin="create", created_by_id=actor.id,
    )
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    db.commit()
    return q


def make_passage(db: Session, bank: QuestionBank, actor: User, **overrides) -> Passage:
    language = overrides.pop("language", "en")
    body = overrides.pop("body", "Line one.\nLine two.")
    p = Passage(bank_id=bank.id, language=language, **overrides)
    db.add(p)
    db.flush()
    v = PassageVersion(
        passage_id=p.id, version_no=1, language=language, title=None, body=body,
        content_hash=hashlib.sha256(f"{p.id}:{body}".encode()).hexdigest(), origin="create", created_by_id=actor.id,
    )
    db.add(v)
    db.flush()
    p.current_version_id = v.id
    db.commit()
    return p


def make_asset(db: Session, owner: User, course: Optional[Course] = None, **overrides) -> Asset:
    """Metadata row only (no blob); use the C3 service for real uploads."""
    seed = overrides.pop("seed", uuid.uuid4().hex)
    sha = hashlib.sha256(seed.encode()).hexdigest()
    fields = dict(
        owner_id=owner.id, course_id=course.id if course else None, kind="image", visibility="public",
        source_sha256=sha, sha256=hashlib.sha256(sha.encode()).hexdigest(), mime="image/webp", bytes=100,
        source_bytes=120, width=8, height=8,
    )
    fields.update(overrides)
    fields.setdefault("storage_key", f"img/{fields['sha256']}.webp")
    asset = Asset(**fields)
    db.add(asset)
    db.commit()
    return asset


# --- Phase 3: assessments, sections, items, versions, attempts ---------------------------------

import hashlib as _hashlib  # noqa: E402
import json as _json  # noqa: E402

from app.lms.assessments.models import (  # noqa: E402
    Assessment, AssessmentItem, AssessmentSection, AssessmentVersion,
)
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection  # noqa: E402


def make_assessment(db: Session, course: Course, actor: User, **overrides) -> Assessment:
    """Draft assessment row (no sections). Pass `sections=[{...}]` to also create sections, and
    `items=[question, ...]` (BankQuestion rows) to add them to the first section."""
    sections = overrides.pop("sections", None)
    items = overrides.pop("items", None)
    from sqlalchemy import func, select

    position = (db.execute(select(func.max(Assessment.position)).where(Assessment.course_id == course.id)).scalar()
                or 0) + 1
    fields = dict(
        course_id=course.id, created_by_id=actor.id, title={"en": "Test assessment"},
        languages=list(course.languages or ["en"]), position=position, navigation="free",
        results_policy="after_submit",
    )
    fields.update(overrides)
    a = Assessment(**fields)
    db.add(a)
    db.flush()
    if sections is None and items:
        sections = [{}]
    first = None
    for i, sec in enumerate(sections or [], start=1):
        s = make_section(db, a, position=i, commit=False, **sec)
        first = first or s
    if items:
        for pos, q in enumerate(items, start=1):
            make_item(db, a, first, question=q, position=pos, commit=False)
    db.commit()
    return a


def make_section(db: Session, assessment: Assessment, *, position: Optional[int] = None, commit: bool = True,
                 **overrides) -> AssessmentSection:
    if position is None:
        from sqlalchemy import func, select

        position = (db.execute(select(func.max(AssessmentSection.position)).where(
            AssessmentSection.assessment_id == assessment.id)).scalar() or 0) + 1
    fields = dict(assessment_id=assessment.id, position=position, rules={})
    fields.update(overrides)
    s = AssessmentSection(**fields)
    db.add(s)
    db.flush()
    if commit:
        db.commit()
    return s


def make_item(db: Session, assessment: Assessment, section: AssessmentSection, *, question=None, passage=None,
              parent: Optional[AssessmentItem] = None, position: Optional[int] = None, commit: bool = True,
              **overrides) -> AssessmentItem:
    kind = overrides.pop("kind", "passage" if passage is not None and question is None else
                         ("question" if question is not None else "pick"))
    if position is None:
        from sqlalchemy import func, select

        position = (db.execute(select(func.max(AssessmentItem.position)).where(
            AssessmentItem.section_id == section.id)).scalar() or 0) + 1
    fields = dict(
        assessment_id=assessment.id, section_id=section.id, parent_item_id=parent.id if parent else None,
        position=position, kind=kind, question_id=question.id if question is not None else None,
        passage_id=passage.id if passage is not None else None,
        points=None if kind == "passage" else Decimal("1"),
    )
    fields.update(overrides)
    item = AssessmentItem(**fields)
    db.add(item)
    db.flush()
    if commit:
        db.commit()
    return item


def make_assessment_version(db: Session, assessment: Assessment, actor: User, *, kind: str = "published",
                            snapshot: Optional[dict] = None, publish: bool = True) -> AssessmentVersion:
    """Direct insert of an immutable version (the A2 publish service replaces this for real flows)."""
    snapshot = snapshot or {"schema": 1, "languages": list(assessment.languages), "sections": [], "slots": {}}
    version_no = None
    if kind == "published":
        assessment.last_version_no += 1
        version_no = assessment.last_version_no
    v = AssessmentVersion(
        assessment_id=assessment.id, kind=kind, version_no=version_no, snapshot=snapshot,
        content_hash=_hashlib.sha256(_json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
        draft_rev=assessment.draft_rev, item_count=0, points_possible=Decimal("0"), created_by_id=actor.id,
    )
    db.add(v)
    db.flush()
    if publish and kind == "published":
        assessment.published_version_id = v.id
        assessment.status = "published"
        assessment.published_draft_rev = assessment.draft_rev
        assessment.published_at = utcnow()
    db.commit()
    return v


def make_attempt(db: Session, assessment: Assessment, version: AssessmentVersion, user: User, *,
                 enrollment: Optional[Enrollment] = None, items: int = 0, question_version=None,
                 **overrides) -> Attempt:
    """Direct attempt insert with `items` attempt_items rows (needs `question_version` when items > 0)."""
    from sqlalchemy import select

    if enrollment is None:
        enrollment = db.execute(select(Enrollment).where(
            Enrollment.course_id == assessment.course_id, Enrollment.user_id == user.id)).scalars().first()
        if enrollment is None:
            enrollment = enroll(db, db.get(Course, assessment.course_id), user)
    is_preview = overrides.get("is_preview", False)
    fields = dict(
        assessment_id=assessment.id, assessment_version_id=version.id, course_id=assessment.course_id,
        enrollment_id=enrollment.id, user_id=user.id, attempt_no=None if is_preview else 1,
        language=assessment.languages[0], status="in_progress", started_at=utcnow(), item_count=items,
        points_possible=Decimal(items),
    )
    fields.update(overrides)
    att = Attempt(**fields)
    db.add(att)
    db.flush()
    for pos in range(1, items + 1):
        db.add(AttemptItem(attempt_id=att.id, position=pos, section_pos=1, slot=pos,
                           question_version_id=question_version.id))
    db.commit()
    return att


def make_attempt_section(db: Session, attempt: Attempt, section_pos: int = 1, **overrides) -> AttemptSection:
    fields = dict(attempt_id=attempt.id, section_pos=section_pos, started_at=attempt.started_at)
    fields.update(overrides)
    s = AttemptSection(**fields)
    db.add(s)
    db.commit()
    return s


# --- Phase 4: grading schemes, categories, submissions ---------------------------------------------

from app.lms.grading.models import GradeCategory, GradingScheme, GradingSchemeVersion, Submission  # noqa: E402


def make_scheme(db: Session, owner: Optional[User], type: str = "percent", params: Optional[dict] = None,
                **overrides) -> GradingScheme:
    """Scheme plus version 1 (params validated like the service). `owner=None` makes a system scheme
    (pass `key=`). The version is `scheme.current_version_id` / `db.get(GradingSchemeVersion, ...)`."""
    from app.lms.grading.params import validate_params
    from app.lms.grading.schemes import new_version_row

    normalized = validate_params(type, params if params is not None else {})
    fields = dict(owner_user_id=owner.id if owner else None, title={"en": "Test scheme"}, type=type,
                  last_version_no=1)
    fields.update(overrides)
    scheme = GradingScheme(**fields)
    db.add(scheme)
    db.flush()
    v = new_version_row(scheme, normalized, version_no=1, created_by_id=owner.id if owner else None)
    db.add(v)
    db.flush()
    scheme.current_version_id = v.id
    db.commit()
    return scheme


def scheme_version(db: Session, scheme: GradingScheme) -> GradingSchemeVersion:
    return db.get(GradingSchemeVersion, scheme.current_version_id)


def make_category(db: Session, course: Course, *, weight=Decimal("0"), position: Optional[int] = None,
                  **overrides) -> GradeCategory:
    if position is None:
        from sqlalchemy import func, select

        position = (db.execute(select(func.max(GradeCategory.position)).where(
            GradeCategory.course_id == course.id)).scalar() or 0) + 1
    fields = dict(course_id=course.id, title={"en": "Category"}, weight=Decimal(str(weight)), position=position)
    fields.update(overrides)
    cat = GradeCategory(**fields)
    db.add(cat)
    db.commit()
    return cat


def grade_attempt(db: Session, attempt: Attempt, raw, *, status: str = "graded", run_hooks: bool = True,
                  submitted_at=None) -> Attempt:
    """Mark an attempt scored with `raw` points (no item grading) and run the scored hooks like the engine."""
    from app.lms.attempts.hooks import run_scored_hooks

    now = utcnow()
    attempt.status = status
    attempt.raw_score = Decimal(str(raw))
    attempt.submitted_at = submitted_at or attempt.submitted_at or now
    attempt.submit_reason = attempt.submit_reason or "manual"
    attempt.graded_at = now if status == "graded" else None
    db.flush()
    if run_hooks:
        run_scored_hooks(db, attempt)
    db.commit()
    return attempt


def make_submission(db: Session, assessment: Assessment, enrollment: Enrollment, **overrides) -> Submission:
    """Direct submission insert (the G2 services compute real ones)."""
    fields = dict(
        course_id=assessment.course_id, assessment_id=assessment.id, enrollment_id=enrollment.id,
        user_id=enrollment.user_id, state="graded", kept_policy=assessment.score_policy or "highest",
        computed_at=utcnow(),
    )
    fields.update(overrides)
    sub = Submission(**fields)
    db.add(sub)
    db.commit()
    return sub
