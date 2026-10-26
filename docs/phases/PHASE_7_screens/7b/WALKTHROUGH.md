# Phase 7b walkthrough (S5 integration, re-run after the S7 UX fixes)

Date 2026-10-26. Branch `phase-7b-s5-integration` (S1-S4 + the S6 security fixes merged); re-run on `phase-7b-s7-uxfix`. Scratch backend through `scripts/e2e_backend.sh` (`env -i`, cwd outside `backend/`, fresh SQLite, console email, `LMS_STORAGE_DRIVER=db`, the e2e ORT seed) on 8072; built frontend (`next build` + `next start` in an rsync'd copy) on 3072; playwright-core with system Chrome (headless). Data: platform admin (e2e seed), organization "Школа-гимназия №5" with org admin Гульнара Осмонова and teacher Айбек Маматов, course "Физика 9 класс" with students Нурлан, Мээрим (ru) and Азамат (ky), independent teacher Эрлан Касымов (personal organization). Scripts: `/tmp/agy_p7b_s7w_scripts/` (form.js fills the S7 structure form) (lib copied from the 7a walkthrough `/tmp/agy_s6w_scripts/`, setup, w1, w3, w9, w11, w14, shots). Each step checks the UI and the API state.

| # | Step | Result | Evidence |
|---|---|---|---|
| | **W1-W2 Platform and organization templates (browser)** | | |
| 1 | platform admin publishes a platform template in the browser (2 sections, time limits, forward-only, allowed types) | PASS | scope=platform status=published v=1 nav=section_forward_only sections=part_a:900s:single_choice+true_false,part_b:900s:numeric+short_text |
| 2 | org admin publishes an organization template and locks it (browser), audited | PASS | scope=organization status=published v=1 locked=true audit=exam_template.lock reason=Единая структура для всех классов |
| | **W3-W8 Teacher: quiz from the locked org template, locks, import format, general CSV import, publish** | | |
| 3 | teacher creates a quiz assignment from the locked org template (browser picker grouped platform / organization) | PASS | sections=theory:1200,problems:1200 locked=true fields=navigation,section_add_remove,section_key,section_order,section_rules,section_time_limit_s picker=[Нет: начать с нуля / Шаблоны платформы / Контрольная: две части · в1 / Шаблоны организации / Контрольная ра |
| 4 | locked structure: 'Добавить раздел' greyed with the template note; section key / time limit greyed | PASS | add.disabled=true key.disabled=true limit.disabled=true note="Разделы заданы шаблоном теста: вопросы добавлять можно, а добавлять, удалять и переставлят" |
| 5 | locked structure: API answers 409 template_locked (add section, navigation, section time limit) | PASS | 409 template_locked:section_add_remove / 409 template_locked:navigation / 409 template_locked:section_time_limit_s |
| 6 | teacher downloads the import-format CSV (BOM, header, one # example row per section) | PASS | import-format-kontrolnaia-rabota-shkola-5-v1.csv header=section,type,stem,option_a,option_b,option_c,option_d,option_e,correct_option,answer,tolerance,answer_min,answer_max,explanation,topic,difficulty,tags,image,external_id rows=#Теория/#Задачи |
| 7 | choosing the exam switches the import language to the exam's language (course default ky, exam ru) | PASS | language=ru |
| 8 | matching general CSV: preview OK, import adds the questions to the right sections (theory 3, problems 1) | PASS | sections=theory:3,problems:1 done="В задание добавлено вопросов: 4." |
| 9 | wrong CSV: import blocked with clear errors (section not in template, type not allowed in section) | PASS | codes=section_not_in_template,type_not_allowed_in_section,type_not_allowed_in_section import.disabled=true |
| 10 | an ORT-format CSV in the general format is refused with format_mismatch (clear message) | PASS | Ошибки (1) Строка Колонка Файл Сообщение — — ort_format.csv Файл не соответствует выбранному формату (например, файл ОРТ в общем формате). Выберите другой формат. Номер строки — строка данных в CSV (з |
| 11 | teacher publishes the template exam (builder) | PASS | status=published version=1 items=4 assignment.publish=409 |
| | **W9-W10 Student takes it; version 2 published** | | |
| 12 | student opens the template exam: lobby shows both sections, Start opens the player | PASS | attempt=1f0bb44b-4aff-42d7-bad4-dcb579c93348 lobby="Мои курсы Физика 9 класс Физика 9 класс Главная Задания Оценки Преподаватели Назад к заданиям Контрольная №1: механика Лимит времени 40 мин Попытки 0 из 1 Разде" |
| 13 | student submits and sees the result (all answers right: full score) | PASS | raw=4.00/4.00 page="Мои курсы Физика 9 класс Физика 9 класс Главная Задания Оценки Преподаватели Назад к заданию Результат Баллы 4 / 4 Сдано: 26.10.2026, 12:49:" |
| 14 | org admin publishes version 2 (browser); the existing exam keeps version 1 and shows v2 as newer | PASS | template v=2 exam v=1 latest=2 theory.min=2 |
| 15 | the attempt started before v2 is unaffected: same sections and items, submits, full score | PASS | start=201 items=4 submit=200 raw=4.00/4.00 |
| 16 | builder badge: 'Из шаблона … в1', newer v2 available, no Upgrade on a published exam with attempts | PASS | Из шаблона «Контрольная работа (школа №5)», в1 / Есть новая версия: в2 |
| 17 | a new exam from the template gets version 2 | PASS | v=2 theory.min=3 |
| | **W11-W13 Save as template, ORT and locked exams, visibility** | | |
| 18 | teacher saves an existing general quiz as a teacher template (draft; the quiz is unchanged) | PASS | href=/ru/exam-templates/a527d883-f2a2-4e23-ad9d-4189624fb065 scope=teacher status=draft sections=1 min=2 |
| 19 | teacher publishes the own template; it appears in the teacher's course picker (group 'Мои шаблоны') | PASS | status=published v=1 picker=teacher,organization,platform |
| 20 | 'Save as template' is absent for the ORT exam (builder) and refused by the API (409 preset_not_templatable) | PASS | buttons=0 api=409 preset_not_templatable |
| 21 | 'Save as template' is absent for an exam made from a locked template and refused by the API (409 template_locked) | PASS | buttons=0 api=409 template_locked |
| 22 | independent teacher (personal org): the school's template is not in the picker, GET is 404, create is refused | PASS | picker=[Нет: начать с нуля / Контрольная: две части · в1] get=404 create=404 template_not_found |
| 23 | platform template is visible to all: in the independent teacher's and the school teacher's pickers | PASS | independent=platform school=teacher,organization,platform |
| 24 | a teacher's own template stays private (404 for another teacher) | PASS | get=404 |
| | **W14 ORT (browser, unchanged)** | | |
| 25 | ORT course: every ORT exam is listed as a quiz assignment (teacher table) | PASS | quiz:ОРТ E2E / quiz:ОРТ E2E staff |
| 26 | ORT student sees the exam card(s) with 'Экзамен ОРТ' and Start | PASS | Мои курсы ОРТ (на русском) ОРТ (на русском) Главная Задания Оценки Преподаватели Задания ОРТ E2E Не начато Экзамен ОРТ Осталось попыток: 1 Начать ОРТ E2E staff Не начато Экзамен ОРТ Осталось попыток:  |
| 27 | Start on the card opens the ORT lobby | PASS | /ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/75226253-8d47-46ad-a3a7-c7a45d6f2d7d |
| 28 | the ORT player opens | PASS | /ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/attempts/b84692fa-29a9-47f4-b8db-b3b942b95124 |
| 29 | ORT result equals the reference attempt with the same answers (raw score, scaled grade, sections) | PASS | raw=4.00 scaled=96.00 ref raw=4.00 scaled=96.00 |
| 30 | ORT gradebook: the exam is one column (assignment id), the cell carries the scaled grade | PASS | col=ОРТ E2E cell=96.00 label=null |
| 31 | ORT import page: ORT format preselected, no exam-template validation select (general format only) | PASS | format=full_main validateSelect=0 |
| 32 | ORT builder: no template badge and no 'Save as template' | PASS |  |

**32 steps, 32 PASS, 0 FAIL.**

## ORT

- W14: the ORT exams stay quiz assignments in ORT (Russian); a student starts from the card, the unchanged lobby and player open, the result (raw and scaled) equals the e2e reference attempt with the same answers, the ORT gradebook column carries the same scaled value. The ORT import page keeps the ORT format preselected and shows no template validation select; the ORT builder has no template badge and no "Save as template" (API 409 `preset_not_templatable`).
- Backend: `tests/lms/test_ort_*.py` (cutover flow, e2e API, expressibility, gradebook golden, import golden, parity, seed, snapshot template keys) 37 passed, 7 skipped (oracle removed in Phase 5, `hypothesis` not installed, one PG-only seed test, which passes in the PG suite).
- `git diff --stat origin/lms -- backend/app/lms/content/importers/{ort_csv,bundle,rules}.py`: empty.
- `frontend/e2e` (`ort.spec.ts` + `ort-visual.spec.ts`), fresh build, run twice: 10/10 passed both times, zero pixel diffs (no baseline changed; `docs/phases/ORT_BASELINE/` untouched).

## Findings fixed during S5 (frontend reconciled with the backend; backend only for one clear bug)

- Publish returned `{template, version, unchanged}`, the editor treated it as a template (crash after "Publish"); the identical-draft case now says "nothing changed".
- `GET .../versions` is a plain list, the client expected a page (the versions table stayed empty).
- Lock / promote menu items now follow the server flags `can_lock` / `can_promote` instead of guessing from the area.
- Save as template sent the section row position instead of the 1-based ordinal.
- Quiz assignment from a template sent `preset: "none"`, which the assignments route refuses (`preset_template_exclusive`): creating a quiz from a template failed in the browser. The body now carries no preset.
- Builder: a locked exam template now greys "Add section", reorder and delete (with the note "sections are fixed by the exam template") and, in the section dialog, the key, time limit and rules; the scheme picker follows the `scheme` lock. Preset (ORT) exams are unchanged (empty lock set).
- Import: the attach result (`attached`) is shown (added per section, skipped with reasons); choosing a template exam switches the import language to one of the exam's languages (the course default `ky` made every attach skip with `item_language_mismatch`); template issue texts carry their parameters (section, type, allowed types, counts); four general-importer codes and `attach_skipped` had no translation.
- Audit log filter offers the target types `exam_template`, `assessment`, `organization`, `invitation`.
- Backend (bug, with test `tests/test_cors_expose_headers.py`): CORS did not expose `Content-Disposition`, so cross-origin downloads lost the server's file name.

## S7 UX fixes (re-run of this walkthrough on `phase-7b-s7-uxfix`)

- The template editor has no JSON field any more: a structure form (default settings, section cards with add / remove /
  move, key from the title under "Advanced", time in minutes, question counts, question types from the block catalog,
  passages, parameters when the spec has them, lock scope checkboxes). The raw JSON stays behind a collapsed
  "Advanced (JSON)" disclosure for the platform admin only. W1 and W10 now fill this form in the browser.
- `spec_invalid` details carry a machine `type` (and `limit`); the UI translates them per field in en/ky/ru and names
  the section by its title ("Section n" when untitled). No English server text in the UI.
- Result page of a general exam: section rows show the section titles (result sections carry the snapshot title).
- Import-format file name: Cyrillic titles are transliterated into the ASCII slug (e.g.
  `import-format-kontrolnaia-rabota-shkola-5-v1.csv`).
- Import: type names and the exam's section titles in template issues and in the attach summary; `too_many_items`
  names the section and its maximum (backend `skip_details`).
- Template picker: locked structure line, navigation line, description. Save-as dialog: one column on a phone.
