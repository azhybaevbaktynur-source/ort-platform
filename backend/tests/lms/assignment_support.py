"""Phase 7a S2 test helpers: course worlds, assignments written directly or through the API, file uploads."""
from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.lms.assignments.models import Assignment
from app.lms.assignments.sync import mirror_from_assessment
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.files import storage
from app.main import app
from app.models.user import User
from tests.lms.factories import auth, enroll, make_assessment, make_assessment_version, make_course, set_status
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import Api, api, clean_rate_limits, db, make_user, teacher  # noqa: F401

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def fresh_storage():
    storage.reset_blob_storage()
    yield
    storage.reset_blob_storage()


@dataclass
class World:
    course: Course
    O: User           # owner (teacher)
    T: User           # assistant
    S: User           # student
    S2: User          # second student
    X: User           # outsider
    OA: User          # org admin of the course's organization
    enr: Enrollment   # S's enrollment
    enr2: Enrollment

    @property
    def cid(self) -> str:
        return str(self.course.id)


def world(db, *, status: str = "published") -> World:
    org = make_org(db)
    owner = teacher(db)
    add_member(db, org, owner, role="teacher")
    course = make_course(db, owner, organization_id=org.id)
    ta, s, s2, x, oa = (make_user(db) for _ in range(5))
    add_member(db, org, oa, role="org_admin")
    enroll(db, course, ta, role="assistant", source="owner")
    e1 = enroll(db, course, s)
    e2 = enroll(db, course, s2)
    if status != "draft":
        set_status(db, course, status)
    return World(course, owner, ta, s, s2, x, oa, e1, e2)


def make_assignment(db, course: Course, actor: User, *, kind: str = "text", published: bool = True,
                    points: Optional[Decimal] = Decimal("10"), **fields) -> Assignment:
    from sqlalchemy import func, select

    pos = (db.execute(select(func.max(Assignment.position)).where(Assignment.course_id == course.id)).scalar()
           or 0) + 1
    a = Assignment(course_id=course.id, kind=kind, title=fields.pop("title", {"en": f"{kind} work"}),
                   points_possible=points, published=published, position=pos, created_by_id=actor.id, **fields)
    db.add(a)
    db.commit()
    return a


def published_quiz(db, course: Course, actor: User, **fields) -> Assignment:
    """Assessment with a published version and its mirrored quiz assignment."""
    x = make_assessment(db, course, actor, **fields)
    make_assessment_version(db, x, actor)
    a = mirror_from_assessment(db, x)
    db.commit()
    return a


def png(w: int = 16, h: int = 16) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (uuid.uuid4().int % 255, 40, 90)).save(buf, "PNG")
    return buf.getvalue()


def pdf(tag: str = "") -> bytes:
    return PDF + (tag or uuid.uuid4().hex).encode()


async def upload(user, path: str, data: bytes, *, filename: str = "work.pdf", ctype: str = "application/pdf"):
    h = auth(user) if user is not None else {}
    h["x-forwarded-for"] = f"10.9.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}, 10.255.255.1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post("/api/v1" + path, files={"file": (filename, data, ctype)}, headers=h)


async def upload_hand_in(user, w: World, a: Assignment, data: bytes, **kw):
    return await upload(user, f"/courses/{w.cid}/assignments/{a.id}/submissions/files", data, **kw)


async def hand_in(api, user, w: World, a: Assignment, **body):
    return await api.call(user, "POST", f"/courses/{w.cid}/assignments/{a.id}/submissions", json=body)
