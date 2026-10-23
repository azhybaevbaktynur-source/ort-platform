"""Phase 3 exam load test: post-run integrity checks (design PHASE_3_DESIGN.md section 8.1).

  python exam_verify.py <run_label>        # run from <worktree>/backend with DATABASE_URL set

Reads loadtest/results/exam_<label>.json (written by exam_load.py) and the acknowledged-answer file it names, then
checks in the database, for that run's assessment:
  lost answers   every acknowledged autosave / submit answer is stored, or superseded by a newer client_ts
                 (submit-body answers of a submit processed after deadline + grace are counted apart: rejected)
  double grades  one scored-hook call per finalized attempt (lt_hook_calls), graded_at set, every item graded once
  finalized      no attempt left in_progress; every section closed; raw_score = sum(item scores)
  grading        correctness agrees with the question key (single_choice / comparison)
  5xx            none in the load results
Server factory (counts ATTEMPT_SCORED_HOOKS calls in lt_hook_calls, inside the grading transaction; optional
server-side request log and admission gate, see Probe):
  LT_PROBE_DIR=<dir> [LT_ADMIT=n] uvicorn --factory --app-dir <repo>/loadtest exam_verify:hooked_app  (cwd: <worktree>/backend)
"""
import asyncio
import atexit
import json
import os
import re
import sys
import time
from collections import Counter
from decimal import Decimal

sys.path.insert(0, os.getcwd())

HERE = os.path.dirname(os.path.abspath(__file__))
GRACE_S = 45


def hooked_app():
    from sqlalchemy import text
    from app.lms.attempts.hooks import ATTEMPT_SCORED_HOOKS
    from app.main import app

    def _count(db, attempt):
        db.execute(text("INSERT INTO lt_hook_calls (attempt_id) VALUES (:a)"), {"a": str(attempt.id)})

    ATTEMPT_SCORED_HOOKS.append(_count)
    return Probe(app, int(os.environ.get("LT_ADMIT", "0")), os.environ.get("LT_PROBE_DIR"))


_KINDS = [("PUT", re.compile(r"/attempts/[^/]+/answers$"), "autosave"),
          ("GET", re.compile(r"/attempts/[^/]+/content$"), "content"),
          ("POST", re.compile(r"/attempts/[^/]+/sections/\d+/close$"), "section_close"),
          ("POST", re.compile(r"/attempts/[^/]+/submit$"), "submit"),
          ("GET", re.compile(r"/attempts/[^/]+$"), "state"),
          ("POST", re.compile(r"/assessments/[^/]+/attempts$"), "start")]


class Probe:
    """Harness only (not app code). Logs every API request server-side (start time, kind, status, ms until the last
    response byte, ms waited for admission) to <LT_PROBE_DIR>/probe_<pid>.csv. With LT_ADMIT=n > 0 it also admits at
    most n requests per process into the app; the rest wait in the event loop holding neither a worker thread nor a
    pool connection (experiment for the 'cap in-flight requests' fix of LOAD_TEST_PRE_PHASE3.md section 3.1)."""

    def __init__(self, app, n, outdir):
        self.app, self.n, self.sem, self.rows, self.last = app, n, None, [], time.time()
        self.path = os.path.join(outdir, f"probe_{os.getpid()}.csv") if outdir else None
        if self.path:
            atexit.register(self.flush)

    def flush(self):
        if self.path and self.rows:
            with open(self.path, "a") as f:
                f.write("".join(",".join(map(str, r)) + "\n" for r in self.rows))
            self.rows = []
        self.last = time.time()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t, p = time.time(), time.perf_counter()
        st, done = [0], [None]

        async def send2(msg):
            if msg["type"] == "http.response.start":
                st[0] = msg["status"]
            elif msg["type"] == "http.response.body" and not msg.get("more_body"):
                done[0] = time.perf_counter()
            await send(msg)

        wait = 0.0
        if self.n > 0:
            if self.sem is None:
                self.sem = asyncio.Semaphore(self.n)
            async with self.sem:
                wait = time.perf_counter() - p
                await self.app(scope, receive, send2)
        else:
            await self.app(scope, receive, send2)
        if self.path and scope["path"].startswith("/api/"):
            kind = next((k for m, rx, k in _KINDS if m == scope["method"] and rx.search(scope["path"])), "other")
            end = done[0] or time.perf_counter()
            self.rows.append((round(t, 3), kind, st[0], round((end - p) * 1000, 2), round(wait * 1000, 2)))
            if len(self.rows) >= 500 or time.time() - self.last > 2:
                self.flush()


def verify(label: str) -> dict:
    from sqlalchemy import create_engine, text
    res = json.load(open(os.path.join(HERE, "results", f"exam_{label}.json")))
    aid = res["exam"]["assessment_id"]
    eng = create_engine(os.environ["DATABASE_URL"])
    out: dict = {"label": label, "assessment_id": aid}
    with eng.connect() as c:
        atts = c.execute(text(
            "SELECT id, user_id, status, submit_reason, graded_at, submitted_at, raw_score, points_possible "
            "FROM attempts WHERE assessment_id = :a AND NOT is_preview"), {"a": aid}).mappings().all()
        out["attempts"] = len(atts)
        out["attempts_per_user_max"] = max(Counter(a["user_id"] for a in atts).values()) if atts else 0
        out["status"] = dict(Counter(a["status"] for a in atts))
        out["submit_reason"] = dict(Counter(a["submit_reason"] or "-" for a in atts))
        out["in_progress_left"] = sum(1 for a in atts if a["status"] == "in_progress")
        out["graded_at_missing"] = sum(1 for a in atts if a["status"] != "in_progress" and a["graded_at"] is None)
        hooks = Counter(str(r[0]) for r in c.execute(text(
            "SELECT h.attempt_id FROM lt_hook_calls h JOIN attempts a ON a.id = h.attempt_id "
            "WHERE a.assessment_id = :a"), {"a": aid}))
        finalized = {str(a["id"]) for a in atts if a["status"] in ("graded", "needs_review")}
        out["hook_calls"] = sum(hooks.values())
        out["hook_double"] = sum(1 for v in hooks.values() if v > 1)
        out["hook_missing"] = len(finalized - set(hooks))
        out["hook_on_unfinalized"] = len(set(hooks) - finalized)
        # every item graded, sum matches, answered before the grade, sections closed
        agg = c.execute(text(
            "SELECT ai.attempt_id, count(*) n, count(ai.correctness) graded, coalesce(sum(ai.score),0) s, "
            "  sum(CASE WHEN ai.answered_at > a.graded_at THEN 1 ELSE 0 END) late "
            "FROM attempt_items ai JOIN attempts a ON a.id = ai.attempt_id "
            "WHERE a.assessment_id = :a AND NOT a.is_preview GROUP BY ai.attempt_id"), {"a": aid}).mappings().all()
        raw = {str(a["id"]): a["raw_score"] for a in atts}
        out["items_total"] = sum(r["n"] for r in agg)
        out["attempts_with_ungraded_items"] = sum(1 for r in agg if r["graded"] != r["n"]
                                                  and raw[str(r["attempt_id"])] is not None)
        out["raw_score_mismatch"] = sum(1 for r in agg if raw[str(r["attempt_id"])] is not None
                                        and Decimal(r["s"]) != Decimal(raw[str(r["attempt_id"])]))
        out["answers_after_grading"] = sum(int(r["late"] or 0) for r in agg)
        out["open_sections_on_finalized"] = c.execute(text(
            "SELECT count(*) FROM attempt_sections s JOIN attempts a ON a.id = s.attempt_id "
            "WHERE a.assessment_id = :a AND a.status <> 'in_progress' AND s.closed_at IS NULL"), {"a": aid}).scalar()
        out["key_mismatch"] = c.execute(text(
            "SELECT count(*) FROM attempt_items ai JOIN attempts a ON a.id = ai.attempt_id "
            "JOIN question_versions qv ON qv.id = ai.question_version_id "
            "WHERE a.assessment_id = :a AND ai.response IS NOT NULL AND ai.correctness IN ('correct','incorrect') "
            "AND ((ai.correctness = 'correct') <> (coalesce(ai.response::jsonb->>'choice_id', ai.response::jsonb->>'choice')"
            "      = (qv.data::jsonb->>'correct')))"), {"a": aid}).scalar()
        # lost answers: latest acknowledged (attempt, position) vs stored row
        stored = {}
        for r in c.execute(text(
                "SELECT ai.attempt_id, ai.position, ai.client_ts, ai.response FROM attempt_items ai "
                "JOIN attempts a ON a.id = ai.attempt_id WHERE a.assessment_id = :a AND ai.client_ts IS NOT NULL"),
                {"a": aid}):
            stored[(str(r[0]), int(r[1]))] = (int(r[2]), r[3])
        late_submit = {str(r[0]) for r in c.execute(text(
            "SELECT id FROM attempts WHERE assessment_id = :a AND submitted_at > deadline_at + make_interval(secs => :g)"),
            {"a": aid, "g": GRACE_S})}
    lost, superseded, exact, n, rejected_late = [], 0, 0, 0, 0
    with open(res["acks_file"]) as f:
        for line in f:
            t, pos, ts, resp, src = json.loads(line)
            n += 1
            s = stored.get((t, pos))
            if s is None or s[0] < ts or (s[0] == ts and s[1] != resp):
                if src == "submit" and t in late_submit:  # final answers judged after deadline + grace: rejected
                    rejected_late += 1                    # by design (SubmitOut does not say which were dropped)
                    continue
                lost.append({"attempt": t, "position": pos, "ack_ts": ts, "stored": s, "src": src})
            elif s[0] > ts:
                superseded += 1
            else:
                exact += 1
    out["acked_positions_checked"] = n
    out["acked_exact"] = exact
    out["acked_superseded"] = superseded
    out["submit_body_rejected_late"] = rejected_late
    out["lost_answers"] = len(lost)
    out["lost_by_src"] = dict(Counter(x["src"] for x in lost))
    out["lost_examples"] = lost[:5]
    out["acked_entries_total"] = res["acks_total"]
    out["started_ok"] = res["started_ok"]
    fivexx = {}
    for name, e in res["endpoints"].items():
        for code, k in e["codes"].items():
            if code.isdigit() and int(code) >= 500 or not code.isdigit():
                fivexx[f"{name}:{code}"] = k
    out["5xx_or_transport"] = fivexx
    out["ok"] = (out["lost_answers"] == 0 and out["hook_double"] == 0 and out["hook_missing"] == 0
                 and out["hook_on_unfinalized"] == 0 and out["in_progress_left"] == 0
                 and out["graded_at_missing"] == 0 and out["attempts_with_ungraded_items"] == 0
                 and out["raw_score_mismatch"] == 0 and out["open_sections_on_finalized"] == 0
                 and out["key_mismatch"] == 0 and out["answers_after_grading"] == 0
                 and out["attempts_per_user_max"] <= 1 and out["attempts"] == res["started_ok"] and not fivexx)
    json.dump(out, open(os.path.join(HERE, "results", f"exam_{label}_verify.json"), "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    verify(sys.argv[1])
