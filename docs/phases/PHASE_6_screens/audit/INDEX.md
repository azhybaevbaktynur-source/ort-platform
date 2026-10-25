# UX audit screenshots: current app (branch `lms`, 2026-10-24)

204 JPEG files (quality 70, full page unless noted), 15.9 MB. Viewports: desktop 1440x900, phone 375x812, deviceScaleFactor 1. Name: `<area>-<nn>-<screen>-<viewport>-<lang>.jpg`.

Setup: scratch SQLite backend (port 8002, `ORT_SEED_SAMPLES=true`, `LMS_STORAGE_DRIVER=db`) and a production build of the frontend (port 3006) from an rsync'd copy. Demo data created through the API: admin Бакыт Осмонов (platform admin, ORT co-teacher), teacher Айгуль Садыкова (approved via the admin API), students Нурлан Абдыкадыров (main), Мээрим Жумабаева, Данияр Асанов, Елена Петрова; Тимур Иманалиев has a pending teacher request. Teacher course "Биология 9 класс" (ru+ky): bank "Клетка и ткани" with 6 questions (single_choice, multiple_answers, true_false, numeric, short_text, essay) and 1 passage; published "Контрольная: клетка" (20 min, free navigation, own 5-point band scheme), draft "Домашнее задание: ткани"; empty draft course "Химия 10 класс". ORT (Russian): the seeded `ort_main` sample exam (25 questions, 5 timed sections), taken and submitted by Нурлан.

URL paths use `<C>` = Biology course, `<ORU>` = ORT (Russian) course; real ids are in the paths below.

## Files

| File | URL path | Role | What is shown |
|---|---|---|---|
| admin-01-overview-desktop-ru.jpg | `/ru/admin` | platform admin | Platform admin overview |
| admin-01-overview-phone-ru.jpg | `/ru/admin` | platform admin | Platform admin overview |
| admin-02-teacher-requests-desktop-ru.jpg | `/ru/admin/teacher-requests` | platform admin | Teacher requests (one pending: Тимур Иманалиев) |
| admin-02-teacher-requests-phone-ru.jpg | `/ru/admin/teacher-requests` | platform admin | Teacher requests (one pending: Тимур Иманалиев) |
| admin-03-users-desktop-ru.jpg | `/ru/admin/users` | platform admin | Users list |
| admin-03-users-phone-ru.jpg | `/ru/admin/users` | platform admin | Users list |
| admin-04-user-detail-student-desktop-ru.jpg | `/ru/admin/users/usr_e78494ba4219` | platform admin | User detail: student |
| admin-04-user-detail-student-phone-ru.jpg | `/ru/admin/users/usr_e78494ba4219` | platform admin | User detail: student |
| admin-05-user-detail-teacher-desktop-ru.jpg | `/ru/admin/users/usr_07dc65a86a1f` | platform admin | User detail: approved teacher |
| admin-05-user-detail-teacher-phone-ru.jpg | `/ru/admin/users/usr_07dc65a86a1f` | platform admin | User detail: approved teacher |
| admin-06-courses-desktop-ru.jpg | `/ru/admin/courses` | platform admin | All courses |
| admin-06-courses-phone-ru.jpg | `/ru/admin/courses` | platform admin | All courses |
| admin-07-course-detail-desktop-ru.jpg | `/ru/admin/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | platform admin | Course detail (Biology 9) |
| admin-07-course-detail-phone-ru.jpg | `/ru/admin/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | platform admin | Course detail (Biology 9) |
| admin-08-course-detail-ort-desktop-ru.jpg | `/ru/admin/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f` | platform admin | Course detail (ORT Russian, platform-owned) |
| admin-08-course-detail-ort-phone-ru.jpg | `/ru/admin/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f` | platform admin | Course detail (ORT Russian, platform-owned) |
| admin-09-audit-log-desktop-ru.jpg | `/ru/admin/audit-log` | platform admin | Audit log |
| admin-09-audit-log-phone-ru.jpg | `/ru/admin/audit-log` | platform admin | Audit log |
| admin-10-storage-desktop-ru.jpg | `/ru/admin/storage` | platform admin | Storage (db driver in this scratch run) |
| admin-10-storage-phone-ru.jpg | `/ru/admin/storage` | platform admin | Storage (db driver in this scratch run) |
| admin-11-my-courses-desktop-ru.jpg | `/ru/courses` | platform admin | Admin's my courses (co-teacher of both ORT courses) |
| admin-11-my-courses-phone-ru.jpg | `/ru/courses` | platform admin | Admin's my courses (co-teacher of both ORT courses) |
| public-01-landing-desktop-ru.jpg | `/ru` | anonymous | Landing page |
| public-01-landing-phone-ru.jpg | `/ru` | anonymous | Landing page |
| public-02-login-desktop-ru.jpg | `/ru/login` | anonymous | Login form |
| public-02-login-phone-ru.jpg | `/ru/login` | anonymous | Login form |
| public-03-register-desktop-ru.jpg | `/ru/register` | anonymous | Registration form |
| public-03-register-phone-ru.jpg | `/ru/register` | anonymous | Registration form |
| public-04-forgot-password-desktop-ru.jpg | `/ru/forgot-password` | anonymous | Forgot password form |
| public-04-forgot-password-phone-ru.jpg | `/ru/forgot-password` | anonymous | Forgot password form |
| student-01-my-courses-catalog-desktop-en.jpg | `/en/courses` | student | My courses with the catalog section (before joining ORT) |
| student-01-my-courses-catalog-desktop-ky.jpg | `/ky/courses` | student | My courses with the catalog section (before joining ORT) |
| student-01-my-courses-catalog-desktop-ru.jpg | `/ru/courses` | student | My courses with the catalog section (before joining ORT) |
| student-01-my-courses-catalog-phone-en.jpg | `/en/courses` | student | My courses with the catalog section (before joining ORT) |
| student-01-my-courses-catalog-phone-ky.jpg | `/ky/courses` | student | My courses with the catalog section (before joining ORT) |
| student-01-my-courses-catalog-phone-ru.jpg | `/ru/courses` | student | My courses with the catalog section (before joining ORT) |
| student-02-join-desktop-ru.jpg | `/ru/courses/join` | student | Join a course by code |
| student-02-join-phone-ru.jpg | `/ru/courses/join` | student | Join a course by code |
| student-03-join-bad-code-desktop-ru.jpg | `/ru/courses/join` | student | Error state: wrong join code |
| student-03-join-bad-code-phone-ru.jpg | `/ru/courses/join` | student | Error state: wrong join code |
| student-04-course-not-found-desktop-ru.jpg | `/ru/courses/00000000-0000-0000-0000-000000000000` | student | Error state: course not found |
| student-04-course-not-found-phone-ru.jpg | `/ru/courses/00000000-0000-0000-0000-000000000000` | student | Error state: course not found |
| student-05-course-home-desktop-en.jpg | `/en/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | student | Course home (Biology 9) |
| student-05-course-home-desktop-ky.jpg | `/ky/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | student | Course home (Biology 9) |
| student-05-course-home-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | student | Course home (Biology 9) |
| student-05-course-home-phone-en.jpg | `/en/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | student | Course home (Biology 9) |
| student-05-course-home-phone-ky.jpg | `/ky/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | student | Course home (Biology 9) |
| student-05-course-home-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | student | Course home (Biology 9) |
| student-06-assessments-list-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments` | student | Course assessments list |
| student-06-assessments-list-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments` | student | Course assessments list |
| student-07-lobby-general-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0` | student | Lobby of the general assessment (time limit, free navigation) |
| student-07-lobby-general-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0` | student | Lobby of the general assessment (time limit, free navigation) |
| student-08-grades-before-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/grades` | student | My grades before any attempt (empty state) |
| student-08-grades-before-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/grades` | student | My grades before any attempt (empty state) |
| student-09-become-teacher-desktop-ru.jpg | `/ru/courses/become-teacher` | student | Become-a-teacher request form |
| student-09-become-teacher-phone-ru.jpg | `/ru/courses/become-teacher` | student | Become-a-teacher request form |
| student-10-people-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/people` | student | People tab as a student |
| student-10-people-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/people` | student | People tab as a student |
| student-11-catalog-joined-desktop-ru.jpg | `/ru/courses` | student | Catalog after joining ORT (Russian): card shows Open |
| student-11-catalog-joined-phone-ru.jpg | `/ru/courses` | student | Catalog after joining ORT (Russian) |
| student-12-course-home-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f` | student | ORT (Russian) course home |
| student-12-course-home-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f` | student | ORT (Russian) course home |
| student-13-assessments-list-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments` | student | ORT course assessments list |
| student-13-assessments-list-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments` | student | ORT course assessments list |
| student-14-lobby-ort-desktop-en.jpg | `/en/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT exam lobby (5 timed sections, forward-only) |
| student-14-lobby-ort-desktop-ky.jpg | `/ky/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT exam lobby (5 timed sections, forward-only) |
| student-14-lobby-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT exam lobby (5 timed sections, forward-only) |
| student-14-lobby-ort-phone-en.jpg | `/en/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT exam lobby (5 timed sections, forward-only) |
| student-14-lobby-ort-phone-ky.jpg | `/ky/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT exam lobby (5 timed sections, forward-only) |
| student-14-lobby-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT exam lobby (5 timed sections, forward-only) |
| student-15-player-comparison-desktop-en.jpg | `/en/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player, math_1 quantitative comparison question (Column A / B) |
| student-15-player-comparison-desktop-ky.jpg | `/ky/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player, math_1 quantitative comparison question (Column A / B) |
| student-15-player-comparison-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player, math_1 quantitative comparison question (Column A / B) |
| student-15-player-comparison-phone-en.jpg | `/en/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player, math_1 quantitative comparison question (Column A / B) |
| student-15-player-comparison-phone-ky.jpg | `/ky/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player, math_1 quantitative comparison question (Column A / B) |
| student-15-player-comparison-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player, math_1 quantitative comparison question (Column A / B) |
| student-16-player-flagged-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player: answered + flagged question, palette shows states |
| student-16-player-flagged-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player on phone: flagged question 3 |
| student-17-player-palette-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player on phone: question palette (viewport scrolled to it; palette sits below the question, no drawer) |
| student-18-section-end-dialog-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | Finish-section confirmation (forward-only, counts unanswered/flagged) |
| student-18-section-end-dialog-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | Finish-section confirmation on phone |
| student-19-player-math2-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player: math_2 section (plain multiple choice) |
| student-20-player-analogies-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player: analogies section |
| student-21-player-passage-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player: reading question with its passage |
| student-21-player-passage-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player on phone: reading question with passage |
| student-22-player-grammar-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | ORT player: grammar (last) section |
| student-23-submit-dialog-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | Finish test confirmation dialog |
| student-23-submit-dialog-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d` | student | Finish test confirmation dialog on phone |
| student-24-result-ort-desktop-en.jpg | `/en/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: scaled score, sections, review below |
| student-24-result-ort-desktop-ky.jpg | `/ky/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: scaled score, sections, review below |
| student-24-result-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: scaled score, sections, review below |
| student-24-result-ort-phone-en.jpg | `/en/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: scaled score, sections, review below |
| student-24-result-ort-phone-ky.jpg | `/ky/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: scaled score, sections, review below |
| student-24-result-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: scaled score, sections, review below |
| student-25-review-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: item review (viewport scrolled to the review list) |
| student-25-review-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b2b3b140-9708-4bfd-894d-878057f4a10d/result` | student | ORT result: item review (viewport scrolled to the review list) |
| student-26-attempts-list-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT lobby after submission: my attempts list |
| student-26-attempts-list-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd` | student | ORT lobby after submission: my attempts list |
| student-27-player-essay-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player: essay question (answered) |
| student-27-player-essay-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player on phone: essay |
| student-27-player-multiple-answers-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player: multiple answers question (answered) |
| student-27-player-multiple-answers-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player on phone: multiple answers with passage |
| student-27-player-numeric-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player: numeric question (answered) |
| student-27-player-short-text-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player: short text question (answered) |
| student-27-player-single-choice-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player: single choice question (answered) |
| student-27-player-single-choice-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player on phone: single choice |
| student-27-player-true-false-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | General assessment player: true false question (answered) |
| student-28-submit-dialog-general-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/2a226a3c-5ab0-4399-8839-79fd40eb2747` | student | Finish test dialog (free navigation) |
| student-29-result-general-desktop-en.jpg | `/en/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General assessment result (essay pending review), review below |
| student-29-result-general-desktop-ky.jpg | `/ky/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General assessment result (essay pending review), review below |
| student-29-result-general-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General assessment result (essay pending review), review below |
| student-29-result-general-phone-en.jpg | `/en/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General assessment result (essay pending review), review below |
| student-29-result-general-phone-ky.jpg | `/ky/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General assessment result (essay pending review), review below |
| student-29-result-general-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General assessment result (essay pending review), review below |
| student-30-review-general-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General result: item review (viewport scrolled to review) |
| student-30-review-general-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7/result` | student | General result: item review (viewport scrolled to review) |
| student-31-attempts-list-general-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0` | student | General lobby after submission: my attempts, no attempts left |
| student-31-attempts-list-general-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0` | student | General lobby after submission: my attempts, no attempts left |
| student-32-grades-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/grades` | student | My grades in Biology (one graded/pending item) |
| student-32-grades-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/grades` | student | My grades in Biology (one graded/pending item) |
| student-33-grades-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/grades` | student | My grades in ORT (Russian) |
| student-33-grades-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/grades` | student | My grades in ORT (Russian) |
| student-34-my-courses-after-desktop-ru.jpg | `/ru/courses` | student | My courses after joining ORT (two courses) |
| student-34-my-courses-after-phone-ru.jpg | `/ru/courses` | student | My courses after joining ORT (two courses) |
| student-35-empty-my-courses-pending-teacher-desktop-ru.jpg | `/ru/courses` | user with pending teacher request | Empty state: no courses yet (pending teacher request) |
| student-35-empty-my-courses-pending-teacher-phone-ru.jpg | `/ru/courses` | user with pending teacher request | Empty state: no courses yet (pending teacher request) |
| student-36-become-teacher-pending-desktop-ru.jpg | `/ru/courses/become-teacher` | user with pending teacher request | Become-teacher page with a pending request |
| student-36-become-teacher-pending-phone-ru.jpg | `/ru/courses/become-teacher` | user with pending teacher request | Become-teacher page with a pending request |
| student-37-admin-forbidden-desktop-ru.jpg | `/ru/admin` | student | Error state: student opens /admin |
| student-37-admin-forbidden-phone-ru.jpg | `/ru/admin` | student | Error state: student opens /admin |
| student-38-grading-schemes-forbidden-desktop-ru.jpg | `/ru/grading-schemes` | student | Student opens /grading-schemes |
| student-38-grading-schemes-forbidden-phone-ru.jpg | `/ru/grading-schemes` | student | Student opens /grading-schemes |
| student-90-error-player-crash-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7` | student | BUG: player of a general assessment crashes (React #31, section title object {ru,ky} rendered as text) |
| student-90-error-player-crash-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/attempts/e92fb81f-95eb-462f-985d-908627cd3bf7` | student | BUG: player of a general assessment crashes (React #31, section title object {ru,ky} rendered as text) |
| teacher-01-my-courses-desktop-ru.jpg | `/ru/courses` | teacher | Teacher: my courses (teaching tab) with catalog |
| teacher-01-my-courses-phone-ru.jpg | `/ru/courses` | teacher | Teacher: my courses (teaching tab) with catalog |
| teacher-02-create-course-desktop-ru.jpg | `/ru/courses/new` | teacher | Create course form |
| teacher-02-create-course-phone-ru.jpg | `/ru/courses/new` | teacher | Create course form |
| teacher-03-course-home-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | teacher | Course home as owner (join code, status) |
| teacher-03-course-home-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be` | teacher | Course home as owner (join code, status) |
| teacher-04-people-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/people` | teacher | People / roster with 4 students |
| teacher-04-people-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/people` | teacher | People / roster with 4 students |
| teacher-05-settings-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/settings` | teacher | Course settings |
| teacher-05-settings-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/settings` | teacher | Course settings |
| teacher-06-bank-list-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank` | teacher | Question banks list |
| teacher-06-bank-list-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank` | teacher | Question banks list |
| teacher-07-bank-questions-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/1f4b140c-9f0d-4328-b482-40663f3e9ab1` | teacher | Bank questions (6 types) |
| teacher-07-bank-questions-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/1f4b140c-9f0d-4328-b482-40663f3e9ab1` | teacher | Bank questions (6 types) |
| teacher-08-question-editor-single-choice-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/q/15d007f9-afd7-4ee8-85ac-deef644795ee` | teacher | Question editor: single choice |
| teacher-08-question-editor-single-choice-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/q/15d007f9-afd7-4ee8-85ac-deef644795ee` | teacher | Question editor: single choice |
| teacher-09-question-editor-numeric-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/q/5788cb31-59f9-4cfd-ada1-5b9d7fbcad61` | teacher | Question editor: numeric |
| teacher-09-question-editor-numeric-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/q/5788cb31-59f9-4cfd-ada1-5b9d7fbcad61` | teacher | Question editor: numeric |
| teacher-10-question-editor-comparison-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/bank/q/773fe5a9-cab4-42b1-9963-78b88bb2ada9` | teacher (platform admin as ORT co-teacher) | Question editor: math_1 comparison (ORT bank) |
| teacher-10-question-editor-comparison-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/bank/q/773fe5a9-cab4-42b1-9963-78b88bb2ada9` | teacher (platform admin as ORT co-teacher) | Question editor: math_1 comparison (ORT bank) |
| teacher-11-question-new-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/1f4b140c-9f0d-4328-b482-40663f3e9ab1/new` | teacher | New question form |
| teacher-11-question-new-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/1f4b140c-9f0d-4328-b482-40663f3e9ab1/new` | teacher | New question form |
| teacher-12-passages-list-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/1f4b140c-9f0d-4328-b482-40663f3e9ab1/passages` | teacher | Bank passages list |
| teacher-12-passages-list-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/1f4b140c-9f0d-4328-b482-40663f3e9ab1/passages` | teacher | Bank passages list |
| teacher-13-passage-editor-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/p/9877c542-5c52-47da-9252-c9269fc6a692` | teacher | Passage editor |
| teacher-13-passage-editor-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/p/9877c542-5c52-47da-9252-c9269fc6a692` | teacher | Passage editor |
| teacher-14-passage-editor-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/bank/p/4c8288ca-e6fd-48d4-8b6d-b847b2d402fe` | teacher (platform admin as ORT co-teacher) | Passage editor (ORT reading passage) |
| teacher-14-passage-editor-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/bank/p/4c8288ca-e6fd-48d4-8b6d-b847b2d402fe` | teacher (platform admin as ORT co-teacher) | Passage editor (ORT reading passage) |
| teacher-15-import-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/import` | teacher | Import page (CSV / bundle zip) |
| teacher-15-import-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/bank/import` | teacher | Import page (CSV / bundle zip) |
| teacher-16-assessments-list-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments` | teacher | Staff assessments list (published + draft) |
| teacher-16-assessments-list-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments` | teacher | Staff assessments list (published + draft) |
| teacher-17-create-assessment-dialog-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments` | teacher | Create assessment dialog (preset, languages) |
| teacher-17-create-assessment-dialog-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments` | teacher | Create assessment dialog (preset, languages) |
| teacher-18-assessment-detail-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0` | teacher | Staff assessment page with publish panel (published) |
| teacher-18-assessment-detail-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0` | teacher | Staff assessment page with publish panel (published) |
| teacher-19-builder-general-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0/edit` | teacher | Assessment builder: general assessment (settings, section, items) |
| teacher-19-builder-general-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0/edit` | teacher | Assessment builder: general assessment (settings, section, items) |
| teacher-20-builder-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd/edit` | teacher (platform admin as ORT co-teacher) | Assessment builder: ORT preset (5 sections) |
| teacher-20-builder-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd/edit` | teacher (platform admin as ORT co-teacher) | Assessment builder: ORT preset (5 sections) |
| teacher-21-builder-draft-empty-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/c9202793-0c61-4ba6-90ef-090f785dfcb0/edit` | teacher | Builder of an empty draft assessment (empty state) |
| teacher-21-builder-draft-empty-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/c9202793-0c61-4ba6-90ef-090f785dfcb0/edit` | teacher | Builder of an empty draft assessment (empty state) |
| teacher-22-publish-panel-validate-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/c9202793-0c61-4ba6-90ef-090f785dfcb0` | teacher | Publish panel of the empty draft after Validate (errors list) |
| teacher-22-publish-panel-validate-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/c9202793-0c61-4ba6-90ef-090f785dfcb0` | teacher | Publish panel of the empty draft after Validate (errors list) |
| teacher-23-staff-attempts-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0/attempts` | teacher | Staff attempts list for the Biology test |
| teacher-23-staff-attempts-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0/attempts` | teacher | Staff attempts list for the Biology test |
| teacher-24-staff-attempt-grading-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0/attempts/8ef91291-ee34-4dff-9dc1-795a84ce6e49` | teacher | Staff attempt detail: manual grading of the essay |
| teacher-24-staff-attempt-grading-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/assessments/f70fa864-85ba-40f0-b64f-dd248c7b0fa0/attempts/8ef91291-ee34-4dff-9dc1-795a84ce6e49` | teacher | Staff attempt detail: manual grading of the essay |
| teacher-25-staff-attempts-ort-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd/attempts` | teacher (platform admin as ORT co-teacher) | Staff attempts list for the ORT exam |
| teacher-25-staff-attempts-ort-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/3425f383-f6fa-4b3a-923f-065d151d53dd/attempts` | teacher (platform admin as ORT co-teacher) | Staff attempts list for the ORT exam |
| teacher-26-gradebook-desktop-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/grades` | teacher | Gradebook |
| teacher-26-gradebook-phone-ru.jpg | `/ru/courses/d3ba4bfc-bfd5-4df2-a579-5f5cf18b52be/grades` | teacher | Gradebook |
| teacher-27-grading-schemes-desktop-ru.jpg | `/ru/grading-schemes` | teacher | Grading schemes list (system + own) |
| teacher-27-grading-schemes-phone-ru.jpg | `/ru/grading-schemes` | teacher | Grading schemes list (system + own) |
| teacher-28-grading-scheme-own-desktop-ru.jpg | `/ru/grading-schemes/3d5b45e0-dc2f-4aa7-86b8-3842989b18a0` | teacher | Own scheme: five-point bands |
| teacher-28-grading-scheme-own-phone-ru.jpg | `/ru/grading-schemes/3d5b45e0-dc2f-4aa7-86b8-3842989b18a0` | teacher | Own scheme: five-point bands |
| teacher-29-grading-scheme-ort-desktop-ru.jpg | `/ru/grading-schemes/00000000-0000-4000-8000-000000000401` | teacher | System scheme: ORT main 60-245 curve |
| teacher-29-grading-scheme-ort-phone-ru.jpg | `/ru/grading-schemes/00000000-0000-4000-8000-000000000401` | teacher | System scheme: ORT main 60-245 curve |
| teacher-30-grading-scheme-new-desktop-ru.jpg | `/ru/grading-schemes/new` | teacher | New grading scheme form |
| teacher-30-grading-scheme-new-phone-ru.jpg | `/ru/grading-schemes/new` | teacher | New grading scheme form |
| teacher-31-empty-course-home-desktop-ru.jpg | `/ru/courses/f49433aa-7933-4acc-ac88-75a0d3ec0cc0` | teacher | Empty state: new draft course (Chemistry) home |
| teacher-31-empty-course-home-phone-ru.jpg | `/ru/courses/f49433aa-7933-4acc-ac88-75a0d3ec0cc0` | teacher | Empty state: new draft course (Chemistry) home |
| teacher-32-empty-course-assessments-desktop-ru.jpg | `/ru/courses/f49433aa-7933-4acc-ac88-75a0d3ec0cc0/assessments` | teacher | Empty state: course with no assessments |
| teacher-32-empty-course-assessments-phone-ru.jpg | `/ru/courses/f49433aa-7933-4acc-ac88-75a0d3ec0cc0/assessments` | teacher | Empty state: course with no assessments |
| teacher-33-empty-course-bank-desktop-ru.jpg | `/ru/courses/f49433aa-7933-4acc-ac88-75a0d3ec0cc0/bank` | teacher | Empty state: course with no question banks |
| teacher-33-empty-course-bank-phone-ru.jpg | `/ru/courses/f49433aa-7933-4acc-ac88-75a0d3ec0cc0/bank` | teacher | Empty state: course with no question banks |
| teacher-34-trash-desktop-ru.jpg | `/ru/courses/trash` | teacher | Course trash |
| teacher-34-trash-phone-ru.jpg | `/ru/courses/trash` | teacher | Course trash |
| teacher-35-ort-course-home-desktop-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f` | teacher (platform admin as ORT co-teacher) | ORT (Russian) course home as co-teacher |
| teacher-35-ort-course-home-phone-ru.jpg | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f` | teacher (platform admin as ORT co-teacher) | ORT (Russian) course home as co-teacher |

## Not captured, and why

- Phone versions of some stateful player steps (math_2, analogies, grammar sections; true/false, numeric and short-text questions; finish dialog of the general test): the flow ran once on desktop; phone shots were taken only where the server state allowed a reload (comparison, flagged, palette, section dialog, passage, ORT submit dialog, single/multiple/essay).
- "Palette open on phone": the phone layout has no palette drawer; the palette is stacked below the question. `student-17-player-palette-phone-ru.jpg` is a viewport shot scrolled to it.
- The general-assessment player for the main student: it crashed (bug 1 below), so his attempt was submitted through the API and the player shots (`student-27-*`) were taken with Елена Петрова after the section title was removed and the test republished.
- Preview as student ("Посмотреть как ученик"), time-up and closed-section dialogs, disabled-user and rejected-request states, and the reset-password page were not captured.
- Review shots (`*-review-*`) are viewport shots scrolled to the review list; the full review is in the matching `*-result-*` full-page shots.

## App bugs and oddities noticed

1. **Player crash (blocker)**: any assessment whose section has a teacher-set title crashes the player with React error #31 (object with keys {ru, ky}) and shows the bare Next.js "Application error" page. `GET /attempts/{id}/content` returns `sections[].title` as a localized dict and `PlayerShell.sectionTitle()` renders it as a string. URL: `/ru/courses/<C>/attempts/<attempt>` (`student-90-error-player-crash-*`). ORT exams are unaffected (their sections have `title: null`). There is also no error boundary around the player.
2. **Timestamps shown in UTC as local time**: the API returns naive ISO datetimes (e.g. `submitted_at: "2026-10-23T17:03:34.545130"`, no `Z`), so the browser (KST, UTC+9) shows 17:03 instead of 02:03 (result page "Сдано", admin user detail "Создан", staff attempt header). Seen on SQLite; check whether PostgreSQL serializes with an offset.
3. ORT result: sections with raw 0 show a scaled score of 0 (scale 60-245) and the total is 87 with percentile 1.8 (`student-24-result-ort-*`). This may be the intended `zero_raw` rule, but it reads oddly next to "Шкала 60–245".
4. The image upload hint in the question editor says "до 5 МБ" while AGENTS.md documents a 2 MiB image limit (may be raw-upload vs stored-WebP; worth checking) (`teacher-08/10-question-editor-*`).
5. The staff attempt detail labels the student's answer "Ваш ответ" (`teacher-24-staff-attempt-grading-*`).
6. The create-assessment modal overlay leaves a white strip at the top of the page (`teacher-17-create-assessment-dialog-desktop-ru.jpg`).
7. Plain-text math in ORT sample explanations (`2^5 = 32`) is not rendered as math (seed content, not UI).
8. The student "My courses" page shows a "Преподаю" (teaching) tab to a pure student (`student-01-*`).

