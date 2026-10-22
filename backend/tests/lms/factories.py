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
    role: str = "student", email: Optional[str] = None, display_name: Optional[str] = None,
) -> User:
    uid = f"usr_{uuid.uuid4().hex[:12]}"
    user = User(
        id=uid, email=email or f"{uid}@test.example", password_hash=_hash(), role=role,
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
