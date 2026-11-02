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
import sqlite3
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
    # BLUEBOOK_PLAYER: review page and split screen walks
    "bb-review-ru", "bb-split-ru", "bb-screens-ru",
    # UX rework 2: mascot spec (no mascot in the player; on the result page)
    "mascot-player-ru", "mascot-result-ru",
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


def _policy_ids(api: Api) -> list[str]:
    """Phase 11: the sign-up accepts the current privacy and terms."""
    return [p["id"] for p in api.call("GET", "/privacy/policies/current") if p["kind"] in ("privacy", "terms")]


def register(api: Api, log: Path, email: str, name: str, lang: str = "ru", *, keep_password: bool = False) -> dict:
    password = secrets.token_urlsafe(18)
    api.call("POST", "/auth/register", body={"email": email, "password": password, "displayName": name, "lang": lang,
                                             "ageBand": "18_plus", "policyVersionIds": _policy_ids(api)})
    code = code_from_log(log, email)
    out = api.call("POST", "/auth/verify-email", body={"email": email, "password": password, "code": code})
    user = {"email": email, "name": name, "token": out["access_token"]}
    if keep_password:  # random per run, in the scratch seed.json only
        user["password"] = password
    return user


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


# --- Phase 8b S3 begin --- (scrolling display mode, frontend/e2e/scrolling-player.spec.ts; written after every ORT,
# quiz-editor and modules row, so those rows and screens are exactly as before)
SCROLL_STUDENTS = ["walk", "phone", "forward", "page", "base", "shots", "bb-scroll", "bb-timer", "bb-keys", "bb-screens"]


def seed_scrolling(api: Api, log: Path, admin_tok: str) -> dict:
    """A general course (ru, ky, en) of a third approved teacher with three published quizzes:
    - "Длинный тест E2E": scrolling, free navigation, 60 min, numbered passages; section 1 has 45 single-choice
      questions (windowing), section 2 a passage with two questions and one plain question;
    - "Пошаговый тест E2E": scrolling, forward-only, two sections of two questions, 10 min each;
    - "Постраничный тест E2E": one question per page (the default), three questions.
    Six enrolled students (one per spec test, so no test depends on another)."""
    teacher = register(api, log, "e2e-scroll-teacher@example.com", "Scroll Teacher")
    tp = profile(api, teacher["token"])
    api.call("POST", f"/platform/users/{tp['id']}/teacher-status", admin_tok, {"status": "approved"})
    teacher["profile"] = profile(api, teacher["token"])
    tok = teacher["token"]
    title = {"ru": "Курс прокрутки E2E", "ky": "Жылдыруу курсу E2E", "en": "Scrolling course E2E"}
    course = api.call("POST", "/courses", tok, {"title": title, "languages": ["ru", "ky", "en"], "default_language": "ru"})
    cid = course["id"]
    api.call("POST", f"/courses/{cid}/publish", tok, {})
    bank = api.call("POST", f"/courses/{cid}/banks", tok, {"title": "Банк прокрутки", "default_language": "ru"})
    qpath = f"/courses/{cid}/banks/{bank['id']}/questions"

    def question(stem: str, right: str, wrong: str, passage_id: str | None = None) -> str:
        body = sc(stem, right, wrong)
        if passage_id:
            body["passage_id"] = passage_id
        return api.call("POST", qpath, tok, body)["id"]

    def quiz(name: str, settings: dict) -> tuple[str, str]:
        a = api.call("POST", f"/courses/{cid}/assessments", tok, {
            "title": {"ru": name, "ky": name, "en": name}, "preset": "none", "languages": ["ru"]})
        api.call("PATCH", f"/courses/{cid}/assessments/{a['id']}", tok, {"draft_rev": a["draft_rev"], **settings})
        return a["id"], f"/courses/{cid}/assessments/{a['id']}"

    def section(base: str, name: str, time_limit_s: int | None = None) -> str:
        body: dict = {"title": {"ru": name, "ky": name, "en": name}}
        if time_limit_s:
            body["time_limit_s"] = time_limit_s
        return api.call("POST", f"{base}/sections", tok, body)["id"]

    # the long quiz: 45 + (passage 2 + 1)
    long_id, base = quiz("Длинный тест E2E", {"display_mode": "scrolling", "passage_display": "numbered",
                                             "time_limit_s": 3600, "show_correct_answers": True})
    s1 = section(base, "Часть 1")
    long_q = [question(f"Вопрос {i}: сколько будет {i} + 1?", str(i + 1), str(i + 2)) for i in range(1, 46)]
    api.call("POST", f"{base}/sections/{s1}/items/bulk", tok, {"question_ids": long_q})
    s2 = section(base, "Часть 2")
    passage = api.call("POST", f"/courses/{cid}/banks/{bank['id']}/passages", tok, {
        "language": "ru", "title": "Текст о горах",
        "body": "Горы Тянь-Шаня тянутся на тысячи километров.\nВысочайшая вершина — пик Победы.\n"
                "Летом на пастбищах пасут скот.\nЗимой в горах много снега.\nРеки начинаются у ледников.\n"
                "Озеро Иссык-Куль не замерзает зимой."})
    pq = [question("Как называется высочайшая вершина?", "Пик Победы", "Хан-Тенгри", passage["id"]),
          question("Что делают летом на пастбищах?", "Пасут скот", "Сеют рис", passage["id"])]
    api.call("POST", f"{base}/sections/{s2}/items", tok, {"kind": "passage", "passage_id": passage["id"], "question_ids": pq})
    api.call("POST", f"{base}/sections/{s2}/items", tok,
             {"kind": "question", "question_id": question("Столица Кыргызстана?", "Бишкек", "Ош")})
    api.call("POST", f"{base}/publish", tok, {})

    # the forward-only quiz
    fwd_id, base = quiz("Пошаговый тест E2E", {"display_mode": "scrolling", "navigation": "section_forward_only"})
    for n in (1, 2):
        sid = section(base, f"Этап {n}", 600)
        qs = [question(f"Этап {n}, вопрос {i}: {n} × {i}?", str(n * i), str(n * i + 1)) for i in (1, 2)]
        api.call("POST", f"{base}/sections/{sid}/items/bulk", tok, {"question_ids": qs})
    api.call("POST", f"{base}/publish", tok, {})

    # the one-per-page quiz (default display)
    page_id, base = quiz("Постраничный тест E2E", {})
    sid = section(base, "Часть 1")
    qs = [question(f"Страница, вопрос {i}: {i} + {i}?", str(2 * i), str(2 * i + 1)) for i in (1, 2, 3)]
    api.call("POST", f"{base}/sections/{sid}/items/bulk", tok, {"question_ids": qs})
    api.call("POST", f"{base}/publish", tok, {})

    students = {}
    for key in SCROLL_STUDENTS:
        s = register(api, log, f"e2e-scroll-{key}@example.com", f"Scroll {key}")
        s["profile"] = profile(api, s["token"])
        api.call("POST", "/courses/join", s["token"], {"code": course["join_code"]})
        students[key] = s
    return {"course_id": cid, "long_quiz": long_id, "forward_quiz": fwd_id, "page_quiz": page_id,
            "teacher": teacher, "students": students}
# --- Phase 8b S3 end ---


# --- Phase 9 S4 begin --- (enrollment form, catalog, apply, inbox: frontend/e2e/catalog-apply.spec.ts; written after
# every other row, so the ORT and earlier walks see exactly the rows they saw before)
def seed_catalog_apply(api: Api, log: Path, admin_tok: str) -> dict:
    """A published, private general course (ru, ky, en) of an approved teacher, no form yet, and one student who is
    in no course (the applicant). The walk builds the form, opens the course to the catalog and applies."""
    teacher = register(api, log, "e2e-apply-teacher@example.com", "Apply Teacher")
    tp = profile(api, teacher["token"])
    api.call("POST", f"/platform/users/{tp['id']}/teacher-status", admin_tok, {"status": "approved"})
    teacher["profile"] = profile(api, teacher["token"])
    tok = teacher["token"]
    title = {"ru": "Курс с анкетой E2E", "ky": "Анкеталуу курс E2E", "en": "Application course E2E"}
    course = api.call("POST", "/courses", tok, {"title": title, "languages": ["ru", "ky", "en"], "default_language": "ru"})
    api.call("POST", f"/courses/{course['id']}/publish", tok, {})
    student = register(api, log, "e2e-apply-student@example.com", "Айдана Заявка")
    student["profile"] = profile(api, student["token"])
    # --- Phase 9 S5 --- (more applicants: withdraw, reject, form_auto; registered after the S4 rows)
    others = {}
    for key, name in (("withdraw", "Бакыт Отзыв"), ("reject", "Нурлан Отказ"), ("auto", "Айгуль Авто")):
        u = register(api, log, f"e2e-apply-{key}@example.com", name)
        u["profile"] = profile(api, u["token"])
        others[key] = u
    return {"course_id": course["id"], "teacher": teacher, "student": student, "applicants": others}
# --- Phase 9 S4 end ---


# --- Phase 9 S5 begin --- (organization walk: departments, settings, usage, shared banks, roster import, student
# invitations; frontend/e2e/org-admin.spec.ts; written after every other row)
def seed_org_admin(api: Api, log: Path, admin_tok: str) -> dict:
    """School "Лицей 61 E2E" (root, teachers may create courses, bank sharing off: the walk turns it on) with an org
    admin and two member teachers: "maths" owns the published course "Математика E2E" with a private bank "Алгебра
    E2E" (two questions), "languages" owns the published course "Языки E2E". Outside the school: an approved teacher
    with an account (the roster file adds him to a department), a student with an account (roster invitation), a
    student for the People → Invitations walk, and an independent teacher (personal organization only)."""
    org = api.call("POST", "/platform/organizations", admin_tok, {"name": "Лицей 61 E2E", "slug": "e2e-lyceum-61",
                                                                    "settings": {"teachers_can_create_courses": True}})
    oid = org["id"]

    def person(email: str, name: str, *, teacher: bool, role: str | None = None) -> dict:
        u = register(api, log, email, name)
        if teacher:
            uid = profile(api, u["token"])["id"]
            api.call("POST", f"/platform/users/{uid}/teacher-status", admin_tok, {"status": "approved"})
        u["profile"] = profile(api, u["token"])
        if role:
            api.call("POST", f"/platform/organizations/{oid}/members", admin_tok,
                     {"user_id": u["profile"]["id"], "role": role})
        return u

    org_admin = person("e2e-lyceum-admin@example.com", "Админ Лицея", teacher=False, role="org_admin")
    maths = person("e2e-lyceum-maths@example.com", "Преподаватель Математики", teacher=True, role="teacher")
    languages = person("e2e-lyceum-lang@example.com", "Преподаватель Языков", teacher=True, role="teacher")
    roster_teacher = person("e2e-roster-teacher@example.com", "Преподаватель Из Списка", teacher=True)
    roster_student = person("e2e-roster-student@example.com", "Ученик Из Списка", teacher=False)
    invite_student = person("e2e-invite-student@example.com", "Ученик По Приглашению", teacher=False)
    independent = person("e2e-independent@example.com", "Независимый Преподаватель", teacher=True)

    def course(owner: dict, ru: str, ky: str, en: str) -> str:
        c = api.call("POST", "/courses", owner["token"], {"title": {"ru": ru, "ky": ky, "en": en},
                                                          "languages": ["ru", "ky", "en"], "default_language": "ru",
                                                          "organization_id": oid})
        api.call("POST", f"/courses/{c['id']}/publish", owner["token"], {})
        return c["id"]

    maths_cid = course(maths, "Математика E2E", "Математика E2E", "Maths E2E")
    lang_cid = course(languages, "Языки E2E", "Тилдер E2E", "Languages E2E")
    bank = api.call("POST", f"/courses/{maths_cid}/banks", maths["token"],
                    {"title": "Алгебра E2E", "default_language": "ru"})
    for q in (sc("Сколько будет 2 + 2?", "4", "5"), sc("Сколько будет 3 · 3?", "9", "6")):
        api.call("POST", f"/courses/{maths_cid}/banks/{bank['id']}/questions", maths["token"], q)
    return {"organization_id": oid, "org_admin": org_admin, "maths": maths, "languages": languages,
            "maths_course_id": maths_cid, "languages_course_id": lang_cid, "bank_id": bank["id"],
            "roster_teacher": roster_teacher, "roster_student": roster_student, "invite_student": invite_student,
            "independent": independent}
# --- Phase 9 S5 end ---


# --- Phase 8c S4a begin --- (course navigation, frontend/e2e/course-nav.spec.ts; written after every other row)
NAV_STUDENTS = ["sidebar", "handin", "phone", "assistant"]


def seed_course_nav(api: Api, log: Path, admin_tok: str) -> dict:
    """A general course (ru, ky, en) of a fourth approved teacher, published and empty (the spec builds its content
    through the API and the browser), with three enrolled students: "sidebar" (auto-hide, drawer-free checks),
    "handin" (hands an assignment in for the To do deep link) and "phone" (the phone drawer)."""
    teacher = register(api, log, "e2e-nav-teacher@example.com", "Nav Teacher")
    tp = profile(api, teacher["token"])
    api.call("POST", f"/platform/users/{tp['id']}/teacher-status", admin_tok, {"status": "approved"})
    teacher["profile"] = profile(api, teacher["token"])
    tok = teacher["token"]
    title = {"ru": "Навигация E2E", "ky": "Навигация E2E", "en": "Navigation E2E"}
    course = api.call("POST", "/courses", tok, {"title": title, "languages": ["ru", "ky", "en"], "default_language": "ru"})
    cid = course["id"]
    api.call("POST", f"/courses/{cid}/publish", tok, {})
    students = {}
    for key in NAV_STUDENTS:
        s = register(api, log, f"e2e-nav-{key}@example.com", f"Nav {key}")
        s["profile"] = profile(api, s["token"])
        api.call("POST", "/courses/join", s["token"], {"code": course["join_code"]})
        students[key] = s
    # "assistant": promoted to course assistant. Student view downgrades a real teacher/assistant, also the owner who
    # administers their personal organization (fix 2); the Student view checks run as this assistant and as the owner.
    mine = api.call("GET", f"/courses/{cid}", students["assistant"]["token"])["my_enrollment"]["id"]
    api.call("PATCH", f"/courses/{cid}/enrollments/{mine}", tok, {"role": "assistant"})
    # one published quiz with one question (Student view "Start" opens a preview attempt)
    bank = api.call("POST", f"/courses/{cid}/banks", tok, {"title": "Банк навигации", "default_language": "ru"})
    qid = api.call("POST", f"/courses/{cid}/banks/{bank['id']}/questions", tok, sc("Сколько будет 1 + 1?", "2", "3"))["id"]
    a = api.call("POST", f"/courses/{cid}/assessments", tok, {
        "title": {"ru": "Квиз просмотра", "ky": "Квиз просмотра", "en": "Preview quiz"}, "preset": "none", "languages": ["ru"]})
    abase = f"/courses/{cid}/assessments/{a['id']}"
    sid = api.call("POST", f"{abase}/sections", tok, {"title": {"ru": "Часть 1", "ky": "Часть 1", "en": "Part 1"}})["id"]
    api.call("POST", f"{abase}/sections/{sid}/items/bulk", tok, {"question_ids": [qid]})
    api.call("POST", f"{abase}/publish", tok, {})
    return {"course_id": cid, "join_code": course["join_code"], "teacher": teacher, "students": students,
            "view_quiz": a["id"]}
# --- Phase 8c S4a end ---


# --- Phase 8b S5 begin --- (exam-template constructor walk, frontend/e2e/exam-constructor.spec.ts; written after every
# other row, so the ORT, quiz-editor, modules and scrolling rows and screens are exactly as before)
def seed_constructor(api: Api, log: Path, admin_tok: str) -> dict:
    """An organization "Школа E2E" with an org admin and an approved teacher member; the teacher's published course
    "Курс школы E2E" (ru, ky, en) in that organization with two enrolled students; and a published teacher-scope
    template "Шаблон учителя E2E" of that teacher (the org admin promotes it in the walk). The organization template
    itself is designed in the browser by the walk."""
    org = api.call("POST", "/platform/organizations", admin_tok, {"name": "Школа E2E", "slug": "e2e-school",
                                                                    "settings": {"teachers_can_create_courses": True}})
    oid = org["id"]

    def person(email: str, name: str, *, teacher: bool) -> dict:
        u = register(api, log, email, name)
        if teacher:
            uid = profile(api, u["token"])["id"]
            api.call("POST", f"/platform/users/{uid}/teacher-status", admin_tok, {"status": "approved"})
        u["profile"] = profile(api, u["token"])
        return u

    org_admin = person("e2e-org-admin@example.com", "Org Admin", teacher=False)
    api.call("POST", f"/platform/organizations/{oid}/members", admin_tok,
             {"user_id": org_admin["profile"]["id"], "role": "org_admin"})
    teacher = person("e2e-org-teacher@example.com", "School Teacher", teacher=True)
    api.call("POST", f"/platform/organizations/{oid}/members", admin_tok,
             {"user_id": teacher["profile"]["id"], "role": "teacher"})
    tok = teacher["token"]
    title = {"ru": "Курс школы E2E", "ky": "Мектеп курсу E2E", "en": "School course E2E"}
    course = api.call("POST", "/courses", tok, {"title": title, "languages": ["ru", "ky", "en"],
                                                 "default_language": "ru", "organization_id": oid})
    cid = course["id"]
    api.call("POST", f"/courses/{cid}/publish", tok, {})
    students = {}
    for key in ("walk", "phone"):
        s = person(f"e2e-constructor-{key}@example.com", f"Constructor {key}", teacher=False)
        api.call("POST", "/courses/join", s["token"], {"code": course["join_code"]})
        students[key] = s

    name = "Шаблон учителя E2E"
    tt = api.call("POST", "/exam-templates", tok, {
        "owner_scope": "teacher", "organization_id": oid, "title": {"ru": name, "ky": name, "en": name},
        "draft_spec": {"schema": 1, "parameters": [], "lock_scope": [],
                       "sections": [{"key": None, "title": {"ru": "Часть 1"}, "allowed_types": ["single_choice"]}]}})
    api.call("POST", f"/exam-templates/{tt['id']}/publish", tok, {})
    return {"organization_id": oid, "course_id": cid, "join_code": course["join_code"], "org_admin": org_admin,
            "teacher": teacher, "students": students, "teacher_template_id": tt["id"]}
# --- Phase 8b S5 end ---


# --- Phase 11 S3 begin --- (frontend/e2e/privacy.spec.ts; written after every other row)
def scratch_sql(sql: str, *params) -> None:
    """Puts an account in a state the API cannot reach (an account from before Phase 11, a closed grace period). Only the
    scratch SQLite database of this run."""
    url = os.environ["DATABASE_URL"]
    assert url.startswith("sqlite:///"), url
    with sqlite3.connect(url.removeprefix("sqlite:///")) as con:
        con.execute(sql, params)


def seed_privacy(api: Api, log: Path, ort_course_id: str, exam_id: str) -> dict:
    """An account from before Phase 11 (no band, no consents); a student whose gate closed during an open ORT attempt;
    a student with an open export request (the admin's table)."""
    legacy = register(api, log, "e2e-privacy-legacy@example.com", "Legacy Student")
    legacy["profile"] = profile(api, legacy["token"])
    uid = legacy["profile"]["id"]
    scratch_sql("DELETE FROM consent_records WHERE user_id = ?", uid)
    scratch_sql("UPDATE users SET age_band = NULL, consent_state = 'legacy' WHERE id = ?", uid)

    gated = register(api, log, "e2e-privacy-gated@example.com", "Gated Student")
    gated["profile"] = profile(api, gated["token"])
    api.call("POST", f"/courses/{ort_course_id}/join", gated["token"], {})
    st = api.call("POST", f"/courses/{ort_course_id}/assessments/{exam_id}/attempts", gated["token"], {"language": "ru"})
    gated["attempt_id"] = st["id"]
    scratch_sql("UPDATE users SET age_band = 'under_14', consent_state = 'pending_guardian', "
                "consent_due_at = '2020-01-01 00:00:00.000000' WHERE id = ?", gated["profile"]["id"])

    requester = register(api, log, "e2e-privacy-requester@example.com", "Export Student")
    requester["profile"] = profile(api, requester["token"])
    api.call("POST", "/me/privacy/requests", requester["token"], {"kind": "export"})
    return {"legacy": legacy, "gated": gated, "requester": requester}
# --- Phase 11 S3 end ---


# --- Accounts begin --- (frontend/e2e/teacher-signup.spec.ts; written after every other row. One person per test, so
# no test depends on another.)
APPLICATION = {"school": "Лицей 7", "subject": "Математика", "phone": "+996 700 111 222"}


def seed_teacher_signup(api: Api, log: Path, admin_tok: str, school_id: str, school_admin: dict) -> dict:
    def person(key: str, name: str, **kw) -> dict:
        u = register(api, log, f"e2e-signup-{key}@example.com", name, **kw)
        u["profile"] = profile(api, u["token"])
        return u

    def applied(key: str, name: str, **fields) -> dict:
        u = person(key, name)
        u["request_id"] = api.call("POST", "/me/teacher-requests", u["token"],
                                   {"applicant_name": name, **APPLICATION, **fields})["id"]
        return u

    def teacher(key: str, name: str) -> dict:
        u = person(key, name)
        api.call("POST", f"/platform/users/{u['profile']['id']}/teacher-status", admin_tok, {"status": "approved"})
        u["profile"] = profile(api, u["token"])
        return u

    def course(owner: dict, title: str) -> dict:
        c = api.call("POST", "/courses", owner["token"], {"title": {"ru": title, "ky": title, "en": title},
                                                          "languages": ["ru", "ky", "en"], "default_language": "ru"})
        api.call("POST", f"/courses/{c['id']}/publish", owner["token"], {})
        return c

    registered = person("registered", "Уже Зарегистрирован", keep_password=True)
    student = person("student", "Ученик Без Заявки")
    no_links = person("no-links", "Ученик Без Ссылок")
    legacy = person("legacy", "Старый Аккаунт")
    scratch_sql("DELETE FROM consent_records WHERE user_id = ?", legacy["profile"]["id"])
    scratch_sql("UPDATE users SET age_band = NULL, consent_state = 'legacy' WHERE id = ?", legacy["profile"]["id"])
    minor = person("minor", "Ученик Шестнадцати Лет")
    scratch_sql("UPDATE users SET age_band = '14_17' WHERE id = ?", minor["profile"]["id"])

    pending = applied("pending", "Айгуль На Рассмотрении", message="Веду олимпиадную группу.")
    approve = applied("approve", "Бакыт Одобряемый", message="Преподаю пять лет.")
    rejected = applied("rejected", "Отклонённая Заявка")
    api.call("POST", f"/platform/teacher-requests/{rejected['request_id']}/reject", admin_tok, {"reason": "Нет данных о школе"})
    waited = applied("waited", "Подождавший Неделю")
    api.call("POST", f"/platform/teacher-requests/{waited['request_id']}/reject", admin_tok, {"reason": "Нет данных о школе"})
    scratch_sql("UPDATE teacher_requests SET decided_at = '2020-01-01 00:00:00.000000' WHERE id = ?",
                waited["request_id"].replace("-", ""))
    # a teacher of the school who also applies: the queue says where they teach
    school_teacher = applied("school-teacher", "Учитель Из Школы")
    api.call("POST", f"/platform/organizations/{school_id}/members", admin_tok,
             {"user_id": school_teacher["profile"]["id"], "role": "teacher"})

    invitee = person("invitee", "Приглашённый Учитель")
    api.call("POST", f"/org/{school_id}/invitations", school_admin["token"],
             {"email": invitee["email"], "role": "teacher", "language": "ru"})

    independent = teacher("independent", "Независимый С Курсом")
    independent_course = course(independent, "Мой курс E2E")
    orgs = api.call("GET", "/me/organizations", independent["token"])["items"]
    personal_id = next(o["id"] for o in orgs if o["kind"] == "personal")
    name = "Шаблон моей организации E2E"
    template = api.call("POST", "/exam-templates", independent["token"], {
        "owner_scope": "organization", "organization_id": personal_id, "title": {"ru": name, "ky": name, "en": name},
        "draft_spec": {"schema": 1, "parameters": [], "lock_scope": [],
                       "sections": [{"key": None, "title": {"ru": "Часть 1"}, "allowed_types": ["single_choice"]}]}})

    # a person with their own courses and a school: the course picker must not show their name
    both = teacher("both", "Учитель С Двумя Местами")
    api.call("POST", f"/platform/organizations/{school_id}/members", admin_tok,
             {"user_id": both["profile"]["id"], "role": "teacher"})

    revoked = teacher("revoked", "Отозванный Учитель")
    course(revoked, "Замороженный курс E2E")
    api.call("POST", f"/platform/users/{revoked['profile']['id']}/teacher-status", admin_tok,
             {"status": "revoked", "reason": "Жалоба"})
    revoked["profile"] = profile(api, revoked["token"])

    revoke_target = teacher("revoke-target", "Учитель Под Отзывом")
    target_course = course(revoke_target, "Курс под отзывом E2E")
    target_student = person("revoke-student", "Ученик Учителя Под Отзывом")
    api.call("POST", "/courses/join", target_student["token"], {"code": target_course["join_code"]})

    return {"registered": registered, "student": student, "no_links": no_links, "legacy": legacy, "minor": minor,
            "pending": pending, "approve": approve, "rejected": rejected, "waited": waited,
            "school_teacher": school_teacher, "invitee": invitee, "school_name": "Лицей 61 E2E",
            "independent": independent, "independent_course_id": independent_course["id"],
            "personal_org_id": personal_id, "personal_template_id": template["id"], "personal_template_name": name,
            "both": both, "revoked": revoked, "revoke_target": revoke_target}
# --- Accounts end ---


# --- Landing screens begin --- (frontend/e2e/landing-screens.spec.ts; written after every other row)
def tri(ru: str, ky: str, en: str) -> dict:
    return {"ru": ru, "ky": ky, "en": en}


def seed_landing(api: Api, log: Path, admin_tok: str, ort_course_id: str) -> dict:
    """A school that reads like a real one for the landing page screenshots: a teacher with two courses (modules, pages,
    assignments, quizzes), three students, one handed-in assignment to check, one quiz result. Fictional people, private
    courses (not in the catalog), no "E2E" in anything visible."""
    from datetime import datetime, timedelta, timezone

    def due(days: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=17, minute=59, second=0, microsecond=0).isoformat()  # 23:59 in Bishkek

    def person(email: str, name: str) -> dict:
        p = register(api, log, email, name)
        p["profile"] = profile(api, p["token"])
        return p

    teacher = person("e2e-landing-teacher@example.com", "Гулзат Мамбетова")
    api.call("POST", f"/platform/users/{teacher['profile']['id']}/teacher-status", admin_tok, {"status": "approved"})
    teacher["profile"] = profile(api, teacher["token"])
    tok = teacher["token"]
    student = person("e2e-landing-student@example.com", "Айбек Осмонов")
    classmates = [person("e2e-landing-classmate-1@example.com", "Элина Жумабаева"),
                  person("e2e-landing-classmate-2@example.com", "Темирлан Султанов")]

    def new_course(title: dict) -> dict:
        c = api.call("POST", "/courses", tok, {"title": title, "languages": ["ru", "ky", "en"], "default_language": "ru"})
        api.call("POST", f"/courses/{c['id']}/publish", tok, {})
        for s in [student, *classmates]:
            api.call("POST", "/courses/join", s["token"], {"code": c["join_code"]})
        return c

    def task(cid: str, kind: str, title: dict, days: int, points: int) -> dict:
        a = api.call("POST", f"/courses/{cid}/assignments", tok, {"kind": kind, "title": title, "points_possible": points})
        return api.call("PATCH", f"/courses/{cid}/assignments/{a['id']}", tok, {"published": True, "due_at": due(days)})

    def quiz(cid: str, bank_id: str, title: dict, days: int, questions: list[dict]) -> tuple[str, dict]:
        ids = [api.call("POST", f"/courses/{cid}/banks/{bank_id}/questions", tok, q)["id"] for q in questions]
        a = api.call("POST", f"/courses/{cid}/assessments", tok, {"title": title, "preset": "none", "languages": ["ru"]})
        base = f"/courses/{cid}/assessments/{a['id']}"
        sec = api.call("POST", f"{base}/sections", tok, {"title": tri("Часть 1", "1-бөлүк", "Part 1")})
        api.call("POST", f"{base}/sections/{sec['id']}/items/bulk", tok, {"question_ids": ids})
        api.call("POST", f"{base}/publish", tok, {})
        listed = api.call("GET", f"/courses/{cid}/assignments?limit=100", tok)["items"]
        row = next(r for r in listed if r.get("assessment_id") == a["id"])
        api.call("PATCH", f"/courses/{cid}/assignments/{row['id']}", tok, {"due_at": due(days)})
        return a["id"], row

    def module(cid: str, title: dict, items: list[dict]) -> None:
        m = api.call("POST", f"/courses/{cid}/modules", tok, {"title": title, "published": True})
        for item in items:
            api.call("POST", f"/courses/{cid}/modules/{m['id']}/items", tok, {**item, "published": True})

    def page(cid: str, title: dict, body: str) -> dict:
        p = api.call("POST", f"/courses/{cid}/pages", tok, {"title": title["ru"], "language": "ru", "body_md": body, "published": True})
        return {"kind": "page", "page_id": p["id"], "title_override": title}

    def assignment(row: dict) -> dict:
        return {"kind": "assignment", "assignment_id": row["id"]}

    maths = new_course(tri("Математика, 11 класс", "Математика, 11-класс", "Mathematics, grade 11"))
    mid = maths["id"]
    bank = api.call("POST", f"/courses/{mid}/banks", tok, {"title": "Математика", "default_language": "ru"})["id"]
    percent = task(mid, "text", tri("Задачи на проценты", "Пайызга маселелер", "Percentage problems"), 3, 10)
    written = task(mid, "file", tri("Контрольная работа", "Текшерүү иши", "Written test"), 9, 20)
    quiz_id, quiz_row = quiz(mid, bank, tri("Тест: дроби", "Тест: бөлчөктөр", "Quiz: fractions"), 1, [
        sc("Сколько будет 1/2 + 1/4?", "3/4", "2/6"), sc("Сколько процентов составляет 1/4?", "25 %", "40 %")])
    _, quiz_two = quiz(mid, bank, tri("Тест: уравнения", "Тест: теңдемелер", "Quiz: equations"), 6, [
        sc("Решите: x + 3 = 7", "4", "10"), sc("Решите: 2x = 10", "5", "8")])
    module(mid, tri("Дроби и проценты", "Бөлчөктөр жана пайыздар", "Fractions and percentages"), [
        page(mid, tri("Обыкновенные дроби", "Жөнөкөй бөлчөктөр", "Common fractions"), "Дробь показывает часть целого."),
        assignment(quiz_row), assignment(percent)])
    module(mid, tri("Уравнения", "Теңдемелер", "Equations"), [
        page(mid, tri("Линейные уравнения", "Сызыктуу теңдемелер", "Linear equations"), "Уравнение вида ax + b = 0."),
        assignment(quiz_two), assignment(written)])
    module(mid, tri("Геометрия", "Геометрия", "Geometry"), [
        page(mid, tri("Площади фигур", "Фигуралардын аянты", "Areas of shapes"), "Площадь прямоугольника равна a · b.")])

    # a classmate's hand-in (teacher: work to check); the student's quiz result (the correct choice "B" of `sc`)
    api.call("POST", f"/courses/{mid}/assignments/{percent['id']}/submissions", classmates[0]["token"], {"body_text": "Ответ: 25 %."})
    st = api.call("POST", f"/courses/{mid}/assessments/{quiz_id}/attempts", student["token"], {"language": "ru"})
    answers = [{"position": it["position"], "response": {"choice_id": "B"}, "client_ts": 1000 + it["position"]} for it in st["items"]]
    api.call("PUT", f"/attempts/{st['id']}/answers", student["token"], {"answers": answers})
    api.call("POST", f"/attempts/{st['id']}/submit", student["token"], {})

    language = new_course(tri("Кыргыз тили, 11 класс", "Кыргыз тили, 11-класс", "Kyrgyz language, grade 11"))
    essay = task(language["id"], "text", tri("Сочинение о родном крае", "Туулган жер жөнүндө дилбаян", "An essay about your home region"), 5, 10)
    module(language["id"], tri("Письменная речь", "Жазуу речи", "Writing"), [assignment(essay)])

    api.call("POST", f"/courses/{ort_course_id}/join", student["token"], {})
    return {"course_id": mid, "teacher": teacher, "student": student}
# --- Landing screens end ---


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
    scrolling = seed_scrolling(api, log, tok)  # Phase 8b S3 (after every ORT, quiz-editor and modules row)
    exam_constructor = seed_constructor(api, log, tok)  # Phase 8b S5 (after every other row)
    course_nav = seed_course_nav(api, log, tok)  # Phase 8c S4a (after every other row)
    catalog_apply = seed_catalog_apply(api, log, tok)  # Phase 9 S4 (after every other row)
    org_admin = seed_org_admin(api, log, tok)  # Phase 9 S5 (after every other row)
    privacy = seed_privacy(api, log, cid, exam["id"])  # Phase 11 S3 (after every other row)
    landing = seed_landing(api, log, tok, cid)  # landing page screenshots (after every other row)
    teacher_signup = seed_teacher_signup(api, log, tok, org_admin["organization_id"], org_admin["org_admin"])  # Accounts

    seed = {
        "quiz_editor": quiz_editor,
        "modules": modules,
        "scrolling": scrolling,
        "exam_constructor": exam_constructor,
        "course_nav": course_nav,
        "catalog_apply": catalog_apply,
        "org_admin": org_admin,
        "privacy": privacy,
        "landing": landing,
        "teacher_signup": teacher_signup,
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
