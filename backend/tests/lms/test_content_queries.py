"""N+1 guards: statement counts do not grow with the number of rows (design 7.15)."""
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.db import session as db_session
from app.lms.content import repository as repo
from app.lms.content.models import BankQuestion
from tests.lms.content_support import world
from tests.lms.factories import make_bank, make_passage, make_question
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


@contextmanager
def count_statements():
    stmts = []

    def hook(conn, cursor, statement, parameters, context, executemany):
        stmts.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", hook)
    try:
        yield stmts
    finally:
        event.remove(db_session.engine, "before_cursor_execute", hook)


def fill(db, w, bank, n, passage=None):
    for i in range(n):
        make_question(db, bank, w.O, stem=f"question {i}", passage_id=passage.id if passage else None)


def test_question_list_page_of_100_is_one_statement(db):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    fill(db, w, bank, 100)
    stmt = repo.question_list_stmt(bank.id, repo.QuestionFilter()).order_by(BankQuestion.position).limit(101)
    db.rollback()
    with count_statements() as s:
        rows = db.execute(stmt).all()
    assert len(rows) == 100 and len(s) == 1
    assert all(r[1].startswith("question") for r in rows)  # stem comes from the same statement


def test_student_payloads_for_150_versions_with_passages_use_two_queries(db):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    passages = [make_passage(db, bank, w.O, body=f"passage {i}") for i in range(25)]
    vids = []
    for i in range(150):
        q = make_question(db, bank, w.O, stem=f"q{i}", passage_id=passages[i % 25].id)
        vids.append(q.current_version_id)
    db.expire_all()
    with count_statements() as s:
        out = repo.load_student_payloads(db, vids)
    assert len(out) == 150 and len(s) <= 2, [x[:80] for x in s]
    sample = out[vids[3]]
    assert sample["passage"]["body"] == "passage 3" and set(sample) == {
        "id", "type", "language", "stem", "image_url", "points", "data", "passage"}
    assert set(sample["passage"]) == {"id", "title", "body", "image_url"}


def test_load_versions_chunks_in_lists_of_500(db):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    q = make_question(db, bank, w.O)
    import uuid

    ids = [q.current_version_id] + [uuid.uuid4() for _ in range(1199)]
    with count_statements() as s:
        got = repo.load_versions(db, ids)
    assert list(got) == [q.current_version_id] and len(s) == 3


@pytest.mark.parametrize("n_small,n_big", [(3, 60)])
async def test_api_statement_count_does_not_depend_on_page_size(db, api, n_small, n_big):
    w = world(db)
    small = make_bank(db, w.course, w.O, title="s")
    big = make_bank(db, w.course, w.O, title="b")
    p_small, p_big = make_passage(db, small, w.O), make_passage(db, big, w.O)
    fill(db, w, small, n_small, p_small)
    fill(db, w, big, n_big, p_big)
    for i in range(n_big):
        make_passage(db, big, w.O)
    qs, qb = make_question(db, small, w.O), make_question(db, big, w.O)
    paths = [
        ("banks", "/courses/{c}/banks", None),
        ("questions", "/courses/{c}/banks/{b}/questions", None),
        ("passages", "/courses/{c}/banks/{b}/passages", None),
        ("translations", "/courses/{c}/questions/{q}/translations", None),
    ]
    await api.call(w.O, "GET", f"/courses/{w.cid}/banks")  # warm-up: first request pays one-off lookups
    for name, tpl, _ in paths:
        counts = []
        for bank, q in ((small, qs), (big, qb)):
            url = tpl.format(c=w.cid, b=bank.id, q=q.id)
            with count_statements() as s:
                res = await api.call(w.O, "GET", url, params={"limit": 100})
            assert res.status_code == 200, (name, res.text)
            counts.append(len(s))
        assert counts[0] == counts[1], (name, counts)
        assert counts[1] <= 8, (name, counts)


async def test_versions_list_is_one_query_regardless_of_size(db, api):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    q = make_question(db, bank, w.O)
    from app.lms.content import service as svc

    for i in range(30):
        svc.new_question_version(db, q, {"type": q.type, "stem": f"v{i}", "data": {
            "choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": "B"}},
            actor_id=w.O.id, origin="edit")
    db.commit()
    url = f"/courses/{w.cid}/questions/{q.id}/versions"
    await api.call(w.O, "GET", url)  # warm-up
    with count_statements() as s:
        res = await api.call(w.O, "GET", url, params={"limit": 100})
    assert res.status_code == 200 and len(res.json()["items"]) == 31
    # 2 user lookups, course, role, question, versions (with authors joined): constant in the number of versions
    assert len(s) == 6 and len([x for x in s if "FROM question_versions" in x]) == 1
