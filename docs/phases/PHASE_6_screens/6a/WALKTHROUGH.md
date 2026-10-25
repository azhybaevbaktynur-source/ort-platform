# Phase 6a: ORT walkthrough and browser check (2026-10-25)

Real browser (Chrome headless via playwright-core), production build of `phase-6a` (commit `5def2b2`) on port 3015, scratch SQLite backend on port 8015 (`env -i`, `ORT_SEED_SAMPLES=false` so the ORT bank started empty, `LMS_STORAGE_DRIVER=db`, console email). Everything below was done in the UI unless marked (API). Screenshots: `INDEX.md`.

## 1. ORT walkthrough (PHASE_6_DESIGN §6 step 2)

Course ORT (Russian) `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f`, teacher side as the platform admin (ORT owner), student side as Нурлан Абдыкадыров.

| # | Step | Result | Evidence |
|---|---|---|---|
| 1 | Import page opens with format select; default format `full_main` (CSV) | PASS | `#imp-format = full_main`; `ort-teacher-01-import-page-*` |
| 2 | Upload `sample_ort_questions_ru.csv`, check, import | PASS | preview "Импортировать 25 вопросов", then "Импорт завершён", new bank `sample_ort_questions_ru` (25 new); `ort-teacher-02a/02b` |
| 3 | Upload `backend/tests/fixtures/bundles/tsoomo19.zip` (default format again `full_main`), check, import | PASS | preview "Импортировать 150 вопросов", done: bank `tsoomo19`, 30 per section, images stored; `ort-teacher-03a/03b` |
| 4 | Create exam with preset "ОРТ, основной тест" | PASS | redirect to `/assessments/{exam}/edit`; five sections created; `ort-teacher-05`, `ort-teacher-06` |
| 5 | Sections in order math_1, math_2, analogies, reading, grammar | PASS | Математика I (Сравнение) > Математика II > Аналогии и дополнения > Чтение и понимание > Практическая грамматика (45/45/30/60/35 min) |
| 6 | Add items (Add questions dialog, bank tsoomo19, section filter) | PASS | 3 math_1 + 2 math_2 + 2 analogies + 1 reading passage group with 2 questions + 2 grammar = 11 items (API check). The script's first count for reading said FAIL; false negative: the two reading questions were added as one passage group, which counts as one item. `ort-teacher-07`, `ort-teacher-08` |
| 7 | Locked controls greyed with "Задано шаблоном ОРТ" (= en "Fixed by the ORT template") | PASS | disabled: "Добавить раздел", all section up/down, all 5 section "Удалить", settings selects "Навигация" and "Схема оценивания"; the note is shown 3 times (sections, navigation, grading scheme); `ort-teacher-06`, `ort-teacher-09-*` |
| 8 | Validate and publish | PASS | "Проблем не найдено", status "Опубликовано, Версия 1"; `ort-teacher-10`, `ort-teacher-12` |
| 9 | Question editing still works in the locked course | PASS | comparison question `/bank/q/{q}`: explanation edited and saved, API `version_no` 1 -> 2; `ort-teacher-14`, `ort-teacher-15` |
| 10 | Create-assessment dialog in the ORT course shows the ORT presets | PASS | "ОРТ, основной тест" and "ОРТ, предметный тест" present |
| 11 | Student joins ORT (Russian) from the catalog ("Записаться") | PASS | card turns to "Открыть"; course listed under "Учусь"; `student-01-my-courses-*` |
| 12 | Lobby, start the exam | PASS | "Начать" -> `/attempts/{attempt}`; `student-14-lobby-ort-*` |
| 13 | Comparison item: Column A / B, timer, palette | PASS | "Колонка А/Б" shown, `[role=timer]` present, palette 3 buttons; `student-15-player-comparison-*` |
| 14 | Answer comparison items, flag one | PASS | palette labels "Вопрос 1, Есть ответ / Вопрос 2, Есть ответ / Вопрос 3, Есть ответ, Помечен"; button becomes "Снять пометку"; `student-16-player-flagged-*`, `student-17-player-palette-phone-*` |
| 15 | Finish section 1 via the section-end dialog | PASS | dialog with "Закрыть раздел" / "Остаться в разделе"; after confirm the player is in Математика II; `student-18-section-end-dialog-*` |
| 16 | Reading passage with line numbers | PASS | 31 numbered lines (5, 10, 15, ...) beside the passage; `student-21-player-passage-*` |
| 17 | Submit via the submit dialog | PASS | "Завершить и отправить" -> `/attempts/{attempt}/result`; `student-23-submit-dialog-*` |
| 18 | Result page: scaled score, five section rows | PASS | score 3/11, scaled 108 (scale 60-245), percentile, Зачётная попытка; five section rows with raw and scaled score; item review below; `student-24-result-ort-*`, `student-25-review-ort-*` |

Walkthrough: 18/18 steps pass. One layout regression affects the ORT student screens on phones (F1 below). The exam itself behaves the same.

## 2. Other 6a flows checked

| Flow | Result | Notes |
|---|---|---|
| Platform admin creates orgs (API), invites the org admin (`role=org_admin`, API), org admin accepts (API) | PASS | |
| Org admin "Пригласить преподавателя" dialog -> invitation email (console) with `/ru/invite/{token}` | PASS | From `"Гульнара Токтогулова via Платформа"`, Reply-To the inviter |
| Invite page logged out (en/ky/ru): org, role, masked email, expiry, Log in / Create account | PASS | `invite-01-*` |
| New-account path: Create account -> register (redirect back) -> email code -> auto accept -> `/ru/courses` | PASS | membership `teacher` in Школа №1 confirmed by API. Email NOT prefilled (F2). `invite-05..07` |
| Existing-account path: logged in as the invited email -> auto accept -> `/ru/courses` | PASS | the "accepting" state only flashes, so it was captured by delaying the accept call 2.5 s; `invite-02-*`, `invite-08` |
| Mismatch: student opens another email's invitation | PASS | yellow box names both emails + "Log out and use another account"; accept API 403 `invitation_email_mismatch`; `invite-03-*` |
| Unknown/expired/revoked token | PASS | one 404 shape, "ask your administrator"; `invite-04-*` |
| Org admin creates a course (title, owner UserPicker finds org teacher "Эрлан") | PASS | template select offers only "Обычный курс (без шаблона)" (org has no ORT grant); `orgadmin-06*` |
| Org admin: remove dialog names the teacher and effect | PASS | `orgadmin-04-*` |
| Org admin: join as teacher (dialog names the effect, confirm) | PASS | roster shows Гульнара with badge "Вошёл как администратор организации"; `orgadmin-08*` |
| Platform admin org detail: all 7 tabs open | PASS | `admin-02-org-detail-*` |
| Suspend dialog (reason, effect named), suspend «Центр «Билим»» | PASS | badge "Приостановлена"; org area shows the banner; `admin-03*`, `orgadmin-09-*` |
| Admin user detail "Организации и роли" | PASS | lists Школа №1 / teacher; `admin-04-*` |
| Admin course transfer UserPicker + confirm dialog naming course and both owners | PASS by email, FAIL by Cyrillic name | F6 (SQLite only); `admin-05*` |
| Independent teacher request approved (API) -> personal org | PASS | `/me/organizations` = org "Тимур Иманалиев", role org_admin |
| Pending invitation banner (Мээрим) -> "Посмотреть приглашения" -> `/ru/teacher-access` with "Принять" | PASS | script's text check said FAIL (it searched for the org name in the banner, which only says "Приглашения для вас: 1"); screenshot confirms; `student-04*` |
| `/teacher-access` (ask your administrator / apply) en/ky/ru | PASS | `student-02-*` |
| Grading schemes as a student: no-permission state | PASS | "Только для преподавателей"; `student-03-*` |
| General course: create-assessment dialog without ORT presets | PASS (with a text leak) | no preset choice; F5; `teacher-02-*` |
| General course: import panel without format select | PASS | `#imp-format` absent, no "ОРТ" text; `teacher-03-*` |
| General course: plain passage (bank page and student player) | PASS | 0 numbered lines; `teacher-04-*`, `student-06-*` |

## 3. Broken flows, regressions and errors

**F1 (major, 6a regression, phones): the student header is wider than the screen in ru and ky.** In ru/ky the header's right group (name + new "Я преподаватель" / "Мен мугалиммин" link + "Выйти") does not wrap. At 375 px `document.scrollWidth` = 450 (ru) / 432 (ky). The overflowing element is `DIV.flex items-center gap-1` (right=450, width=434, text "Нурлан Абдыкадыров Я преподаватель Выйти"), measured on `/ru/courses/{ORU}/attempts/{attempt}` in a 375x812 context. Mobile Chrome then lays out the whole page 432-458 px wide (zoomed out, sideways scroll). This hits every student page: `/courses`, `/teacher-access`, `/grading-schemes`, the ORT lobby, player, dialogs and result. Phone shots are 432-458 px wide (list in INDEX, all `student-*-phone-ky|ru`); en is 376 px. The pre-6a audit images of the same ORT screens (`../audit/student-15..23-*-phone-ru.jpg`) are 375 px, and the ORT visual baselines would flag this. Staff headers have no "Я преподаватель" link, so they wrap correctly. Fix: let the account group wrap or move the link into the account menu (6b `AppHeader`).

**F2 (minor, design gap): register from an invitation is not prefilled.** The email link is `/{lang}/invite/{token}` with no `?email=`. The invite page only knows the masked email, so `/register?redirect=...` opens with an empty email field. Design §7 says "Create account with the email prefilled". The frontend already reads `?email=` (register page line 26); the invitation email (backend `invitations/emails.py`) does not add it. Note that putting the email in the URL exposes it; decide in the design.

**F3 (minor): the email-verification message is still ORT-branded.** Subject "Код подтверждения ОРТ: NNNNNN", From "ОРТ Платформа <noreply@ort.kg>", body "...на платформе подготовки к ОРТ" / "...платформе ОРТ". Design §8.3 says emails use `common.appName`; the invitation emails do ("Платформа"), the auth code email does not.

**F4 (minor, check against §7): the "become a teacher" call to action is still on the student home.** Students on `/courses` still get the card "Хотите вести свои курсы? Запросите доступ учителя. [Стать учителем]", and a pure student sees the "Преподаю / Учусь" tabs. The header now has "Я преподаватель". Design §7 removes the "Become a teacher" link from student navigation. This card is in the page body, so the orchestrator decides whether it stays.

**F5 (minor, T11-style leak): ORT text in a general course.** The general-course create-assessment dialog still shows the hint "Экзамены ОРТ обычно проводятся на одном языке." (`/ru/courses/{course}/assessments` -> "Новое задание").

**F6 (SQLite/dev only, pre-existing): no Cyrillic name search in the user picker on SQLite.** `GET /api/v1/platform/users?limit=10&q=Айгуль` -> 200 `{"items":[],"next_cursor":null}`; `q=newteacher` finds Айгуль Садыкова. Cause: `platform_admin/users_service.py:59-63` lowercases the term in Python but compares with SQL `lower(display_name)`, and SQLite's `lower()` is ASCII-only. PostgreSQL (production) is not affected. In dev and SQLite tests the admin transfer UserPicker cannot find users by a Cyrillic name. The org create-course picker found "Эрлан" (it uses a different path).

**Console and API errors:** no unexpected ones. Over the whole run the only 4xx were the intended ones:
- `404 GET /api/v1/invitations/unknown-or-expired-token-...` (the unknown-token screen);
- `403 POST /api/v1/invitations/{token}/accept` (the mismatch screen).

Each also logs the browser's generic "Failed to load resource" console line. No `pageerror`, no 5xx, no traceback in the backend log.

Not run here: the pytest ORT parity suites and the Playwright baseline comparison (`frontend/e2e/`). This was a manual browser walkthrough only.
