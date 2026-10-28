#!/usr/bin/env python3
"""Deterministic seed for the ORT browser e2e suite, through the HTTP API (run by scripts/e2e_backend.sh).

- users register through /auth/register and confirm with the code the console email provider prints to the
  backend log; passwords are random per run (nothing secret lives in the repository);
- the admin is promoted with backend/make_admin.py and becomes co-teacher of the ORT courses through the ORT
  seed CLI (`python -m app.lms.ort.seed`, what the server does on its next start);
- ORT (Russian): the tsoomo19 bundle is imported as `full_main`; two `ort_main` exams with a fixed small item
  set (every section, comparison items in math_1, one passage group in reading) are built and published:
  "E2E" for the student flows and "E2E staff" for the teacher screens (one submitted seeded attempt, so the
  staff attempts list never depends on which student specs ran);
- students join the course; seed.json (written last) lists ids and tokens for the specs.

Stdlib only, so it runs with any python that has the backend requirements (for make_admin.py)."""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SECTIONS = ["math_1", "math_2", "analogies", "reading", "grammar"]
# items per section (reading: the questions of the first passage)
COUNTS = {"math_1": 3, "math_2": 2, "analogies": 2, "grammar": 2}
STUDENTS = [
    "flow-ru", "flow-ky",
    "vis-phone-ru", "vis-phone-ky", "vis-desktop-ru", "vis-desktop-ky",
    "staff-seed",
    # S11a: phone walk of the palette sheet (after staff-seed, so the seeded names above keep their numbers)
    "flow-phone-ru",
]


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/") + "/api/v1"

    def call(self, method: str, path: str, token: str | None = None, body=None, *, raw: bytes | None = None,
             content_type: str | None = None, ok=(200, 201)):
        headers = {"Accept": "application/json"}
        data = None
        if raw is not None:
            data = raw
            headers["Content-Type"] = content_type or "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                status, text = r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode()
        if status not in ok:
            raise SystemExit(f"seed: {method} {path} -> {status}: {text[:500]}")
        return json.loads(text) if text else None


def multipart(fields: dict[str, str], file_field: str, filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = "e2e" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
               f"Content-Type: application/zip\r\n\r\n".encode() + payload + b"\r\n")
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def code_from_log(log: Path, email: str, timeout: float = 30) -> str:
    """The latest 6-digit code the console email provider printed for this address."""
    end = time.time() + timeout
    pat = re.compile(r"\[EMAIL console\] To: " + re.escape(email) + r" .*?\n(.*?)(?=\n\S*\[EMAIL console\]|\Z)", re.S)
    while time.time() < end:
        text = log.read_text(encoding="utf-8", errors="replace")
        found = pat.findall(text)
        if found:
            codes = re.findall(r"\b(\d{6})\b", found[-1])
            if codes:
                return codes[0]
        time.sleep(0.2)
    raise SystemExit(f"seed: no verification code for {email} in {log}")


def register(api: Api, log: Path, email: str, name: str, lang: str = "ru") -> dict:
    password = secrets.token_urlsafe(18)
    api.call("POST", "/auth/register", body={"email": email, "password": password, "displayName": name, "lang": lang})
    code = code_from_log(log, email)
    out = api.call("POST", "/auth/verify-email", body={"email": email, "password": password, "code": code})
    return {"email": email, "name": name, "token": out["access_token"]}


def profile(api: Api, token: str) -> dict:
    return api.call("GET", "/auth/me", token)


def pages(api: Api, path: str, token: str, **params) -> list[dict]:
    items, cursor = [], None
    while True:
        q = {**params, "limit": 100}
        if cursor:
            q["cursor"] = cursor
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in q.items())
        page = api.call("GET", f"{path}?{qs}", token)
        items += page["items"]
        cursor = page.get("next_cursor")
        if not cursor:
            return items


def ort_ru_course(api: Api, token: str) -> dict:
    for c in pages(api, "/platform/courses", token, q="ORT"):
        title = c.get("title") or {}
        if c.get("template_key", "ort") == "ort" and (c.get("default_language") == "ru" or title.get("en") == "ORT (Russian)"):
            return c
    raise SystemExit("seed: the ORT (Russian) course was not seeded")


def build_exam(api: Api, token: str, cid: str, bank_id: str, title: str, picks: dict[str, list[str]]) -> dict:
    a = api.call("POST", f"/courses/{cid}/assessments", token, {
        "title": {"ru": title, "ky": title, "en": title}, "preset": "ort_main", "languages": ["ru"]})
    assert [s["key"] for s in a["sections"]] == SECTIONS, a["sections"]
    base = f"/courses/{cid}/assessments/{a['id']}"
    for sec in a["sections"]:
        r = api.call("POST", f"{base}/sections/{sec['id']}/items/bulk", token,
                     {"question_ids": picks[sec["key"]], "group_passages": True})
        assert r["added"] == len(picks[sec["key"]]) and not r["skipped"], (sec["key"], r)
    v = api.call("POST", f"{base}/validate", token, {})
    assert not v["errors"], v
    pub = api.call("POST", f"{base}/publish", token, {})
    return {"id": a["id"], "version": pub["version"]["version_no"], "items": pub["version"]["item_count"]}


def seeded_attempt(api: Api, token: str, cid: str, aid: str) -> str:
    """One submitted attempt: the first choice in every item (deterministic), every section closed in order."""
    st = api.call("POST", f"/courses/{cid}/assessments/{aid}/attempts", token, {"language": "ru"})
    tid = st["id"]
    ts = 1000
    for pos in sorted(s["pos"] for s in st["sections"]):
        content = api.call("GET", f"/attempts/{tid}/content?section={pos}", token)
        answers = []
        for it in sorted((i for i in st["items"] if i["section_pos"] == pos), key=lambda i: i["position"]):
            q = content["questions"][it["qv"]]
            ts += 1
            if q["type"] == "comparison":
                resp = {"choice": "A"}
            else:
                order = it.get("choice_order") or [c["id"] for c in q["data"]["choices"]]
                resp = {"choice_id": order[0]}
            answers.append({"position": it["position"], "response": resp, "client_ts": ts})
        api.call("PUT", f"/attempts/{tid}/answers", token, {"answers": answers})
        if pos < len(st["sections"]):
            api.call("POST", f"/attempts/{tid}/sections/{pos}/close", token, {})
    api.call("POST", f"/attempts/{tid}/submit", token, {})
    return tid


# --- Phase 7c S5 begin --- (quiz editor walk, frontend/e2e/quiz-editor.spec.ts; written after every ORT row, so the
# ORT data and screens are exactly as before)
def sc(stem: str, right: str, wrong: str) -> dict:
    return {"type": "single_choice", "language": "ru", "stem": stem, "explanation": None,
            "data": {"choices": [{"id": "A", "text": wrong}, {"id": "B", "text": right}], "correct": "B"}}


def seed_quiz_editor(api: Api, log: Path, admin_tok: str) -> dict:
    """A general course (not ORT) of an approved teacher: a shared bank with two questions, quiz "Квиз Б" that
    already uses both (published, so "the second quiz is unchanged" can be checked), an empty quiz "Квиз А" for the
    walk, and one enrolled student."""
    teacher = register(api, log, "e2e-teacher@example.com", "E2E Teacher")
    tp = profile(api, teacher["token"])
    api.call("POST", f"/platform/users/{tp['id']}/teacher-status", admin_tok, {"status": "approved"})
    teacher["profile"] = profile(api, teacher["token"])
    tok = teacher["token"]
    title = {"ru": "Общий курс E2E", "ky": "Жалпы курс E2E", "en": "General course E2E"}
    course = api.call("POST", "/courses", tok, {"title": title, "languages": ["ru", "ky", "en"], "default_language": "ru"})
    cid = course["id"]
    api.call("POST", f"/courses/{cid}/publish", tok, {})
    bank = api.call("POST", f"/courses/{cid}/banks", tok, {"title": "Общий банк", "default_language": "ru"})
    shared = [
        api.call("POST", f"/courses/{cid}/banks/{bank['id']}/questions", tok, sc("Столица Кыргызстана?", "Бишкек", "Ош")),
        api.call("POST", f"/courses/{cid}/banks/{bank['id']}/questions", tok, sc("Сколько будет 3 + 4?", "7", "8")),
    ]

    def quiz(name: str) -> dict:
        return api.call("POST", f"/courses/{cid}/assessments", tok, {
            "title": {"ru": name, "ky": name, "en": name}, "preset": "none", "languages": ["ru"]})

    quiz_a = quiz("Квиз А")
    quiz_b = quiz("Квиз Б")
    base_b = f"/courses/{cid}/assessments/{quiz_b['id']}"
    sec = api.call("POST", f"{base_b}/sections", tok, {})
    api.call("POST", f"{base_b}/sections/{sec['id']}/items/bulk", tok, {"question_ids": [q["id"] for q in shared]})
    pub_b = api.call("POST", f"{base_b}/publish", tok, {})
    student = register(api, log, "e2e-quiz-student@example.com", "Quiz Student")
    student["profile"] = profile(api, student["token"])
    api.call("POST", "/courses/join", student["token"], {"code": course["join_code"]})
    return {
        "course_id": cid, "bank_id": bank["id"], "shared_question_ids": [q["id"] for q in shared],
        "quiz_a": quiz_a["id"], "quiz_b": quiz_b["id"], "quiz_b_version": pub_b["version"]["version_no"],
        "teacher": teacher, "student": student,
    }
# --- Phase 7c S5 end ---


# --- Phase 8a S5 begin --- (modules walk, frontend/e2e/modules.spec.ts; written after every ORT and quiz-editor row, so
# those rows and screens are exactly as before)
def seed_modules(api: Api, log: Path, admin_tok: str, ort_course_id: str) -> dict:
    """A general course (ru, ky, en) of a second approved teacher, published, with no structure yet (the walk builds
    it in the browser) and one enrolled student; plus one extra ORT (Russian) student for the ORT proof of the walk
    (ORT exam listed in a locked module still starts)."""
    teacher = register(api, log, "e2e-modules-teacher@example.com", "Modules Teacher")
    tp = profile(api, teacher["token"])
    api.call("POST", f"/platform/users/{tp['id']}/teacher-status", admin_tok, {"status": "approved"})
    teacher["profile"] = profile(api, teacher["token"])
    tok = teacher["token"]
    title = {"ru": "Курс модулей E2E", "ky": "Модулдар курсу E2E", "en": "Modules course E2E"}
    course = api.call("POST", "/courses", tok, {"title": title, "languages": ["ru", "ky", "en"], "default_language": "ru"})
    cid = course["id"]
    api.call("POST", f"/courses/{cid}/publish", tok, {})
    student = register(api, log, "e2e-modules-student@example.com", "Modules Student")
    student["profile"] = profile(api, student["token"])
    api.call("POST", "/courses/join", student["token"], {"code": course["join_code"]})
    ort_student = register(api, log, "e2e-ort-modules@example.com", "ORT Modules Student")
    ort_student["profile"] = profile(api, ort_student["token"])
    api.call("POST", f"/courses/{ort_course_id}/join", ort_student["token"], {})
    return {"course_id": cid, "join_code": course["join_code"], "teacher": teacher, "student": student,
            "ort_student": ort_student}
# --- Phase 8a S5 end ---


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    api, log, root = Api(args.api), Path(args.log), Path(args.root)
    out_path = Path(args.out)
    if out_path.exists():
        out_path.unlink()

    admin = register(api, log, "e2e-admin@example.com", "E2E Admin")
    subprocess.run([sys.executable, str(root / "backend" / "make_admin.py"), admin["email"]], check=True,
                   env=os.environ.copy(), stdout=subprocess.DEVNULL)
    # what the server does on its next start: platform admins become co-teachers of the ORT courses (P5-6)
    subprocess.run([sys.executable, "-m", "app.lms.ort.seed"], check=True, env=os.environ.copy(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tok = admin["token"]
    me = profile(api, tok)
    assert me.get("is_platform_admin"), me
    admin["profile"] = me

    course = ort_ru_course(api, tok)
    cid = course["id"]
    body, ctype = multipart({"language": "ru", "exam_type": "full_main"}, "file", "tsoomo19.zip",
                            (root / "backend/tests/fixtures/bundles/tsoomo19.zip").read_bytes())
    rep = api.call("POST", f"/courses/{cid}/imports", tok, raw=body, content_type=ctype)
    bank_id = rep["banks"][0]["bank_id"]

    qpath = f"/courses/{cid}/banks/{bank_id}/questions"
    picks: dict[str, list[str]] = {}
    comparison_qid = None
    for key in SECTIONS:
        qs = pages(api, qpath, tok, section=key)
        assert qs, key
        if key == "reading":
            pid = next(q["passage_id"] for q in qs if q.get("passage_id"))
            picks[key] = [q["id"] for q in qs if q.get("passage_id") == pid]
            passage_id = pid
        else:
            picks[key] = [q["id"] for q in qs[:COUNTS[key]]]
        if key == "math_1":
            assert all(q["type"] == "comparison" for q in qs[:COUNTS[key]]), qs[:3]
            comparison_qid = picks[key][0]

    # answer keys (staff view): index of the correct answer button as the player shows it (choices not shuffled)
    keys: dict[str, dict] = {}
    for key in SECTIONS:
        for qid in picks[key]:
            d = api.call("GET", f"/courses/{cid}/questions/{qid}", tok)["current_version"]["data"]
            if "column_a" in d:
                keys[qid] = {"type": "comparison", "correct": "ABCD".index(d["correct"]), "choices": 4}
            else:
                ids = [c["id"] for c in d["choices"]]
                keys[qid] = {"type": "single_choice", "correct": ids.index(d["correct"]), "choices": len(ids)}

    exam = build_exam(api, tok, cid, bank_id, "ОРТ E2E", picks)
    staff_exam = build_exam(api, tok, cid, bank_id, "ОРТ E2E staff", picks)

    students = {}
    for i, key in enumerate(STUDENTS):
        s = register(api, log, f"e2e-{key}@example.com", f"Student {i + 1:02d}", "ky" if key.endswith("ky") else "ru")
        s["profile"] = profile(api, s["token"])
        api.call("POST", f"/courses/{cid}/join", s["token"], {})
        students[key] = s
    staff_attempt = seeded_attempt(api, students["staff-seed"]["token"], cid, staff_exam["id"])

    quiz_editor = seed_quiz_editor(api, log, tok)  # Phase 7c S5 (after every ORT row)
    modules = seed_modules(api, log, tok, cid)  # Phase 8a S5 (after every ORT and quiz-editor row)

    seed = {
        "quiz_editor": quiz_editor,
        "modules": modules,
        "api": args.api, "course_id": cid, "bank_id": bank_id, "exam": exam, "staff_exam": staff_exam,
        "picks": picks, "keys": keys, "comparison_question_id": comparison_qid, "passage_id": passage_id,
        "staff_attempt_id": staff_attempt, "admin": admin, "students": students,
    }
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    print(f"seed: course {cid}, exam {exam}, staff exam {staff_exam}, {len(students)} students")
    return 0


if __name__ == "__main__":
    sys.exit(main())
