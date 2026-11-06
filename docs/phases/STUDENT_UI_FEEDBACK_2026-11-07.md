# Owner feedback on the student redesign, 2026-11-07 (verbatim brief)

Owner feedback on the student redesign (docs/phases/STUDENT_UI_DESIGN.md). Main rule: improve the existing architecture, don't destroy it. ORT behavior (timers, sections, scoring, imports) stays exactly the same; its look may change. The repo is public: keep calling the reference app "the reference app".

How to work: First write docs/phases/STUDENT_UI_FIX_PLAN.md (architect on Fable): for each problem below, the cause found in the code, the fix, files touched, risks, tests. Record every design and decision in the docs and PRODUCT_DECISIONS.md, then build. Don't stop for my review between the problems; build them in order 1 → 7, each with its tests, ORT review and deploy (Neon backup branch before any migration).

Model rule for this task:
- Architect on Fable: all analysis, design, the fix plan, and reviews of 2–7.
- Implementers on Opus for important work: anything touching data or migrations, analytics counting, access and subscriptions (problem 6), the shell and routing changes (problem 2), the result page, the course/lessons pages (problem 5), cover image upload and storage (problem 7), ORT-related code, and anything that failed once.
- Implementers on Sonnet only for simple, well-specified work: spacing and color/token changes, card and catalog styling, translation keys, renaming, deleting dead code after Opus has identified it, small text fixes.
- Pass the model explicitly in every Agent call. If a Sonnet slice fails or comes back wrong, redo it on Opus; never retry on the same model.

1. Sidebar spacing: in the student sidebar the gap above "Сохранённые" is much larger than between the other items (Главная, Тесты, Аналитика, [big gap], Сохранённые). Find the cause (probably empty group headings "УРОКИ"/"ПРАКТИКА" that keep their spacing). Fix: identical spacing between all items; an empty group takes no space. Check at 1440 and 1920 and in the phone tab bar.

2. Exam pages in the old design: the lobby (/courses/{c}/assessments/{a}), the result and the review open in the old frame (old header, old course menu "Курс, Задания, Оценки, Преподаватели, Мой прогресс, Сохранённые", "Назад к заданиям"). Owner decision, replacing §2.4 of the design:
   - lobby, result and review render inside the new StudentShell with the new tokens and font;
   - the exam player stays full-screen without the sidebar (Bluebook style) but uses the new tokens and font;
   - ORT behavior unchanged; update the ORT baseline screenshots as approved new baselines and keep the behavior tests (e2e, scoring parity) green.
   Redesign the result page: big scaled score on the ORT scale with a clear meaning, section breakdown, mascot, "review mistakes" and "next test" actions. Remove confusing labels ("Незачёт", "Идёт в зачёт", "Процентиль 0.0" for an empty attempt); explain a 0 score below the 60 minimum (owner rule D6) in plain words.
   Then remove redundancy: find old student pages, menus, components and routes that the new shell made unreachable or duplicated (old course sidebar for exam-prep courses, old dashboard parts, old breadcrumbs), and delete them with their tests replaced by new ones. List what you removed.

3. "Открыть попытку" from Сохранённые → Ошибки opens the result in the old frame: fixed by item 2; also make the link open the review directly at that question (anchor), and check every link from the new pages leads to a new-design page.

4. Colors and analytics data:
   - Colors: too many colors without meaning (violet, teal, orange, blue tags, red rings, gold, blue). Make it calm and consistent: one brand blue, gold only for Pro/unlock, neutral section tags (or one subtle tint), and color only where it means something (accuracy: low/mid/high, always with the number). Apply across the whole student area, not just analytics.
   - Data bug: the analytics page shows "Вопросов решено 1, верно 0 из 1" at the top but "40 ответов", "34 ответа" in the weak topics. Find out why (unanswered items counted as answers? different periods?) and fix the counting so every card uses the same definition and period. Add tests.
   - With little data, show "not enough data yet" (mascot) instead of marking every topic "Слабо 0 %". Define a minimum number of answers before a topic is rated.
   - Review the teacher analytics with the same eyes, list what is wrong, and fix it in this step too.

5. Courses with lessons: the reference app also has video courses next to tests: course overview with "Continue your course", progress, syllabus by modules with lessons and durations, an about card, and a lesson page with the video, the course outline on the side and "Next lesson". We already have modules, pages, files and video URL items (8a, U7). Design one course experience on top of the existing modules, for both exam-prep courses and teacher courses, write it in docs/phases/COURSE_LESSONS_DESIGN.md (phone and desktop layouts), then build it:
   - student: overview, syllabus, lesson page, progress, Pro-locked lessons where the course sets it;
   - teacher: building modules and lessons stays today's model, with a better editor design (add video/page/file/test in a module, reorder, publish);
   - how tests and lessons live together in one course and in the student sidebar;
   - keep data changes minimal; list them.

6. Payment: replace the code-first system (docs/phases/S3_ACCESS_DESIGN.md) with a subscription model like the reference app, built on the existing access_passes (they already have start and end). Write docs/phases/SUBSCRIPTION_DESIGN.md, then build:
   - students see one clear Free vs Pro offer with plans (e.g. 1 month, 3 months, until the end of the exam season), what Pro includes, and how to pay (text the owner fills in later);
   - admin: one simple "grant Pro" action (plan or end date), a list of Pro users with end dates, renew and cancel;
   - codes stay only as optional gift/voucher codes, in a simpler admin screen;
   - the exam date countdown stays independent of access;
   - migration: no existing pass or code is lost;
   - automatic online payment: design only (realistic local provider options for Kyrgyzstan, what each needs: contract, fees, webhooks, auto-renewal). Don't build it: it needs a provider contract and keys from the owner.

7. Catalog and course cards redesign, with cover images. Today's catalog cards use random dark colors (dark teal, dark green) that clash with the student palette, and show too much text and too many labels with the same weight ("Открыт для всех", "Платформа", language, full description, a big outline button). Fix:
   - Course cover image: course owners (and platform admins for platform courses) can upload a cover in course settings: JPG/PNG/WebP, max 2 MB, stored in the public R2 bucket with the existing limits and dedup, converted to WebP, cropped to 16:9 with a simple preview. Add the cover field with a minimal migration (Neon backup first). Without an uploaded image, show a generated default cover from the student palette (soft gradient in the brand blues, with a subtle subject icon or a small mascot), never random dark colors. The ORT courses get a nice default cover the owner can replace later.
   - One course card, used everywhere (catalog, home, "my courses"): cover on top; title (max 2 lines); one short meta line (language · number of tests · number of lessons); the teacher or organization name only for non-platform courses; description max 2 lines (full text on the course page); for joined courses a progress bar instead of the description. One clear action: "Записаться" (primary) or "Открыть" for joined courses. Drop the "Открыт для всех" and "Платформа" labels; show a badge only when it matters (e.g. "Pro", "по коду", "заявка").
   - Catalog page: search + language filter only for students; the organization and enrollment-method filters move into a small "Ещё фильтры" or are removed for students. Grid 3 / 2 / 1 columns; designed empty state with the mascot.
   - The course overview page from item 5 uses the same cover as its header banner.

When everything is deployed: one short review list (URLs and what to look at) covering 1–7.
