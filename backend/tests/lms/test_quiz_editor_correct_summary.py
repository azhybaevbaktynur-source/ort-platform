"""Phase 7c S5: `ItemQuestionOut.correct_summary` (the collapsed quiz card shows the correct answers).

Staff with `course:content.read_admin` get it in `GET _A`; the student lobby, attempt start and attempt content never
carry it (nor the accepted answers it is built from)."""
from app.lms.quiz_editor.summary import correct_summary
from tests.lms.assessment_support import MA, NUM, SENT_NUM, SENT_SHORT, SHORT
from tests.lms.quiz_editor_support import A, card, quiz_question, quiz_world
from tests.lms.s3_support import api, clean_rate_limits, db, make_user, teacher  # noqa: F401


def test_summary_per_type():
    sc = {"choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "  4 \n"}], "correct": "B"}
    assert correct_summary("single_choice", sc) == "4"
    assert correct_summary("single_choice", {"choices": [{"id": "A", "text": ""}, {"id": "B", "text": "x"}],
                                             "correct": "A"}) == "A"  # an image-only choice: its letter
    assert correct_summary("multiple_answers", {**MA, "correct": ["A", "C"]}) == "1; 3"
    assert correct_summary("true_false", {"correct": True}) == "true"
    assert correct_summary("true_false", {"correct": False}) == "false"
    assert correct_summary("comparison", {"column_a": "x", "column_b": "y", "correct": "D"}) == "D"
    assert correct_summary("numeric", {"answers": [{"kind": "exact", "value": "7", "margin": "0"},
                                                   {"kind": "exact", "value": "7.5", "margin": "0.5"},
                                                   {"kind": "range", "min": "1", "max": "3"}]}) == "7; 7.5 ± 0.5; 1 – 3"
    assert correct_summary("short_text", {"answers": ["Paris", "Париж"], "case_sensitive": False}) == "Paris; Париж"
    assert correct_summary("essay", {"word_limit": 10, "rubric_note": "r"}) is None
    assert correct_summary("single_choice", None) is None
    assert correct_summary("unknown", {"correct": "A"}) is None
    long = correct_summary("short_text", {"answers": ["x" * 150, "y" * 150]})
    assert len(long) == 200 and long.endswith("…")


async def test_staff_get_has_summary_student_payloads_do_not(db, api):
    w = quiz_world(db, link=True, languages=("en",))
    await quiz_question(api, db, w, type="short_text", stem="Capital?", data=SHORT)
    await quiz_question(api, db, w, type="numeric", stem="Number?", data=NUM)
    await quiz_question(api, db, w, type="essay", stem="Write.", data={"word_limit": 50, "rubric_note": None})

    g = await api.call(w.O, "GET", A(w))
    assert g.status_code == 200
    qs = [i["question"] for i in g.json()["sections"][0]["items"]]
    assert [q["correct_summary"] for q in qs] == ["4", "4", SENT_SHORT, SENT_NUM, None]
    for user in (w.T, w.AS):  # course staff holding content.read_admin
        assert (await api.call(user, "GET", A(w))).json()["sections"][0]["items"][2]["question"]["correct_summary"] == SENT_SHORT

    assert (await api.call(w.O, "POST", f"{A(w)}/publish", json={})).status_code == 200
    lobby = await api.call(w.S, "GET", A(w))
    assert lobby.status_code == 200
    st = await api.call(w.S, "POST", f"{A(w)}/attempts", json={"language": "en"})
    assert st.status_code in (200, 201), st.text
    content = await api.call(w.S, "GET", f"/attempts/{st.json()['id']}/content?section=1")
    assert content.status_code == 200, content.text
    for r in (lobby, st, content):
        assert "correct_summary" not in r.text
        assert SENT_SHORT not in r.text and SENT_NUM not in r.text


async def test_assessment_writes_and_lists_carry_no_summary(db, api):
    """Item/section write responses and the staff list use the plain read model (no answers)."""
    w = quiz_world(db, link=True, languages=("en",))
    await quiz_question(api, db, w, type="short_text", stem="Capital?", data=SHORT)
    lst = await api.call(w.O, "GET", f"/courses/{w.cid}/assessments")
    assert lst.status_code == 200 and SENT_SHORT not in lst.text
    r = await api.call(w.O, "POST", f"{A(w)}/questions", json={"payload": card(type="short_text", data=SHORT)})
    assert r.status_code == 201
    assert r.json()["item"]["question"]["correct_summary"] is None
