import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { sectionCounts, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * Phase 8a modules walk (PHASE_8A_DESIGN 11): a teacher of a general course writes a page (with math) and uploads a
 * PDF, builds three modules (M1 page + PDF, M2 a quiz made with "New quiz" in the 7c editor with "score at least
 * 80 %", M3 after M2 and sequential), publishes; the student sees M2 locked by its opening date (the quiz lobby
 * answers 423 with the reason) and M3 locked behind M2, opens the page, downloads the PDF, scores 70 % (M3 stays
 * locked), retakes with 90 % (M3 opens); the teacher overrides the grade to 60 % (M3 stays open), re-applies the rules
 * (M3 locks again); an announcement goes from draft to posted and reaches the student's list and home; the course home
 * switches to a page. Then the ORT proof (design 13): an ORT exam listed in a locked module of the ORT course still
 * starts, and the student sees the new tabs only while structure is published (cleaned up afterwards, so the ORT
 * specs that run next see the course exactly as seeded).
 *
 * Phase 8c S4a (PHASE_8C_DESIGN 12): the teacher works on the Course page (`base`; the staff `/modules` route redirects
 * there), adds items from the grouped "+ Add" menu (`coursePage.addItems.*`), publishes with the icon button
 * (`aria-pressed`) and finds a module card by its `#m-{id}` anchor; the student parts assert the course sidebar
 * (`courseNav`) instead of the old tab bar. Written against the design before S2 (course page) and S3 (one-page
 * objects) were merged: the selectors below are the design's roles and i18n keys.
 *
 * Data: `seed_backend.py` (`seed_modules`, after every ORT and quiz-editor row): course "Курс модулей E2E" (ru, ky, en)
 * of an approved teacher, published, empty; one enrolled student; one extra ORT (Russian) student.
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/modules.spec.ts
 * (in a git worktree add E2E_PYTHON=<main repo>/backend/venv/bin/python). With PHASE8A_SCREENS_DIR=<dir> the last test
 * also writes the UX-gate screenshots (docs/phases/PHASE_8A_screens/).
 */

const L = "ru" as const;
/** UX-gate screenshot folder (docs/phases/PHASE_8A_screens); unset = the screenshot test is skipped. */
const SCREENS = process.env.PHASE8A_SCREENS_DIR ? path.resolve(process.env.PHASE8A_SCREENS_DIR) : null;
if (SCREENS) fs.mkdirSync(path.join(SCREENS, "ort-review"), { recursive: true });
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);

const PAGE_TITLE = "Введение в дроби";
const PAGE_BODY = "## Что такое дробь\n\nДробь $\\frac{a}{b}$ показывает часть целого.\n\n$$x^2 + y^2 = z^2$$\n\n- числитель\n- знаменатель";
const FILE_TITLE = "Конспект урока";
const M1 = "Модуль 1. Знакомство";
const M2 = "Модуль 2. Проверка";
const M3 = "Модуль 3. Итоги";
const QUIZ = "Тест по дробям";
const LINK_TITLE = "Дополнительное чтение";
const ANN_TITLE = "Контрольная в пятницу";

/** A tiny valid PDF (the server checks the magic bytes and the size). */
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

async function api(user: SeedUser, method: string, path: string, body?: unknown, ok = [200, 201, 204]) {
  const r = await fetch(`${seed().api}/api/v1${path}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(ok, `${method} ${path} -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

async function open(browser: Browser, user: SeedUser, viewport = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light", acceptDownloads: true });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

/** Student outline: one `section` per module (unchanged by 8c). */
const moduleCard = (page: Page, title: string) => page.locator("section").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
/** Teacher Course page (8c): every module card carries the anchor `#m-{moduleId}` (design 3.3, 5.3). */
const tCard = (page: Page, title: string) =>
  page.locator('[id^="m-"]').filter({ has: page.getByRole("heading", { name: title, exact: true }) }).first();
/** The course sidebar (design 2.1): staff and students, same landmark name as the old tab bar. */
const sidebar = (page: Page) => page.getByRole("navigation", { name: t("courses.home.tabsLabel") });

async function createModule(page: Page, title: string) {
  await page.getByRole("button", { name: t("modules.editor.newModule") }).first().click();
  const dlg = page.getByRole("dialog", { name: t("modules.settings.createTitle") });
  await dlg.getByRole("textbox", { name: t("modules.settings.titleLabel") }).fill(title);
  await dlg.getByRole("button", { name: t("modules.settings.create") }).click();
  await expect(dlg).toBeHidden();
  await expect(tCard(page, title)).toBeVisible();
}

async function moduleMenu(page: Page, title: string, item: string) {
  const card = tCard(page, title);
  await card.getByRole("button", { name: t("modules.editor.actions") }).first().click();
  await page.getByRole("menuitem", { name: item }).click();
}

/** "+ Add" in a module header, then the item from the grouped menu (Content: page, file, link, header; Assessment: quiz, assignment). */
async function addItem(page: Page, module: string, kind: "page" | "file" | "link" | "header" | "quiz" | "assignment", pick?: string, req?: string, threshold?: string) {
  await tCard(page, module).getByRole("button", { name: t("modules.editor.addItem") }).first().click();
  await page.getByRole("menuitem", { name: t(`coursePage.addItems.${kind}`) }).click();
  const dlg = page.getByRole("dialog", { name: t("modules.add.title") });
  if (pick) await dlg.getByRole("radio", { name: new RegExp(pick) }).check();
  if (req) await dlg.getByRole("radio", { name: req, exact: true }).check();
  if (threshold) await dlg.getByRole("spinbutton").fill(threshold);
  return dlg;
}

async function studentModules(page: Page, cid: string) {
  await page.goto(`/${L}/courses/${cid}/modules`);
  await expect(page.getByRole("heading", { name: M1, exact: true })).toBeVisible();
  await settle(page);
}

/** Publish icon button of a module header or item row (design 3.6): `aria-pressed` = published. */
const publishIcon = (card: Locator, title: string, lang: "ru" | "en" = "ru") =>
  card.getByRole("button", { name: tr(lang, "modules.editor.publishToggle", { title }), exact: true });

const badge = (page: Page, title: string, state: string) => moduleCard(page, title).getByText(t(`modules.state.${state}`), { exact: true });

test.describe("modules walk (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("teacher builds, student unlocks, teacher re-applies, announcements, course home", async ({ browser }) => {
    test.setTimeout(420_000);
    const md = seed().modules;
    const cid = md.course_id;
    const base = `/${L}/courses/${cid}`;
    const tp = await open(browser, md.teacher);

    // ---- page with math (Markdown, server preview), published
    await tp.goto(`${base}/pages/new`);
    await tp.getByRole("textbox", { name: t("pages.editor.fieldTitle") }).fill(PAGE_TITLE);
    await tp.getByRole("textbox", { name: t("pages.editor.fieldBody") }).fill(PAGE_BODY);
    await tp.getByRole("switch", { name: t("pages.editor.fieldPublished") }).click();
    await tp.getByRole("button", { name: t("common.save") }).first().click();
    await tp.waitForURL(/\/pages\/[0-9a-f-]{36}/); // 8c: the page object (`?tab=edit`), was `/edit`
    const pageId = /\/pages\/([0-9a-f-]{36})/.exec(tp.url())![1];

    // ---- PDF upload (published)
    await tp.goto(`${base}/files`);
    await tp.getByRole("button", { name: t("courseFiles.upload") }).first().click();
    const up = tp.getByRole("dialog", { name: t("courseFiles.uploadTitle") });
    await up.locator("input[type=file]").setInputFiles({ name: "konspekt.pdf", mimeType: "application/pdf", buffer: PDF });
    await up.getByRole("textbox", { name: t("courseFiles.fieldTitle") }).fill(FILE_TITLE);
    await up.getByRole("button", { name: t("courseFiles.upload") }).click();
    await expect(up).toBeHidden();
    await expect(tp.getByText(FILE_TITLE, { exact: true })).toBeVisible();

    // ---- three modules
    await tp.goto(`${base}/modules`);
    await tp.waitForURL(new RegExp(`/courses/${cid}$`)); // 8c: the staff /modules route redirects to the Course page
    await expect(tp.getByText(t("modules.editor.emptyTitle"))).toBeVisible();
    await createModule(tp, M1);
    await createModule(tp, M2);
    await createModule(tp, M3);

    // M1: the page ("view" requirement) and the PDF
    let dlg = await addItem(tp, M1, "page", PAGE_TITLE, t("modules.reqPicker.types.view"));
    await dlg.getByRole("button", { name: t("modules.add.submit") }).click();
    await expect(dlg).toBeHidden();
    dlg = await addItem(tp, M1, "file", FILE_TITLE);
    await dlg.getByRole("button", { name: t("modules.add.submit") }).click();
    await expect(dlg).toBeHidden();
    await expect(tCard(tp, M1).getByText(FILE_TITLE, { exact: true })).toBeVisible();

    // M2: "+ Add -> Quiz" creates the quiz assignment and its item, then opens the 7c editor
    dlg = await addItem(tp, M2, "quiz");
    await dlg.getByRole("textbox", { name: t("modules.add.quizTitle") }).fill(QUIZ);
    for (const other of ["ky", "en"]) {
      const box = dlg.getByRole("checkbox", { name: t(`courses.languages.${other}`) });
      if (await box.isChecked()) await box.uncheck();
    }
    const quizResp = tp.waitForResponse((r) => r.request().method() === "POST" && /\/modules\/[0-9a-f-]{36}\/quiz$/.test(r.url()));
    await dlg.getByRole("button", { name: t("modules.add.createQuiz") }).click();
    const quizOut = await (await quizResp).json();
    const assignmentId: string = quizOut.assignment.id;
    const aid: string = quizOut.assessment_id;
    await tp.waitForURL(new RegExp(`/assessments/${aid}/edit`));
    await expect(tp.getByText(t("quizEditor.section.emptyQuizTitle"))).toBeVisible();
    // three single-choice questions worth 1, 2 and 7 points; "B" is always right (70 % = only Q3, 90 % = Q2 + Q3)
    for (const [i, pts] of [[1, "1"], [2, "2"], [3, "7"]] as const) {
      await tp.getByRole("button", { name: t("quizEditor.card.addQuestion") }).last().click();
      await tp.getByLabel(t("bank.editor.stem")).fill(`Вопрос ${i}: выберите «Да»`);
      await tp.getByLabel(t("quizEditor.card.answerLabel", { letter: "A" })).fill("Нет");
      await tp.getByLabel(t("quizEditor.card.answerLabel", { letter: "A" })).press("Enter");
      await tp.keyboard.type("Да");
      await tp.getByRole("radio", { name: t("quizEditor.card.markCorrect", { letter: "B" }) }).check();
      await tp.getByLabel(t("bank.editor.points"), { exact: true }).fill(pts);
      await tp.getByRole("button", { name: t("quizEditor.card.done") }).click();
      await expect(tp.getByLabel(t("bank.editor.stem"))).toHaveCount(0);
      await settle(tp);
    }
    // three attempts allowed (builder setting through the API; the editor's settings panel is 7c ground)
    const a0 = await api(md.teacher, "GET", `/courses/${cid}/assessments/${aid}`);
    await api(md.teacher, "PATCH", `/courses/${cid}/assessments/${aid}`, { draft_rev: a0.draft_rev, allowed_attempts: 3 });
    await tp.reload();
    await tp.getByRole("button", { name: t("quizEditor.publishBar.publish") }).click();
    await expect(tp.getByText(t("assessments.status.published")).first()).toBeVisible();

    // back in the outline: requirement "score at least 80 %" on the quiz item
    await tp.goto(base);
    const quizRow = tCard(tp, M2).locator("li").filter({ hasText: QUIZ });
    await quizRow.getByRole("button", { name: t("modules.editor.actions") }).click();
    await tp.getByRole("menuitem", { name: t("modules.editor.setRequirement") }).click();
    const reqDlg = tp.getByRole("dialog", { name: t("modules.reqPicker.title") });
    await reqDlg.getByRole("radio", { name: t("modules.reqPicker.types.min_percent"), exact: true }).check();
    await reqDlg.getByRole("spinbutton").fill("80");
    await reqDlg.getByRole("button", { name: t("lms.common.save") }).click();
    await expect(reqDlg).toBeHidden();
    await expect(quizRow).toContainText(t("modules.req.min_percent", { threshold: 80 }));
    await expect(quizRow).not.toContainText(t("modules.warnings.target_unpublished"));

    // M3: sequential, after M2; a link with "mark as done"
    await moduleMenu(tp, M3, t("modules.editor.editSettings"));
    let set = tp.getByRole("dialog", { name: t("modules.settings.editTitle") });
    await set.getByRole("checkbox", { name: t("modules.settings.sequential") }).check();
    await set.getByRole("button", { name: t("lms.common.save") }).click();
    await expect(set).toBeHidden();
    await moduleMenu(tp, M3, t("modules.editor.prerequisites"));
    const pre = tp.getByRole("dialog", { name: t("modules.prereq.title") });
    await pre.getByRole("checkbox", { name: M2 }).check();
    await pre.getByRole("button", { name: t("lms.common.save") }).click();
    await expect(pre).toBeHidden();
    await expect(tCard(tp, M3)).toContainText(t("modules.editor.after", { titles: M2 }));
    dlg = await addItem(tp, M3, "link", undefined, t("modules.reqPicker.types.mark_done"));
    await dlg.getByRole("textbox", { name: t("modules.add.url") }).fill("https://example.com/fractions");
    await dlg.getByRole("textbox", { name: t("modules.add.titleOverride") }).fill(LINK_TITLE);
    await dlg.getByRole("button", { name: t("modules.add.submit") }).click();
    await expect(dlg).toBeHidden();

    // M2 opens tomorrow (the 423 check below); then publish all three
    const tomorrow = new Date(Date.now() + 24 * 3600_000);
    tomorrow.setUTCHours(9, 0, 0, 0);
    await moduleMenu(tp, M2, t("modules.editor.editSettings"));
    set = tp.getByRole("dialog", { name: t("modules.settings.editTitle") });
    await set.getByLabel(t("modules.settings.unlockAt")).fill(tomorrow.toISOString().slice(0, 16));
    await set.getByRole("button", { name: t("lms.common.save") }).click();
    await expect(set).toBeHidden();
    for (const m of [M1, M2, M3]) {
      await publishIcon(tCard(tp, m), m).click();
      await expect(publishIcon(tCard(tp, m), m)).toHaveAttribute("aria-pressed", "true");
    }
    await settle(tp);

    // ---- student: the course home is the modules view; M1 open, M2 opens tomorrow, M3 waits for M2
    const sp = await open(browser, md.student);
    await sp.goto(base);
    await expect(sp.getByRole("heading", { name: M1, exact: true })).toBeVisible();
    await settle(sp);
    await expect(badge(sp, M1, "unlocked")).toBeVisible();
    await expect(badge(sp, M2, "locked")).toBeVisible();
    await expect(badge(sp, M3, "locked")).toBeVisible();
    await expect(moduleCard(sp, M2)).toContainText(t("modules.reason.unlockAt", { date: "" }).trim());
    await expect(moduleCard(sp, M3)).toContainText(t("modules.reason.prerequisite", { title: M2 }));
    await expect(moduleCard(sp, M2).getByRole("link", { name: new RegExp(QUIZ) })).toHaveCount(0);
    // the quiz by URL while M2 is locked: the lobby says why (423 module_locked)
    await sp.goto(`${base}/assessments/${aid}`);
    await expect(sp.getByText(t("pages.locked.title"))).toBeVisible();
    await expect(sp.getByText(t("pages.locked.bodyModule", { title: M2 }))).toBeVisible();
    const startTry = await fetch(`${seed().api}/api/v1/courses/${cid}/assessments/${aid}/attempts`, {
      method: "POST", headers: { Authorization: `Bearer ${md.student.token}`, "Content-Type": "application/json" }, body: JSON.stringify({ language: "ru" }),
    });
    expect(startTry.status).toBe(423);
    expect((await startTry.json()).error.code).toBe("module_locked");

    // ---- teacher clears the opening date: M2 opens, M3 still waits
    await moduleMenu(tp, M2, t("modules.editor.editSettings"));
    set = tp.getByRole("dialog", { name: t("modules.settings.editTitle") });
    await set.getByLabel(t("modules.settings.unlockAt")).fill("");
    await set.getByRole("button", { name: t("lms.common.save") }).click();
    await expect(set).toBeHidden();
    await studentModules(sp, cid);
    await expect(badge(sp, M2, "unlocked")).toBeVisible();
    await expect(badge(sp, M3, "locked")).toBeVisible();

    // ---- the page (KaTeX) records "view": M1 has its only requirement met
    await moduleCard(sp, M1).getByRole("link", { name: new RegExp(PAGE_TITLE) }).click();
    await sp.waitForURL(new RegExp(`/pages/${pageId}\\?from=module`));
    await expect(sp.getByRole("heading", { name: PAGE_TITLE })).toBeVisible();
    await expect(sp.locator(".katex").first()).toBeVisible();
    // 8a UX / 8c: the Course link of the sidebar stays active on a page (design 2.2) and the page offers the way back (M7)
    await expect(sidebar(sp).getByRole("link", { name: t("courses.home.tab"), exact: true })).toHaveAttribute("aria-current", "page");
    await sp.getByRole("link", { name: t("pages.locked.toModules") }).click();
    await sp.waitForURL(new RegExp(`/courses/${cid}/modules$`));
    await studentModules(sp, cid);
    await expect(badge(sp, M1, "completed")).toBeVisible();
    // ---- the PDF downloads through the authenticated content route
    const download = sp.waitForEvent("download");
    await moduleCard(sp, M1).getByRole("button", { name: new RegExp(FILE_TITLE) }).click();
    const file = await download;
    const saved = await file.path();
    expect(saved).toBeTruthy();
    expect(fs.readFileSync(saved!).subarray(0, 5).toString()).toBe("%PDF-");

    // ---- quiz attempt 1: 70 % (only Q3 right) -> released, below 80 %, M3 stays locked
    const takeQuiz = async (answers: number[]) => {
      await studentModules(sp, cid);
      await moduleCard(sp, M2).getByRole("link", { name: new RegExp(QUIZ) }).click();
      await sp.waitForURL(new RegExp(`/assessments/${aid}`));
      await sp.getByRole("button", { name: t("assessments.lobby.start") }).click();
      await sp.waitForURL(/\/attempts\/[0-9a-f-]{36}/);
      const attemptId = /\/attempts\/([0-9a-f-]{36})/.exec(sp.url())![1];
      for (const [i, choice] of answers.entries()) {
        await expect(sp.getByText(`Вопрос ${i + 1}: выберите «Да»`)).toBeVisible();
        const radio = sp.getByRole("radiogroup", { name: t("player.answers") }).getByRole("radio").nth(choice);
        await radio.click();
        await expect(radio).toHaveAttribute("aria-checked", "true");
        if (i < answers.length - 1) await sp.getByRole("button", { name: t("player.next") }).click();
      }
      await sp.getByRole("button", { name: t("player.finishTest") }).first().click();
      await sp.getByRole("dialog").getByRole("button", { name: t("player.submit.confirm") }).click();
      await expect.poll(async () => (await api(md.student, "GET", `/attempts/${attemptId}`)).status, { timeout: 20_000 }).toBe("graded");
      return attemptId;
    };
    await takeQuiz([0, 0, 1]);
    await studentModules(sp, cid);
    await expect(badge(sp, M2, "started")).toBeVisible();
    await expect(moduleCard(sp, M2)).toContainText(t("modules.req.best", { percent: 70 }));
    await expect(badge(sp, M3, "locked")).toBeVisible();

    // ---- attempt 2: 90 % -> M2 completed, M3 opens (its link item with "mark as done")
    await takeQuiz([0, 1, 1]);
    await studentModules(sp, cid);
    await expect(badge(sp, M2, "completed")).toBeVisible();
    await expect(badge(sp, M3, "unlocked")).toBeVisible();
    await expect(moduleCard(sp, M3).getByRole("checkbox", { name: t("modules.markDone") })).toBeVisible();

    // ---- the teacher overrides the grade down to 60 %: M3 stays open (a met requirement stays met)
    const subs = await api(md.teacher, "GET", `/courses/${cid}/assignments/${assignmentId}/submissions`);
    const sub = await api(md.teacher, "GET", `/courses/${cid}/submissions/${subs.rows[0].cell.submission_id}`);
    await api(md.teacher, "PUT", `/courses/${cid}/submissions/${sub.submission_id}/override`, { points: 6, reason: "Пересмотр", version: sub.version });
    await studentModules(sp, cid);
    await expect(badge(sp, M2, "completed")).toBeVisible();
    await expect(badge(sp, M3, "unlocked")).toBeVisible();

    // ---- "Re-apply rules" (whole course): M2 is no longer met at 60 %, M3 locks again
    await tp.goto(base);
    await tp.getByRole("button", { name: t("coursePage.moreActions"), exact: true }).click(); // course toolbar "⋯"
    await tp.getByRole("menuitem", { name: t("modules.editor.reapplyCourse") }).click();
    const re = tp.getByRole("alertdialog", { name: t("modules.editor.reapplyTitle") });
    await re.getByRole("button", { name: t("modules.editor.reapply") }).click();
    await expect(re).toBeHidden();
    await studentModules(sp, cid);
    await expect(badge(sp, M2, "started")).toBeVisible();
    await expect(badge(sp, M3, "locked")).toBeVisible();
    await expect(badge(sp, M1, "completed")).toBeVisible();

    // ---- student home: the quiz (the first open item with an unmet requirement) is listed once: "Next up" when it is
    // there, else "continue in your courses" (8a UX M4: no row repeats the hero or a "Next up" row)
    await sp.goto(`/${L}/courses`);
    await expect(sp.locator('section[aria-labelledby="home-next"]')).toBeVisible();
    const inNext = await sp.locator('section[aria-labelledby="home-next"]').getByText(QUIZ).count();
    const inModulesNext = await sp.locator('section[aria-labelledby="home-modules-next"]').getByText(QUIZ).count();
    expect(inNext + inModulesNext).toBe(1);

    // ---- announcement: draft (students do not see it), then posted -> course list and the student home
    await tp.goto(`${base}/announcements`);
    await tp.getByRole("link", { name: t("announcements.new") }).first().click();
    await tp.getByRole("textbox", { name: t("announcements.fieldTitle") }).fill(ANN_TITLE);
    await tp.getByRole("textbox", { name: t("announcements.fieldBody") }).fill("Повторите **дроби** и задачу $\\frac{3}{4} + \\frac{1}{4}$.");
    await tp.getByRole("button", { name: t("announcements.saveDraft") }).click();
    await tp.waitForURL(new RegExp(`${base}/announcements$`));
    await expect(tp.getByRole("heading", { name: t("announcements.drafts") })).toBeVisible();
    await sp.goto(`${base}/announcements`);
    await expect(sp.getByText(ANN_TITLE)).toHaveCount(0);
    await tp.getByRole("button", { name: t("announcements.postNow") }).click();
    await expect(tp.getByRole("heading", { name: t("announcements.drafts") })).toHaveCount(0);
    await sp.reload();
    await expect(sp.getByRole("heading", { name: ANN_TITLE })).toBeVisible();
    await expect(sp.locator(".katex").first()).toBeVisible();
    await sp.goto(`/${L}/courses`);
    await expect(sp.locator('section[aria-labelledby="home-announcements"]')).toContainText(ANN_TITLE);

    // ---- course home switched to the page (Settings -> "Course home"): the student's course opens on the page
    await tp.goto(`${base}/settings`);
    await tp.getByRole("combobox", { name: t("courses.homeKind.label") }).selectOption("page");
    await tp.getByRole("combobox", { name: t("courses.homeKind.page") }).selectOption(pageId);
    const homeSection = tp.locator("form#course-home");
    await homeSection.getByRole("button", { name: t("lms.common.save") }).click();
    await expect(tp.getByText(t("courses.settings.saved")).first()).toBeVisible();
    await sp.goto(base);
    await expect(sp.getByRole("heading", { name: PAGE_TITLE })).toBeVisible();
    await expect(sp.locator(".katex").first()).toBeVisible();
    // and back to modules (the screenshots below start from the modules home)
    await tp.getByRole("combobox", { name: t("courses.homeKind.label") }).selectOption("modules");
    await homeSection.getByRole("button", { name: t("lms.common.save") }).click();
    await expect.poll(async () => (await api(md.teacher, "GET", `/courses/${cid}`)).home_kind).toBe("modules");
    await sp.goto(base);
    await expect(sp.getByRole("heading", { name: M1, exact: true })).toBeVisible();
    await tp.context().close();
    await sp.context().close();
  });

  test("ORT: structure is additive, the ORT exam is never gated (design 13)", async ({ browser }) => {
    test.setTimeout(300_000);
    const s = seed();
    const admin = s.admin;
    const cid = s.course_id;
    const base = `/${L}/courses/${cid}`;
    const ortStudent = s.modules.ort_student;
    const created: { modules: string[]; file?: string } = { modules: [] };
    const tabs = sidebar;
    /** ORT review images (orchestrator approval; never written into docs/phases/ORT_BASELINE). */
    const review = async (page: Page, name: string) => {
      if (!SCREENS) return;
      for (const vp of ["phone", "desktop"] as const) {
        await page.setViewportSize(VIEWPORTS[vp]);
        await settle(page);
        await page.screenshot({ path: path.join(SCREENS, "ort-review", `${name}-${vp}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
      }
      await page.setViewportSize(VIEWPORTS.desktop);
    };
    try {
      // before: the ORT student's sidebar has no Files / Announcements (auto-hide), the home lists the exams
      const sp = await open(browser, ortStudent);
      await sp.goto(base);
      await expect(sp.getByRole("link", { name: "ОРТ E2E", exact: true }).first()).toBeVisible();
      await expect(tabs(sp).getByRole("link", { name: t("courses.home.tab"), exact: true })).toBeVisible();
      await expect(tabs(sp).getByRole("link", { name: t("announcements.title"), exact: true })).toHaveCount(0);
      await expect(tabs(sp).getByRole("link", { name: t("courseFiles.title"), exact: true })).toHaveCount(0);
      const course0 = await api(ortStudent, "GET", `/courses/${cid}`);
      expect(course0.home_kind).toBe("assignments");
      expect(course0.features).toEqual({ modules: false, files: false, announcements: false });
      await review(sp, "ort-student-course-home-before");
      // the home kind is locked on ORT courses
      await api(admin, "PATCH", `/courses/${cid}`, { home_kind: "modules" }, [409]);

      // staff see every sidebar link in the ORT course (owner Q5 default; Files and Announcements marked as hidden)
      const ap = await open(browser, admin);
      await ap.goto(base);
      for (const name of [t("courses.home.tab"), t("assignments.tab"), t("courseFiles.title"), t("announcements.title")]) {
        await expect(tabs(ap).getByRole("link", { name: new RegExp(`^${name}(\\s|$)`) })).toBeVisible(); // staff links may carry the "hidden from students" mark text
      }
      await review(ap, "ort-teacher-course-home-after");

      // a published module with a PDF, and a module that opens tomorrow listing the ORT exam
      const form = new FormData();
      form.append("file", new Blob([PDF], { type: "application/pdf" }), "ort-rules.pdf");
      form.append("folder", "");
      form.append("title", "Правила ОРТ");
      form.append("published", "true");
      const upr = await fetch(`${s.api}/api/v1/courses/${cid}/course-files`, { method: "POST", headers: { Authorization: `Bearer ${admin.token}` }, body: form });
      expect(upr.status).toBe(201);
      created.file = (await upr.json()).id;
      const mA = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: "Подготовка" }, published: true });
      created.modules.push(mA.id);
      await api(admin, "POST", `/courses/${cid}/modules/${mA.id}/items`, { kind: "file", file_id: created.file, published: true });
      const assignments = await api(admin, "GET", `/courses/${cid}/assignments?limit=100`);
      const examAssignment = (assignments.items as { id: string; assessment_id: string | null }[]).find((a) => a.assessment_id === s.exam.id)!;
      expect(examAssignment).toBeTruthy();
      const mB = await api(admin, "POST", `/courses/${cid}/modules`, {
        title: { ru: "Пробный ОРТ" }, published: true, unlock_at: new Date(Date.now() + 2 * 24 * 3600_000).toISOString(),
      });
      created.modules.push(mB.id);
      await api(admin, "POST", `/courses/${cid}/modules/${mB.id}/items`, { kind: "assignment", assignment_id: examAssignment.id, published: true });

      // after: the student sees Modules and Files; the ORT module lists the exam as locked, yet the exam starts
      await sp.goto(base);
      await expect(tabs(sp).getByRole("link", { name: t("courseFiles.title"), exact: true })).toBeVisible();
      await expect(sp.getByRole("link", { name: "ОРТ E2E", exact: true }).first()).toBeVisible(); // home unchanged
      await review(sp, "ort-student-course-home-with-structure");
      await sp.goto(`${base}/modules`);
      await expect(badge(sp, "Пробный ОРТ", "locked")).toBeVisible();
      await expect(badge(sp, "Подготовка", "completed")).toBeVisible(); // no requirement: complete once open
      // 8a UX M6: the exam row inside the locked module is open (gating-exempt) and says where it lives
      await expect(moduleCard(sp, "Пробный ОРТ").getByRole("link")).toContainText(t("modules.availableInAssignments"));
      await review(sp, "ort-student-modules");
      const exam = new OrtExam(sp, "ru");
      await exam.openLobby();
      await exam.assertLobby();
      await exam.start();
      for (const pos of [1, 2, 3, 4]) await exam.skipSection(pos);
      await exam.openSubmit({ unanswered: sectionCounts()[4], flagged: 0 });
      await exam.confirmSubmit();
      await exam.assertResult(0, sectionCounts().reduce((a, b) => a + b, 0));
      await ap.context().close();
      await sp.context().close();
    } finally {
      // the ORT specs that run next see the course exactly as seeded
      for (const id of created.modules) await api(admin, "DELETE", `/courses/${cid}/modules/${id}`);
      if (created.file) await api(admin, "DELETE", `/courses/${cid}/course-files/${created.file}`);
      const after = await api(ortStudent, "GET", `/courses/${cid}`);
      expect(after.features).toEqual({ modules: false, files: false, announcements: false });
    }
  });

  // ---------------------------------------------------------------- UX gate screenshots (PHASE_8A_DESIGN 12)
  test("UX gate screenshots (PHASE8A_SCREENS_DIR)", async ({ browser }) => {
    test.skip(!SCREENS, "set PHASE8A_SCREENS_DIR to write the UX-gate screenshots");
    test.setTimeout(900_000);
    const md = seed().modules;
    const cid = md.course_id;
    const outline = await api(md.teacher, "GET", `/courses/${cid}/modules`);
    const byRu = (title: string) => outline.modules.find((m: { title: { ru: string } }) => m.title.ru === title);
    // localized titles for the en / ky screens
    for (const [ru, ky, en] of [[M1, "1-модуль. Таанышуу", "Module 1. Getting started"], [M2, "2-модуль. Текшерүү", "Module 2. Check"], [M3, "3-модуль. Жыйынтык", "Module 3. Summary"]]) {
      await api(md.teacher, "PATCH", `/courses/${cid}/modules/${byRu(ru).id}`, { title: { ru, ky, en } });
    }
    // a fourth module opening later with a page (the locked page screen and the "opens on" reason)
    const pages = await api(md.teacher, "GET", `/courses/${cid}/pages?limit=50`);
    const ruPage = pages.items.find((p: { title: string }) => p.title === PAGE_TITLE);
    for (const [lang, title, body] of [
      ["en", "Introduction to fractions", "## What is a fraction\n\nA fraction $\\frac{a}{b}$ is a part of a whole.\n\n$$x^2 + y^2 = z^2$$\n\n- numerator\n- denominator"],
      ["ky", "Бөлчөктөргө киришүү", "## Бөлчөк деген эмне\n\nБөлчөк $\\frac{a}{b}$ бүтүндүн бир бөлүгүн көрсөтөт.\n\n$$x^2 + y^2 = z^2$$\n\n- алымы\n- бөлүмү"],
    ]) {
      await api(md.teacher, "POST", `/courses/${cid}/pages`, { title, language: lang, body_md: body, published: true, translation_group_id: ruPage.translation_group_id });
    }
    const later = await api(md.teacher, "POST", `/courses/${cid}/pages`, { title: "Повторение", language: "ru", body_md: "Повторим всё.", published: true });
    const m4 = await api(md.teacher, "POST", `/courses/${cid}/modules`, {
      title: { ru: "Модуль 4. Повторение", ky: "4-модуль. Кайталоо", en: "Module 4. Review" }, published: true,
      unlock_at: new Date(Date.UTC(2026, 11, 15, 9, 0)).toISOString(),
    });
    await api(md.teacher, "POST", `/courses/${cid}/modules/${m4.id}/items`, { kind: "page", page_id: later.id, published: true, requirement: { type: "view" } });
    // a fifth module, open and untouched (the "unlocked" badge next to completed, in progress and locked)
    const extra = await api(md.teacher, "POST", `/courses/${cid}/pages`, { title: "Задачи для практики", language: "ru", body_md: "Решите задачи $1$–$5$.", published: true });
    const m5 = await api(md.teacher, "POST", `/courses/${cid}/modules`, {
      title: { ru: "Модуль 5. Практика", ky: "5-модуль. Практика", en: "Module 5. Practice" }, published: true,
    });
    await api(md.teacher, "POST", `/courses/${cid}/modules/${m5.id}/items`, { kind: "page", page_id: extra.id, published: true, requirement: { type: "view" } });
    // a second PDF in a folder, so the files list shows a group
    const form = new FormData();
    form.append("file", new Blob([PDF], { type: "application/pdf" }), "tasks.pdf");
    form.append("folder", "Задачи");
    form.append("title", "Задачи на дроби");
    form.append("published", "true");
    expect((await fetch(`${seed().api}/api/v1/courses/${cid}/course-files`, { method: "POST", headers: { Authorization: `Bearer ${md.teacher.token}` }, body: form })).status).toBe(201);
    await api(md.teacher, "POST", `/courses/${cid}/announcements`, { title: "Расписание на неделю", body_md: "Занятия по **вторникам** и четвергам.", pinned: true, publish: true });
    const quizAid = outline.modules.flatMap((m: { items: { target: { assessment_id?: string } | null }[] }) => m.items).find((i: { target: { assessment_id?: string } | null }) => i.target?.assessment_id)!.target.assessment_id;
    const empty = await api(md.teacher, "POST", "/courses", { title: { ru: "Пустой курс", ky: "Бош курс", en: "Empty course" }, languages: ["ru", "ky", "en"], default_language: "ru" });
    // 8a UX M1: a draft quiz with a requirement in M5: the outline warns, and publishing M5 asks first
    const draftQuiz = await api(md.teacher, "POST", `/courses/${cid}/modules/${m5.id}/quiz`, {
      kind: "quiz", title: { ru: "Черновик теста", ky: "Тест долбоору", en: "Draft quiz" }, quiz: { preset: "none", languages: ["ru"] },
    });
    await api(md.teacher, "PUT", `/courses/${cid}/modules/${m5.id}/items/${draftQuiz.item.id}/requirement`, { type: "min_percent", threshold: 80 });
    const m5Title = { ru: "Модуль 5. Практика", ky: "5-модуль. Практика", en: "Module 5. Practice" };

    const shoot = async (page: Page, name: string, vp: string, lang: string, full = true) => {
      await settle(page);
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(SCREENS!, `${name}-${vp}-${lang}.png`), fullPage: full, animations: "disabled", caret: "hide" });
    };

    for (const lang of ["ru", "ky", "en"] as const) {
      const tl = (key: string, vars: Record<string, string | number> = {}) => tr(lang, key, vars);
      for (const vp of ["phone", "desktop"] as const) {
        const ctx = await browser.newContext({ viewport: VIEWPORTS[vp], locale: lang === "en" ? "en-US" : "ru-RU", timezoneId: "UTC", colorScheme: "light" });
        const sp = await ctx.newPage();
        await signIn(sp, md.student);
        const base = `/${lang}/courses/${cid}`;
        await sp.goto(base);
        await expect(sp.getByRole("heading", { level: 2 }).first()).toBeVisible();
        await shoot(sp, "student-course-home-modules", vp, lang);
        await sp.goto(`${base}/pages/${ruPage.id}?from=module`);
        await expect(sp.locator(".katex").first()).toBeVisible();
        await shoot(sp, "student-page-math", vp, lang);
        await sp.goto(`${base}/pages/${later.id}`);
        await expect(sp.getByText(tl("pages.locked.title"))).toBeVisible();
        await shoot(sp, "student-page-locked", vp, lang);
        await sp.goto(`${base}/files`);
        await expect(sp.getByText(FILE_TITLE, { exact: true })).toBeVisible();
        await shoot(sp, "student-files", vp, lang);
        await sp.goto(`${base}/announcements`);
        await expect(sp.getByRole("heading", { name: ANN_TITLE })).toBeVisible();
        await shoot(sp, "student-announcements", vp, lang);
        await sp.goto(`/${lang}/courses`);
        await expect(sp.locator('section[aria-labelledby="home-next"]')).toBeVisible();
        await shoot(sp, "student-home-strip", vp, lang);
        // the quiz lobby inside a module that is locked (M3 is after M2; M2's quiz is open, so lock M2 by date briefly)
        await api(md.teacher, "PATCH", `/courses/${cid}/modules/${byRu(M2).id}`, { unlock_at: new Date(Date.UTC(2026, 11, 1, 9, 0)).toISOString() });
        await api(md.teacher, "POST", `/courses/${cid}/modules/${byRu(M2).id}/reapply`, {});
        await sp.goto(`${base}/assessments/${quizAid}`);
        await expect(sp.getByText(tl("pages.locked.title"))).toBeVisible();
        await shoot(sp, "student-quiz-lobby-locked", vp, lang);
        await api(md.teacher, "PATCH", `/courses/${cid}/modules/${byRu(M2).id}`, { unlock_at: null });
        // course home = page
        await api(md.teacher, "PATCH", `/courses/${cid}`, { home_kind: "page", home_page_id: ruPage.id });
        await sp.goto(base);
        await expect(sp.locator(".katex").first()).toBeVisible();
        await shoot(sp, "student-course-home-page", vp, lang);
        await api(md.teacher, "PATCH", `/courses/${cid}`, { home_kind: "modules", home_page_id: null });
        // course home = modules without published modules: today's layout (the quiz-editor course)
        const qctx = await browser.newContext({ viewport: VIEWPORTS[vp], locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
        const qp = await qctx.newPage();
        await signIn(qp, seed().quiz_editor.student);
        await qp.goto(`/${lang}/courses/${seed().quiz_editor.course_id}`);
        await expect(qp.getByRole("heading", { level: 1 })).toBeVisible();
        await shoot(qp, "student-course-home-fallback", vp, lang);
        await qctx.close();
        await ctx.close();

        if (lang === "ky") continue; // teacher screens in ru and en
        const tctx = await browser.newContext({ viewport: VIEWPORTS[vp], locale: lang === "en" ? "en-US" : "ru-RU", timezoneId: "UTC", colorScheme: "light" });
        const tp = await tctx.newPage();
        await signIn(tp, md.teacher);
        const card = (ruTitle: string) => tp.locator('[id^="m-"]').filter({ has: tp.getByRole("heading", { name: { [M1]: lang === "en" ? "Module 1. Getting started" : M1, [M2]: lang === "en" ? "Module 2. Check" : M2, [M3]: lang === "en" ? "Module 3. Summary" : M3 }[ruTitle]!, exact: true }) });
        await tp.goto(`/${lang}/courses/${empty.id}`);
        await expect(tp.getByText(tl("modules.editor.emptyTitle"))).toBeVisible();
        await shoot(tp, "teacher-outline-empty", vp, lang);
        await tp.goto(base);
        await expect(card(M1)).toBeVisible();
        const m5Card = tp.locator('[id^="m-"]').filter({ has: tp.getByRole("heading", { name: m5Title[lang], exact: true }) });
        await expect(m5Card.getByText(tl("modules.warnings.requirementIgnoredTitle"))).toBeVisible();
        await shoot(tp, "teacher-outline", vp, lang);
        // M1: unpublish M5, then switching it on asks first (cancel; published again through the API)
        await api(md.teacher, "PATCH", `/courses/${cid}/modules/${m5.id}`, { published: false });
        await tp.reload();
        await publishIcon(m5Card, m5Title[lang], lang === "en" ? "en" : "ru").click();
        await expect(tp.getByRole("alertdialog", { name: tl("modules.warnings.requirementIgnoredTitle") })).toBeVisible();
        await shoot(tp, "teacher-publish-warning", vp, lang, false);
        await tp.keyboard.press("Escape");
        await expect(tp.getByRole("alertdialog")).toHaveCount(0);
        await api(md.teacher, "PATCH", `/courses/${cid}/modules/${m5.id}`, { published: true });
        await tp.reload();
        await expect(card(M1)).toBeVisible();
        const dialogShot = async (name: string) => { await shoot(tp, name, vp, lang, false); await tp.keyboard.press("Escape"); await expect(tp.getByRole("dialog")).toHaveCount(0); };
        await card(M2).getByRole("button", { name: tl("modules.editor.actions") }).first().click();
        await tp.getByRole("menuitem", { name: tl("modules.editor.editSettings") }).click();
        await dialogShot("teacher-module-settings");
        await card(M3).getByRole("button", { name: tl("modules.editor.actions") }).first().click();
        await tp.getByRole("menuitem", { name: tl("modules.editor.prerequisites") }).click();
        await dialogShot("teacher-prerequisites");
        await card(M2).locator("li").filter({ hasText: QUIZ }).getByRole("button", { name: tl("modules.editor.actions") }).click();
        await tp.getByRole("menuitem", { name: tl("modules.editor.setRequirement") }).click();
        await dialogShot("teacher-requirement");
        await card(M1).getByRole("button", { name: tl("modules.editor.addItem") }).first().click();
        await tp.getByRole("menuitem", { name: tl("coursePage.addItems.page") }).click();
        await expect(tp.getByRole("dialog").getByRole("radio").first()).toBeVisible(); // the page list loaded
        await dialogShot("teacher-add-item");
        await tp.getByRole("button", { name: tl("modules.progress.open") }).click();
        const prog = tp.getByRole("dialog", { name: tl("modules.progress.title") });
        await prog.getByRole("combobox").selectOption({ index: 1 });
        await expect(prog.getByRole("heading", { level: 2 }).first()).toBeVisible();
        await dialogShot("teacher-progress");
        await tp.goto(`${base}/pages`);
        await expect(tp.getByText(PAGE_TITLE).filter({ visible: true }).first()).toBeVisible();
        await shoot(tp, "teacher-pages", vp, lang);
        await tp.goto(`${base}/pages/${ruPage.id}/edit`);
        await expect(tp.locator(".katex").first()).toBeVisible();
        await shoot(tp, "teacher-page-editor", vp, lang);
        await tp.goto(`${base}/files`);
        await expect(tp.getByText(FILE_TITLE, { exact: true })).toBeVisible();
        await shoot(tp, "teacher-files", vp, lang);
        await tp.getByRole("button", { name: tl("courseFiles.upload") }).first().click();
        await dialogShot("teacher-files-upload");
        await tp.goto(`${base}/announcements/new`);
        await tp.getByRole("textbox", { name: tl("announcements.fieldTitle") }).fill(lang === "en" ? "Test on Friday" : "Контрольная в пятницу");
        await tp.getByRole("textbox", { name: tl("announcements.fieldBody") }).fill(lang === "en" ? "Review **fractions** and $\\frac{3}{4} + \\frac{1}{4}$." : "Повторите **дроби** и $\\frac{3}{4} + \\frac{1}{4}$.");
        await expect(tp.locator(".katex").first()).toBeVisible();
        await shoot(tp, "teacher-announcement-compose", vp, lang);
        tp.on("dialog", (d) => void d.accept());
        await tp.goto(`${base}/announcements`);
        await expect(tp.getByRole("heading", { name: ANN_TITLE })).toBeVisible();
        await shoot(tp, "teacher-announcements", vp, lang);
        await tp.goto(`${base}/settings`);
        await tp.locator("form#course-home").scrollIntoViewIfNeeded();
        await shoot(tp, "teacher-settings-home", vp, lang, false);
        await tctx.close();
      }
    }
  });
});
