# Phase 7a walkthrough (S6 integration)

Date 2026-10-26. Scratch backend through `scripts/e2e_backend.sh` (`env -i`, cwd outside `backend/`, fresh SQLite, console email, `LMS_STORAGE_DRIVER=db`, the e2e ORT seed), built frontend (`next build` + `next start` in an rsync'd copy), playwright-core with system Chrome (headless). Data: teacher Айгуль Сыдыкова, course "Биология 10 класс" (weighted: Домашние задания 40 %, Контрольные 60 %; late policy 10 %/day, max 50 %), students Нурлан (ru), Мээрим (ru), Азамат (ky). Scripts: `/tmp/agy_s6w_scripts/` (lib, setup, w1-w10, shots). Each step checks the UI and the API state.

| # | Step | Result | Evidence |
|---|---|---|---|
| | **W1-W2 Teacher builds assignments (browser)** | | |
| 1 | teacher creates text assignment in the dialog | PASS | /ru/courses/81b2b2e1-a834-4334-bea7-da3283ff949f/assignments/d7b7df32-9e54-4355-a6ce-d386629ac98c/edit |
| 2 | teacher creates file assignment in the dialog | PASS | /ru/courses/81b2b2e1-a834-4334-bea7-da3283ff949f/assignments/e795e5d5-1cc5-4e7f-a037-b66692b5da9b/edit |
| 3 | teacher edits and publishes the text assignment | PASS | published=true due=2026-10-27T18:50:00Z until=2026-11-04T18:50:00Z rubric=0 total=0 |
| 4 | teacher edits and publishes the file assignment with a 2-criterion rubric | PASS | published=true due=2026-10-24T18:50:00Z until=2026-11-01T18:50:00Z rubric=2 total=20 |
| | **W3 Students hand in (browser)** | | |
| 5 | student hands in a text answer (on time) | PASS | status=submitted late=false |
| 6 | student hands in a PDF after the due date (late) | PASS | status=submitted late=true file=lab_report_nurlan.pdf |
| 7 | student list shows the statuses | PASS | {"none":"not_started","quiz":"not_started","text":"submitted","file":"submitted"} |
| 8 | ky student hands in a text on a phone | PASS | status=submitted |
| | **W4 Teacher grades and releases (browser)** | | |
| 9 | teacher grades a text hand-in with feedback | PASS | {"raw":"8.00","rel":null} |
| 10 | teacher releases the text assignment's grades | PASS |  |
| 11 | teacher grades the late PDF with the rubric, feedback text and a feedback file | PASS | raw=17.00 late_deduction=3.40 effective=13.60 rubric=2 fb_file=true |
| 12 | teacher grades the oral exam (no hand-in) and releases it | PASS |  |
| | **W5 Student sees grades and feedback (browser)** | | |
| 13 | student sees the released rubric grade (late deduction applied) and the feedback text | PASS |  |
| 14 | student opens the feedback file | PASS | blob:/7c305c33-8b19 |
| 15 | student downloads the own hand-in | PASS | lab_report_nurlan.pdf |
| 16 | student sees the text grade and feedback | PASS |  |
| 17 | my grades: one row per assignment, released grades, submitted/late flags, feedback | PASS | [["none","graded","18.00",null],["quiz","not_started",null,null],["text","graded","8.00",false],["file","graded","13.60",true]] total={"percent":"82.80","display_value":null,"label":null,"passed":null} |
| 18 | second student's released text grade | PASS |  |
| | **W6 Gradebook** | | |
| 19 | gradebook has one column per assignment (4) with categories | PASS | none:Устный экзамен: клетка:T / quiz:Тест: органоиды клетки:T / text:Эссе: строение клетки:HW / file:Лабораторная работа №1 (PDF):HW |
| 20 | gradebook cells keyed by assignment id and weighted total 0.4*72% + 0.6*90% = 82.8% | PASS | text=8.00 file=13.60 oral=18.00 total=82.80 |
| 21 | second student total = text only (9/10 in homework) | PASS | total=90.00 |
| 22 | gradebook page shows the four assignment headers | PASS | Ученик Устный экзамен: клетка из 20 опубликовано 1/1 Тест: органоиды клетки из 3 Эссе: строение клетки из 10 опубликовано 2/2 Лабораторная работа №1 (PDF) из 20 опубликовано 1/1 Итог текущий  |
| | **W7 Accommodations and exceptions (browser)** | | |
| 23 | teacher sets an accommodation (+1 attempt) in the People tab | PASS | {"a":1} |
| 24 | teacher adds a due-date exception for one student (Override dialog) | PASS | Мээрим Жумабаева 2026-10-28T18:55:00Z |
| 25 | student with +1 attempt: /assessments list shows 2 allowed attempts, assignments list 2 left | PASS | assessments.allowed=2 assignments.left=2 |
| 26 | another student keeps 1 attempt and the original due date | PASS | allowed=1 due=2026-10-24T18:50:00Z vs 2026-10-28T18:55:00Z |
| 27 | student /assessments page shows the effective attempts | PASS | Мои курсы Биология 10 класс Биология 10 класс Главная Задания Оценки Преподаватели Задания Тест: органоиды клетки Не начато Срок: 29.10.2026, 00:50 Время: 15 мин Вопросов: 3 Осталось попыток: 2 Начать |
| 28 | student with the exception hands in the PDF after the original due date: on time | PASS | late=false due=2026-10-28T18:55:00Z |
| | **W8 Access code on a general quiz (browser)** | | |
| 29 | teacher sets an access code in the quiz settings | PASS | has_access_code=true |
| 30 | wrong access code is refused with a clear message | PASS | /ru/courses/81b2b2e1-a834-4334-bea7-da3283ff949f/assessments/9aae3fdc-39f0-41a1-bd62-268d5f0f4acd |
| 31 | right access code starts the attempt | PASS | /ru/courses/81b2b2e1-a834-4334-bea7-da3283ff949f/attempts/eafacc91-694c-4f67-844d-5e158e04ccc6 |
| 32 | quiz attempt is graded into the quiz column (3/3) | PASS | {"eff":"3.00","state":"graded","content":3} |
| | **W9 ORT** | | |
| 33 | ORT course: every ORT exam is listed as a quiz assignment (teacher table) | PASS | quiz:ОРТ E2E / quiz:ОРТ E2E staff |
| 34 | ORT student sees the exam card(s) with 'Экзамен ОРТ' and Start | PASS | Мои курсы ОРТ (на русском) ОРТ (на русском) Главная Задания Оценки Преподаватели Задания ОРТ E2E Не начато Экзамен ОРТ Осталось попыток: 1 Начать ОРТ E2E staff Не начато Экзамен ОРТ Осталось попыток:  |
| 35 | Start on the card opens the ORT lobby | PASS | /ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/4ab9f788-bd03-492b-983a-10f8d28b0227 |
| 36 | the ORT player opens | PASS | /ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b1c6daa8-7944-4e59-b35b-bb8a070ded88 |
| 37 | ORT result equals the reference attempt with the same answers (raw score, scaled grade, sections) | PASS | raw=4.00 scaled=96.00 ref raw=4.00 scaled=96.00 |
| 38 | ORT gradebook: the exam is one column (assignment id), the cell carries the scaled grade | PASS | col=ОРТ E2E cell=96.00 label=null |
| | **W10 Resubmission after an unreleased grade** | | |
| 39 | resubmission after an unreleased grade is accepted and needs grading again | PASS | before=graded/6.00 hand_in=201 after=pending_review/null resubmitted=true |
| 40 | teacher roster shows 'Нужно оценить' and 'Сдано повторно' for that student | PASS |  |

**40 steps, 40 PASS, 0 FAIL.**

## ORT

- The ORT exams are listed as quiz assignments in ORT (Russian) (teacher table, student cards "Экзамен ОРТ" with Start -> the unchanged lobby -> player).
- A student's ORT result (raw 4, scaled 96) equals the e2e reference attempt with the same answers; the ORT gradebook shows the exam as one column keyed by its assignment id with the same scaled value.
- `tests/lms/test_ort_gradebook_golden.py` green (SQLite and PG suites).
- `frontend/e2e` (`ort.spec.ts` + `ort-visual.spec.ts`) run twice against a fresh build: 10/10 passed both times, zero pixel diffs. No baseline changed: the access-code field is hidden for ORT presets (S7 security fix), so `teacher-builder-*` is identical.

## Findings fixed during the walkthrough

- Grading screen at 1440 px: the roster's separate "Оценить" column was cut off in the half-width table; the student name is now the row's one action (with the label "Оценить: <name>").
- Lobby with an access code: the code field moved above "Начать тест" (enter the code, then start); exams without a code render as before.
- The student quiz list (`/assessments`) said "Задания" (now the assignments word); it is "Тесты / Тесттер / Quizzes" (glossary note in `docs/UX_GUIDELINES.md` section 5).
- Frontend contract fixes (rubric body, roster `rows`, accommodation and exception rows with `user`, student grade shape, file ids) - without them the rubric save, the grading roster, the accommodations table and the feedback download failed.

## Not covered in the browser

- R2 presigned downloads (`LMS_STORAGE_DRIVER=r2`): hand-in files are served by a 302 to a presigned URL there; the frontend fetches the route with the bearer token and follows the redirect, which needs CORS on the private bucket for the site origin. Only the `db` driver was exercised here (owner/orchestrator to verify on the rehearsal).
