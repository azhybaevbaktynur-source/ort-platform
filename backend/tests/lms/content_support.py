"""Shared helpers for the C4 content API tests."""
from __future__ import annotations

from types import SimpleNamespace

from tests.lms.factories import enroll, make_course, make_user

SC = {"choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": "B"}


def qbody(**kw) -> dict:
    body = {"type": "single_choice", "language": "en", "stem": "What is 2 + 2?", "data": SC,
            "default_points": 1}
    body.update(kw)
    return body


def world(db, status: str = "published", languages=("en", "ru", "ky")):
    """O owner, T co-teacher, AS assistant, S student, X outsider; one course."""
    O = make_user(db, teacher_status="approved")
    T = make_user(db, teacher_status="approved")
    AS, S, X = make_user(db), make_user(db), make_user(db)
    course = make_course(db, O, status=status, languages=list(languages), default_language=languages[0])
    enroll(db, course, T, "teacher", source="staff_add")
    enroll(db, course, AS, "assistant", source="staff_add")
    enroll(db, course, S, "student")
    return SimpleNamespace(O=O, T=T, AS=AS, S=S, X=X, course=course, cid=str(course.id))


async def new_bank(api, user, cid, **kw) -> dict:
    res = await api.call(user, "POST", f"/courses/{cid}/banks", json={"title": "Bank", **kw})
    assert res.status_code == 201, res.text
    return res.json()


async def new_question(api, user, cid, bank_id, **kw) -> dict:
    res = await api.call(user, "POST", f"/courses/{cid}/banks/{bank_id}/questions", json=qbody(**kw))
    assert res.status_code == 201, res.text
    return res.json()


async def new_passage(api, user, cid, bank_id, **kw) -> dict:
    body = {"language": "en", "title": "T", "body": "Line one.\n[5] Line two."}
    body.update(kw)
    res = await api.call(user, "POST", f"/courses/{cid}/banks/{bank_id}/passages", json=body)
    assert res.status_code == 201, res.text
    return res.json()
