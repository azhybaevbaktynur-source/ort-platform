"""Phase 8a S3 test helpers (pages, course files, announcements, course home; PHASE_8A_DESIGN 7.3, 10).

- `open_gate` fixture: `modules.gate.require_access` as a recorded no-op (S2 implements and tests the gate; these
  tests check that S3 calls it for students only, with the right target). `gate_calls` lists the calls.
- `matrix(...)`: the action x role x course status table of design 7.3 for one route.
- `upload_course_file(...)`: multipart upload with the form fields."""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable, Optional

import pytest
from httpx import ASGITransport, AsyncClient

from app.lms.modules import gate
from app.main import app
from tests.lms.factories import auth
from tests.lms.modules_support import structure_world

ROLES = ("O", "T", "S", "OA", "X")
STATUSES = ("draft", "published", "concluded")

# design 7.3: read (content.read) and manage (content.manage)
READ = {
    "draft": {"O": "ok", "T": "ok", "S": 403, "OA": "ok", "X": 404},
    "published": {"O": "ok", "T": "ok", "S": "ok", "OA": "ok", "X": 404},
    "concluded": {"O": "ok", "T": "ok", "S": "ok", "OA": "ok", "X": 404},
}
MANAGE = {
    "draft": {"O": "ok", "T": "ok", "S": 403, "OA": 403, "X": 404},
    "published": {"O": "ok", "T": "ok", "S": 403, "OA": 403, "X": 404},
    "concluded": {"O": 403, "T": 403, "S": 403, "OA": 403, "X": 404},
}


class GateCalls(list):
    pass


@pytest.fixture
def gate_calls(monkeypatch) -> GateCalls:
    calls = GateCalls()

    def record(db, ctx, course, *, page=None, file=None, assignment=None):
        calls.append({"user": ctx.user.id, "course": course.id, "page": getattr(page, "id", None),
                      "file": getattr(file, "id", None)})

    monkeypatch.setattr(gate, "require_access", record)
    return calls


@pytest.fixture(autouse=True)
def open_gate(gate_calls):
    yield gate_calls


async def matrix(api, db, table: dict, ok: int,
                 request: Callable[[object, object], Awaitable[tuple]] | Callable[[object, object], tuple],
                 *, statuses=STATUSES, call: Optional[Callable] = None) -> None:
    """For every course status a fresh world; for every role `request(w, user) -> (method, path, json)` builds the
    request (it may create the target first). Expected: `ok` where the table says "ok", else the status code."""
    for status in statuses:
        w = structure_world(db, status=status)
        for role in ROLES:
            user = getattr(w, role)
            req = request(w, user)
            if hasattr(req, "__await__"):
                req = await req
            method, path, body = req
            res = await (call(user, method, path, body) if call else api.call(user, method, path, json=body))
            want = table[status][role]
            want = ok if want == "ok" else want
            assert res.status_code == want, (status, role, method, path, res.status_code, res.text)


def pdf_bytes(tag: str = "") -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n" + (tag or uuid.uuid4().hex).encode()


async def upload_course_file(user, course_id, data: bytes, *, filename: str = "notes.pdf", folder: str = "",
                             title: Optional[str] = None, published: Optional[str] = None,
                             ctype: str = "application/pdf"):
    h = auth(user) if user is not None else {}
    h["x-forwarded-for"] = f"10.8.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}, 10.255.255.1"
    form = {"folder": folder}
    if title is not None:
        form["title"] = title
    if published is not None:
        form["published"] = published
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(f"/api/v1/courses/{course_id}/course-files", files={"file": (filename, data, ctype)},
                            data=form, headers=h)
