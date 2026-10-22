"""7.1 Timing unit tests: deadlines (P3-13), grace edges (P3-14) and lazy section transitions (P3-15)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.lms.attempts import timing
from app.lms.attempts.timing import SectionState, Transition

T0 = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
GRACE = 45


def s(seconds):
    return T0 + timedelta(seconds=seconds)


@pytest.mark.parametrize("snapshot,extra,until,expected", [
    ({"time_limit_s": 600, "sections": []}, 0, None, s(600)),
    ({"time_limit_s": 600, "sections": []}, 120, None, s(720)),
    ({"time_limit_s": None, "sections": [{"time_limit_s": 60}, {"time_limit_s": 120}]}, 0, None, s(180)),
    ({"time_limit_s": None, "sections": [{"time_limit_s": 60}, {"time_limit_s": None}]}, 0, None, None),
    ({"time_limit_s": None, "sections": []}, 0, None, None),
    ({"time_limit_s": 600, "sections": []}, 0, s(300), s(300)),
    ({"time_limit_s": 600, "sections": []}, 0, s(900), s(600)),
    ({"time_limit_s": None, "sections": []}, 0, s(900), s(900)),
    # time_limit_s wins over the section sum
    ({"time_limit_s": 500, "sections": [{"time_limit_s": 60}, {"time_limit_s": 120}]}, 0, None, s(500)),
])
def test_attempt_deadline(snapshot, extra, until, expected):
    assert timing.attempt_deadline(T0, snapshot, extra, until) == expected


def test_attempt_deadline_accepts_naive_datetimes_as_utc():
    naive = T0.replace(tzinfo=None)
    assert timing.attempt_deadline(naive, {"time_limit_s": 60, "sections": []}, 0, None) == s(60)


@pytest.mark.parametrize("start,limit,attempt_dl,expected", [
    (s(0), 100, None, s(100)),
    (s(0), 100, s(50), s(50)),
    (s(0), None, s(50), s(50)),   # untimed section follows the attempt deadline
    (s(0), None, None, None),
    (s(10), 100, s(500), s(110)),
])
def test_section_deadline(start, limit, attempt_dl, expected):
    assert timing.section_deadline(start, limit, attempt_dl) == expected


@pytest.mark.parametrize("offset,ok", [(-1, True), (0, True), (44, True), (45, True), (46, False), (600, False)])
def test_grace_edges(offset, ok):
    deadline = s(1000)
    assert timing.writable(deadline, deadline + timedelta(seconds=offset), GRACE) is ok


def test_writable_without_deadline():
    assert timing.writable(None, s(10**7), GRACE) is True


def sec(pos, started, deadline, limit, closed=None):
    return SectionState(pos, started, deadline, closed, limit)


def att(cur, deadline, nav="section_forward_only"):
    return SimpleNamespace(current_section_pos=cur, deadline_at=deadline, navigation=nav)


def chain():
    """Three sections of 100 s each under a 300 s attempt; section 1 started at T0."""
    return [sec(1, s(0), s(100), 100), sec(2, None, None, 100), sec(3, None, None, 100)]


@pytest.mark.parametrize("now_s,expected", [
    (100, []),                       # at the deadline
    (145, []),                       # last grace second
    (146, [("close", 1, s(100), 2, s(100), s(200))]),
    (245, [("close", 1, s(100), 2, s(100), s(200))]),   # section 2 deadline 200 + 45 = 245 still ok
    (246, [("close", 1, s(100), 2, s(100), s(200)), ("close", 2, s(200), 3, s(200), s(300))]),
    (346, [("finalize",)]),          # attempt deadline 300 + 45 passed
])
def test_forward_only_chain(now_s, expected):
    out = timing.advance(chain(), att(1, s(300)), s(now_s), GRACE)
    got = [(t.kind,) if t.kind == "finalize" else
           (t.kind, t.pos, t.at, t.next_pos, t.next_started_at, t.next_deadline_at) for t in out]
    assert got == expected


def test_last_section_expired_finalizes_before_attempt_deadline():
    sections = [sec(1, s(0), s(100), 100, closed=s(100)), sec(2, s(100), s(200), 100)]
    out = timing.advance(sections, att(2, s(1000)), s(246), GRACE)
    assert out == [Transition("finalize", 2, s(200))]


def test_next_section_deadline_is_capped_by_attempt_deadline():
    sections = [sec(1, s(0), s(100), 100), sec(2, None, None, 500)]
    out = timing.advance(sections, att(1, s(250)), s(146), GRACE)
    assert out[0].next_deadline_at == s(250)


def test_untimed_attempt_never_expires():
    sections = [sec(1, s(0), None, None), sec(2, None, None, None)]
    assert timing.advance(sections, att(1, None), s(10**7), GRACE) == []


def test_free_navigation_only_expires_with_the_attempt():
    sections = [sec(1, s(0), s(300), None), sec(2, s(0), s(300), None)]
    assert timing.advance(sections, att(1, s(300), nav="free"), s(345), GRACE) == []
    assert timing.advance(sections, att(1, s(300), nav="free"), s(346), GRACE) == [Transition("finalize", 1, s(300))]
