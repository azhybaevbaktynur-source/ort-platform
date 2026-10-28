import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser, type ViewportName } from "./helpers";

/**
 * Phase 8b S5: the exam-template constructor walk (PHASE_8B_DESIGN 11 "S5", 12, 12.1), end to end in the browser.
 * An org admin creates an organization template ("New template", scrolling starter) and designs it in the
 * constructor: forward-only navigation, two sections (single choice only, 10 min; six types with numbered reading
 * passages, 20 min), a system scheme with the live preview table, the ORT-style result page and lock scope
 * "sections"; every change autosaves (checked on the server). Sample tab: the sandbox gate, "preview not ready" while
 * the sections are empty, one sample question per section in the 7c card editor (the type dropdown offers only the
 * section's types), then "Preview as student" opens the real player in a new tab (amber preview banner, scrolling,
 * forward-only), finishes to the ORT-style result and "Back" (`?return=`) lands on the constructor's Sample tab.
 * Publish v1, edit the draft, diff v1 -> draft, the draft-conflict dialog ("take the saved version"), lock. The
 * teacher creates a quiz assignment from the template (template picker, locked structure line), fills both sections
 * in the card editor ("Add section" disabled, the server answers 409 `template_locked`) and publishes; two students
 * (desktop, 375 px phone) take it in scrolling mode and see the ORT-style result with the template's section names.
 * The owner unlocks and publishes v2 (diff v1 -> v2); the teacher's exam keeps v1 (two sections, 10 min). Finally the
 * org admin promotes the teacher's own template to the organization.
 *
 * Data: `seed_backend.py` (`seed_constructor`, after every other seed): organization "Школа E2E" (teachers may create
 * courses) with an org admin and an approved teacher member, the teacher's published course "Курс школы E2E" with two
 * students, and the teacher's published teacher-scope template "Шаблон учителя E2E".
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/exam-constructor.spec.ts
 * (in a git worktree add E2E_PYTHON=<main repo>/backend/venv/bin/python). With PHASE8B_SCREENS_DIR=<dir> the second
 * test writes the UX-gate screenshots (docs/phases/PHASE_8B_screens/, see INDEX.md "S5"); without it it is skipped.
 */

type L3 = "ru" | "ky" | "en";
const L: L3 = "ru";
const t = (key: string, vars: Record<string, string | number> = {}, lang: L3 = L) => tr(lang, key, vars);

interface CtorSeed {
  organization_id: string;
  course_id: string;
  join_code: string;
  org_admin: SeedUser;
  teacher: SeedUser;
  students: Record<"walk" | "phone", SeedUser>;
  teacher_template_id: string;
}
const cs = (): CtorSeed => (seed() as unknown as { exam_constructor: CtorSeed }).exam_constructor;

const SCREENS = process.env.PHASE8B_SCREENS_DIR ? path.resolve(process.env.PHASE8B_SCREENS_DIR) : null;

async function api(user: SeedUser, p: string, method = "GET", body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  return { status: r.status, json: text ? JSON.parse(text) : null };
}
async function apiOk(user: SeedUser, p: string, method = "GET", body?: unknown) {
  const r = await api(user, p, method, body);
  expect(r.status, `${method} ${p}: ${JSON.stringify(r.json)}`).toBeLessThan(300);
  return r.json;
}

async function userPage(browser: Browser, user: SeedUser, vp: ViewportName = "desktop", lang: L3 = L): Promise<Page> {
  const ctx = await browser.newContext({
    viewport: VIEWPORTS[vp], locale: lang === "en" ? "en-US" : lang === "ky" ? "ky-KG" : "ru-RU", timezoneId: "UTC", colorScheme: "light",
  });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function shot(page: Page, name: string, opts: { fullPage?: boolean; element?: Locator } = {}) {
  if (!SCREENS) return;
  await settle(page);
  fs.mkdirSync(SCREENS, { recursive: true });
  const file = path.join(SCREENS, `${name}.png`);
  const o = { animations: "disabled" as const, caret: "hide" as const, path: file };
  if (opts.element) await opts.element.screenshot(o);
  else await page.screenshot({ ...o, fullPage: !!opts.fullPage });
}

const tab = (page: Page, id: string) => page.getByRole("tab", { name: new RegExp(`^${t(`examTemplates.constructor.tabs.${id}`)}`) });
const saved = (page: Page) => expect(page.getByRole("status").filter({ hasText: t("examTemplates.constructor.saveState.saved") })).toBeVisible({ timeout: 20_000 });
/** Wait until the stored draft satisfies `pred` (autosave reached the server), then for the "Saved" status. */
async function draftWhere(page: Page, user: SeedUser, tid: string, pred: (spec: Record<string, any>) => boolean) {
  await expect.poll(async () => pred((await apiOk(user, `/exam-templates/${tid}`)).draft_spec ?? {}), { timeout: 20_000 }).toBe(true);
  await saved(page);
}
const sectionCard = (page: Page, i: number) => page.locator(`#tplf-sections-${i}`);
const stemField = (page: Page) => page.getByLabel(t("bank.editor.stem"));
const answerField = (page: Page, letter: string) => page.getByLabel(t("quizEditor.card.answerLabel", { letter }));
async function done(page: Page) {
  await page.getByRole("button", { name: t("quizEditor.card.done") }).click();
  await expect(stemField(page)).toHaveCount(0);
  await settle(page);
}
/** One single-choice card: two answers, the second one correct. */
async function writeCard(page: Page, scope: Locator, stem: string, wrong: string, right: string, typeOptions?: number) {
  await scope.getByRole("button", { name: t("quizEditor.card.addQuestion") }).last().click();
  await expect(stemField(page)).toBeVisible();
  // the type dropdown offers only the section's allowed types (7c rule)
  if (typeOptions !== undefined) await expect(page.getByRole("combobox", { name: t("bank.editor.type") }).locator("option")).toHaveCount(typeOptions);
  await stemField(page).fill(stem);
  await answerField(page, "A").fill(wrong);
  await answerField(page, "A").press("Enter");
  await expect(answerField(page, "B")).toBeFocused();
  await page.keyboard.type(right);
  await page.getByRole("radio", { name: t("quizEditor.card.markCorrect", { letter: "B" }) }).check();
  await done(page);
}

const TPL = "Вступительный тест E2E";
/** What the walk built, for the UX-gate screenshots that follow it (serial, same worker). */
const W: { tid?: string; aid?: string; resultPath?: string } = {};
/** A RegExp matching `s` literally (labels carry parentheses). */
const rx = (s: string, flags = "") => new RegExp(s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), flags);

test.describe("exam-template constructor walk (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("design, sample, preview, publish, diff, lock, exam, student, v2, promote", async ({ browser }) => {
    test.setTimeout(600_000);
    const c = cs();
    const admin = await userPage(browser, c.org_admin);
    const orgBase = `/${L}/org/${c.organization_id}/exam-templates`;

    // ---- the org admin creates an organization template (scrolling starter) from the list
    await admin.goto(orgBase);
    await admin.getByRole("button", { name: t("examTemplates.list.new") }).click();
    const create = admin.getByRole("dialog", { name: t("examTemplates.create.title") });
    await create.getByRole("textbox").first().fill(TPL);
    await create.getByRole("radio", { name: rx(t("examTemplates.blocks.displayModes.scrolling")) }).check();
    await create.getByRole("button", { name: t("examTemplates.create.submit") }).click();
    await admin.waitForURL(/\/exam-templates\/[0-9a-f-]{36}/);
    const tid = /\/exam-templates\/([0-9a-f-]{36})/.exec(admin.url())![1];
    W.tid = tid;
    await expect(admin.getByRole("heading", { name: TPL })).toBeVisible();

    // ---- Structure: forward-only navigation, section 1 (single choice only, 10 min), section 2 (passages, numbered, 20 min)
    await admin.getByRole("radio", { name: rx(t("assessments.navigation.section_forward_only")) }).check();
    const s1 = sectionCard(admin, 0);
    await s1.getByRole("textbox").first().fill("Часть 1");
    const types1 = s1.locator("#tplf-sections-0-allowed_types").getByRole("checkbox");
    const single = t("bank.types.single_choice.name");
    for (let i = 0; i < (await types1.count()); i++) {
      const box = types1.nth(i);
      const label = (await box.evaluate((el) => el.closest("label")?.textContent ?? "")).trim();
      if ((label === single) !== (await box.isChecked())) await box.click();
    }
    await s1.getByLabel(t("examTemplates.specForm.timeLimit")).fill("10");
    await admin.getByRole("button", { name: t("examTemplates.specForm.addSection") }).click();
    const s2 = sectionCard(admin, 1);
    await s2.getByRole("textbox").first().fill("Часть 2");
    await s2.getByLabel(t("examTemplates.specForm.timeLimit")).fill("20");
    await s2.getByRole("checkbox", { name: t("examTemplates.specForm.allowPassages") }).check();
    await s2.getByLabel(t("examTemplates.specForm.passageDisplay")).selectOption("numbered");
    await draftWhere(admin, c.org_admin, tid, (d) => d.sections?.[1]?.passage_display === "numbered" && d.sections?.[1]?.time_limit_s === 1200);

    // ---- Scoring: a system scheme with the live table, ORT-style result page
    await tab(admin, "scoring").click();
    const scheme = admin.getByLabel(t("examTemplates.editor.scheme"));
    const schemeOpts = await scheme.locator("optgroup option").evaluateAll((os) => os.map((o) => [(o as HTMLOptionElement).value, o.textContent ?? ""]));
    await scheme.selectOption(schemeOpts[0][0]);
    await expect(admin.getByRole("heading", { name: t("examTemplates.constructor.scoring.previewTitle") })).toBeVisible();
    await admin.getByRole("radio", { name: rx(t("examTemplates.blocks.resultViews.ort")) }).check();
    await draftWhere(admin, c.org_admin, tid, (d) => d.result_view === "ort" && !!d.scoring?.grading_scheme_version_id);

    // ---- Display: scrolling (from the starter), lock scope "sections"
    await tab(admin, "display").click();
    await expect(admin.getByRole("radio", { name: rx(t("examTemplates.blocks.displayModes.scrolling")) })).toBeChecked();
    await admin.getByRole("checkbox", { name: rx(t("examTemplates.specForm.lockKeys.sections")) }).check();
    await draftWhere(admin, c.org_admin, tid, (d) => (d.lock_scope ?? []).includes("sections"));

    // ---- Sample questions: the sandbox gate, then one question per section in the 7c card editor (types limited)
    await tab(admin, "sample").click();
    await admin.getByRole("button", { name: t("examTemplates.sandbox.create") }).click();
    const part1 = admin.locator("section[aria-label='Часть 1']");
    const part2 = admin.locator("section[aria-label='Часть 2']");
    await expect(part1).toBeVisible();
    await expect(part2).toBeVisible();
    // preview before any sample question: one amber "not ready" callout naming the sections, no player
    // (8b UX: no generic "could not load" title, no Retry, no second red list)
    const launch = admin.getByRole("button", { name: t("examTemplates.preview.launch") });
    const pagesBefore = admin.context().pages().length;
    await launch.click();
    const notReady = admin.getByRole("alert").filter({ hasText: t("examTemplates.errors.preview_not_ready") });
    await expect(notReady).toBeVisible();
    await expect(notReady).toContainText(t("examTemplates.preview.issueLine", { section: "Часть 1", text: t("examTemplates.preview.noQuestions") }));
    await expect(notReady).toContainText(t("examTemplates.preview.issueLine", { section: "Часть 2", text: t("examTemplates.preview.noQuestions") }));
    await expect(admin.getByText(t("ui.error.title"))).toHaveCount(0);
    await expect(admin.getByRole("button", { name: t("ui.retry") })).toHaveCount(0);
    await expect.poll(() => admin.context().pages().length).toBe(pagesBefore);

    await writeCard(admin, part1, "Сколько будет 2 + 2?", "3", "4", 1);
    await writeCard(admin, part2, "Столица Кыргызстана?", "Ош", "Бишкек", 6);

    // ---- Preview: the header "Preview" (8b UX: the same action as the Sample tab's launcher) opens the real player in
    // a new tab (desktop), amber banner, scrolling, forward-only, ORT-style result; "Back to the template" returns to
    // the constructor's Sample tab
    const headerPreview = admin.getByRole("button", { name: t("examTemplates.constructor.header.preview"), exact: true });
    const [player] = await Promise.all([admin.context().waitForEvent("page"), headerPreview.click()]);
    await player.waitForURL(/\/attempts\/[0-9a-f-]{36}\?return=/);
    await expect(player.getByText(t("player.previewBanner"))).toBeVisible();
    await expect(player.locator('section[id^="item-"]')).toHaveCount(1);
    await expect(player.getByRole("timer")).toBeVisible();
    await shot(player, "ctor-preview-player-desktop-ru");
    await player.locator('section[id^="item-"]').first().getByRole("radio").nth(1).click();
    await player.getByRole("button", { name: t("player.finishSection") }).first().click();
    await player.getByRole("dialog").getByRole("button", { name: t("player.sectionEnd.confirm") }).click();
    await expect(player.getByText("Столица Кыргызстана?")).toBeVisible();
    await player.locator('section[id^="item-"]').first().getByRole("radio").nth(1).click();
    await player.getByRole("button", { name: t("player.finishTest") }).first().click();
    await player.getByRole("dialog").getByRole("button", { name: t("player.submit.confirm") }).click();
    await player.waitForURL(/\/result/);
    await shot(player, "ctor-preview-result-desktop-ru", { fullPage: true });
    const back = player.getByRole("link", { name: t("examTemplates.preview.backToTemplate"), exact: true });
    await expect(back).toHaveAttribute("href", new RegExp(`/exam-templates/${tid}\\?tab=sample$`));
    await back.click();
    await player.waitForURL(new RegExp(`/exam-templates/${tid}\\?tab=sample$`));
    await expect(player.getByRole("button", { name: t("examTemplates.preview.launch") })).toBeVisible();
    await player.close();

    // ---- Publish v1
    await admin.getByRole("button", { name: t("examTemplates.publish.action") }).first().click();
    const pubDlg = admin.getByRole("alertdialog", { name: t("examTemplates.publish.title") }).or(admin.getByRole("dialog", { name: t("examTemplates.publish.title") }));
    await pubDlg.getByRole("button", { name: t("examTemplates.publish.action") }).click();
    await expect(pubDlg).toBeHidden();
    await expect.poll(async () => (await apiOk(c.org_admin, `/exam-templates/${tid}`)).current_version_no).toBe(1);

    // ---- edit the draft (section 1: 15 min; a third section), the diff v1 -> draft in the Versions tab
    await tab(admin, "structure").click();
    const card1 = sectionCard(admin, 0);
    if (!(await card1.getByLabel(t("examTemplates.specForm.timeLimit")).isVisible())) await card1.getByRole("button", { expanded: false }).first().click();
    await card1.getByLabel(t("examTemplates.specForm.timeLimit")).fill("15");
    await admin.getByRole("button", { name: t("examTemplates.specForm.addSection") }).click();
    await sectionCard(admin, 2).getByRole("textbox").first().fill("Часть 3");
    await sectionCard(admin, 2).getByLabel(t("examTemplates.specForm.timeLimit")).fill("5");
    await draftWhere(admin, c.org_admin, tid, (d) => d.sections?.length === 3 && d.sections?.[0]?.time_limit_s === 900 && d.sections?.[2]?.time_limit_s === 300);
    await tab(admin, "versions").click();
    await admin.getByRole("button", { name: t("examTemplates.diff.compareWithDraftN", { n: 1 }) }).click();
    const diff = admin.locator("#tpl-diff");
    await expect(diff).toBeVisible();
    await expect(diff).toContainText(t("examTemplates.diff.summary.sectionsAdded", { n: 1 }));
    await expect(diff).toContainText("Часть 3");

    // ---- the conflict dialog: someone else saves the draft meanwhile; "take theirs" reloads it
    const fresh = await apiOk(c.org_admin, `/exam-templates/${tid}`);
    await apiOk(c.org_admin, `/exam-templates/${tid}`, "PATCH", { draft_rev: fresh.draft_rev, title: { ru: TPL } });
    await tab(admin, "structure").click();
    await sectionCard(admin, 2).getByLabel(t("examTemplates.specForm.timeLimit")).fill("6");
    const conflict = admin.getByRole("alertdialog", { name: t("examTemplates.constructor.conflict.title") });
    await expect(conflict).toBeVisible({ timeout: 20_000 });
    await conflict.getByRole("button", { name: t("examTemplates.constructor.conflict.takeTheirs") }).click();
    await expect(conflict).toBeHidden();

    // ---- lock the template (More -> Lock -> reason dialog)
    await admin.getByRole("button", { name: t("examTemplates.editor.more") }).click();
    await admin.getByRole("menuitem", { name: rx(t("examTemplates.lock.action")) }).click();
    const lockDlg = admin.getByRole("dialog", { name: t("examTemplates.lock.title") }).or(admin.getByRole("alertdialog", { name: t("examTemplates.lock.title") }));
    // 8b UX: the effect lists the ticked lock-scope keys and says earlier assignments do not change
    await expect(lockDlg.getByRole("listitem")).toHaveText([t("examTemplates.specForm.lockKeys.sections")]);
    await expect(lockDlg).toContainText(t("examTemplates.lock.effectEarlier"));
    await lockDlg.getByRole("textbox").fill("Структура утверждена методсоветом");
    await lockDlg.getByRole("button", { name: t("examTemplates.lock.action") }).click();
    await expect(lockDlg).toBeHidden();
    await expect(admin.getByText(t("examTemplates.constructor.lockedOwner"))).toBeVisible();
    await shot(admin, "ctor-locked-desktop-ru");
    expect((await apiOk(c.org_admin, `/exam-templates/${tid}`)).locked).toBe(true);

    // ---- the teacher creates an exam from the template (a quiz assignment), fills it with the 7c editor, publishes
    const teacher = await userPage(browser, c.teacher);
    await teacher.goto(`/${L}/courses/${c.course_id}/assignments`);
    await teacher.getByRole("button", { name: t("assignments.list.create") }).first().click();
    const newA = teacher.getByRole("dialog", { name: t("assignments.create.title") });
    await newA.getByRole("radio", { name: rx(t("assignments.kinds.quiz")) }).check();
    await newA.getByRole("textbox").first().fill("Вступительный тест, 9 класс");
    await newA.getByLabel(t("examTemplates.picker.startFrom")).selectOption({ label: `${TPL} · ${t("examTemplates.versionShort", { n: 1 })}` });
    await expect(newA.getByText(t("examTemplates.picker.lockedLine"))).toBeVisible();
    await newA.getByRole("button", { name: t("assignments.create.submitQuiz") }).click();
    await teacher.waitForURL(/\/assessments\/[0-9a-f-]{36}\/edit/);
    const aid = /\/assessments\/([0-9a-f-]{36})/.exec(teacher.url())![1];
    W.aid = aid;
    await expect(teacher.getByText(t("examTemplates.lockedSections"))).toBeVisible();
    const sec = (name: string) => teacher.locator("section").filter({ has: teacher.getByRole("heading", { name }) });
    await writeCard(teacher, sec("Часть 1"), "Сколько будет 5 + 5?", "11", "10", 1);
    await writeCard(teacher, sec("Часть 1"), "Сколько будет 3 × 3?", "6", "9", 1);
    await writeCard(teacher, sec("Часть 2"), "Самая длинная река Кыргызстана?", "Чу", "Нарын", 6);
    // lock scope "sections" on a locked template: "Add section" is disabled and the server refuses it (409)
    await expect(teacher.getByRole("button", { name: t("assessments.section.add") })).toBeDisabled();
    const addSec = await api(c.teacher, `/courses/${c.course_id}/assessments/${aid}/sections`, "POST", { title: { ru: "Часть 4" } });
    expect(addSec.status).toBe(409);
    expect(addSec.json.error.code).toBe("template_locked");
    await teacher.getByRole("button", { name: t("quizEditor.publishBar.publish") }).click();
    await expect(teacher.getByText(t("assessments.status.published")).first()).toBeVisible();
    expect((await apiOk(c.teacher, `/courses/${c.course_id}/assessments/${aid}`)).status).toBe("published");

    // ---- students take it: scrolling, forward-only, then the ORT-style result (desktop, then a 375 px phone)
    for (const [who, vp] of [["walk", "desktop"], ["phone", "phone"]] as const) {
      const student = await userPage(browser, c.students[who], vp);
      await student.goto(`/${L}/courses/${c.course_id}/assessments/${aid}`);
      await student.getByRole("button", { name: t("assessments.lobby.start") }).click();
      await student.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);
      const items = student.locator('section[id^="item-"]');
      await expect(items).toHaveCount(2);
      await expect(student.getByText(t("player.previewBanner"))).toHaveCount(0);
      for (const n of [0, 1]) await items.nth(n).getByRole("radio").nth(1).click();
      if (vp === "phone") expect(await student.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
      await student.getByRole("button", { name: t("player.finishSection") }).first().click();
      await student.getByRole("dialog").getByRole("button", { name: t("player.sectionEnd.confirm") }).click();
      await expect(student.getByText("Самая длинная река Кыргызстана?")).toBeVisible();
      await expect(items).toHaveCount(1);
      await items.first().getByRole("radio").nth(1).click();
      await student.getByRole("button", { name: t("player.finishTest") }).first().click();
      await student.getByRole("dialog").getByRole("button", { name: t("player.submit.confirm") }).click();
      await student.waitForURL(/\/result/);
      // ORT-style result of a general quiz: scaled grade and the template's own section names
      await expect(student.getByText(t("results.grade.sectionsTitle"))).toBeVisible();
      await expect(student.getByRole("cell", { name: "Часть 1" })).toBeVisible();
      if (who === "walk") W.resultPath = new URL(student.url()).pathname.replace(/^\/[a-z]{2}\//, "/");
      await student.context().close();
    }

    // ---- v2: the owner unlocks, publishes the edited draft; the exam keeps v1 and its two sections
    await admin.getByRole("button", { name: t("examTemplates.editor.more") }).click();
    await admin.getByRole("menuitem", { name: rx(t("examTemplates.unlock.action")) }).click();
    const unlockDlg = admin.getByRole("dialog", { name: t("examTemplates.unlock.title") }).or(admin.getByRole("alertdialog", { name: t("examTemplates.unlock.title") }));
    await unlockDlg.getByRole("button", { name: t("examTemplates.unlock.action") }).click();
    await expect(unlockDlg).toBeHidden();
    await admin.getByRole("button", { name: t("examTemplates.publish.action") }).first().click();
    await pubDlg.getByRole("button", { name: t("examTemplates.publish.action") }).click();
    await expect(pubDlg).toBeHidden();
    await expect.poll(async () => (await apiOk(c.org_admin, `/exam-templates/${tid}`)).current_version_no).toBe(2);
    await tab(admin, "versions").click();
    await admin.getByRole("button", { name: t("examTemplates.diff.compareWithPreviousN", { n: 2 }) }).click();
    await expect(admin.locator("#tpl-diff")).toContainText("Часть 3");
    const after = await apiOk(c.teacher, `/courses/${c.course_id}/assessments/${aid}`);
    expect(after.exam_template).toMatchObject({ template_id: tid, version_no: 1, latest_version_no: 2 });
    expect(after.current_version_no).toBe(1);
    expect(after.sections).toHaveLength(2);
    expect(after.sections[0].time_limit_s).toBe(600); // v1's 10 minutes, not the draft's 15
    expect(after).toMatchObject({ display_mode: "scrolling", result_view: "ort", navigation: "section_forward_only", structure_locked: true });

    // ---- promote: the org admin turns the teacher's own template into an organization template
    await admin.goto(`${orgBase}/${c.teacher_template_id}`);
    await admin.getByRole("button", { name: t("examTemplates.editor.more") }).click();
    await admin.getByRole("menuitem", { name: rx(t("examTemplates.promote.action")) }).click();
    const promDlg = admin.getByRole("dialog", { name: t("examTemplates.promote.title") }).or(admin.getByRole("alertdialog", { name: t("examTemplates.promote.title") }));
    await promDlg.getByRole("button", { name: t("examTemplates.promote.action") }).click();
    await expect(promDlg).toBeHidden();
    await expect.poll(async () => (await apiOk(c.org_admin, `/exam-templates/${c.teacher_template_id}`)).owner_scope).toBe("organization");
    await admin.context().close();
    await teacher.context().close();
  });

  test("UX-gate screenshots", async ({ browser }) => {
    test.skip(!SCREENS || !W.tid || !W.aid || !W.resultPath, "PHASE8B_SCREENS_DIR unset or the walk did not finish");
    test.setTimeout(900_000);
    const c = cs();
    const oid = c.organization_id;
    // a second teacher template, only for the promote dialog (opened and cancelled)
    const t2 = await apiOk(c.teacher, "/exam-templates", "POST", {
      owner_scope: "teacher", organization_id: oid, title: { ru: "Шаблон учителя 2", en: "Teacher template 2" },
      draft_spec: { schema: 1, parameters: [], lock_scope: [], sections: [{ key: null, title: { ru: "Часть 1" }, allowed_types: ["single_choice"] }] },
    });
    await apiOk(c.teacher, `/exam-templates/${t2.id}/publish`, "POST", {});

    for (const lang of ["ru", "en"] as const) {
      const tl = (k: string, v: Record<string, string | number> = {}) => t(k, v, lang);
      const tabL = (page: Page, id: string) => page.getByRole("tab", { name: new RegExp(`^${tl(`examTemplates.constructor.tabs.${id}`)}`) });
      const dialog = (page: Page, title: string) => page.getByRole("dialog", { name: title }).or(page.getByRole("alertdialog", { name: title }));
      for (const vp of ["desktop", "phone"] as const) {
        const sfx = `${vp}-${lang}`;
        const top = async (page: Page) => { await page.evaluate(() => window.scrollTo(0, 0)); };
        const admin = await userPage(browser, c.org_admin, vp, lang);
        const base = `/${lang}/org/${oid}/exam-templates`;

        // list (org area: organization and teacher templates, scope badges)
        await admin.goto(base);
        await expect(admin.getByRole("link", { name: TPL }).first()).toBeVisible();
        await shot(admin, `ctor-list-${sfx}`);

        // the walk's template (v2, unlocked): every tab
        await admin.goto(`${base}/${W.tid}`);
        await expect(admin.getByRole("heading", { name: TPL })).toBeVisible();
        await shot(admin, `ctor-structure-${sfx}`);
        await sectionCard(admin, 1).getByRole("button", { expanded: false }).first().click();
        await sectionCard(admin, 1).scrollIntoViewIfNeeded();
        await admin.evaluate(() => window.scrollBy(0, -80));
        await shot(admin, `ctor-section-${sfx}`);
        await top(admin);
        await tabL(admin, "scoring").click();
        await admin.getByRole("heading", { name: tl("examTemplates.constructor.scoring.previewTitle") }).scrollIntoViewIfNeeded();
        await expect(admin.locator("table").first()).toBeVisible();
        await shot(admin, `ctor-scoring-${sfx}`);
        await top(admin);
        await tabL(admin, "display").click();
        await shot(admin, `ctor-display-${sfx}`);
        await admin.locator("#tplf-lock_scope").scrollIntoViewIfNeeded();
        await shot(admin, `ctor-lockscope-${sfx}`);
        await top(admin);
        await tabL(admin, "sample").click();
        await expect(admin.getByRole("button", { name: tl("examTemplates.preview.launch") })).toBeVisible();
        await expect(admin.getByText("Сколько будет 2 + 2?")).toBeVisible();
        await shot(admin, `ctor-sample-${sfx}`);
        await top(admin);
        await tabL(admin, "versions").click();
        await admin.getByRole("button", { name: tl("examTemplates.diff.compareWithPreviousN", { n: 2 }) }).click();
        await expect(admin.locator("#tpl-diff")).toContainText("Часть 3");
        await admin.locator("#tpl-diff").scrollIntoViewIfNeeded();
        await shot(admin, `ctor-diff-${sfx}`, { element: admin.locator("#tpl-diff") });
        await top(admin);
        await admin.getByRole("button", { name: tl("examTemplates.editor.more") }).click();
        await admin.getByRole("menuitem", { name: rx(tl("examTemplates.lock.action")) }).click();
        const lockDlg = dialog(admin, tl("examTemplates.lock.title"));
        await expect(lockDlg).toBeVisible();
        await shot(admin, `ctor-lock-dialog-${sfx}`);
        await lockDlg.getByRole("button", { name: tl("ui.cancel") }).click();

        // a fresh template: Sample-tab gate, "not ready" preview, publish dialog, conflict dialog, validation issues
        const fresh = await apiOk(c.org_admin, "/exam-templates", "POST", {
          owner_scope: "organization", organization_id: oid, title: { ru: "Новый шаблон E2E", en: "New template E2E" },
          draft_spec: { schema: 1, display_mode: "scrolling", parameters: [], lock_scope: [], sections: [
            { key: null, title: { ru: "Часть 1", en: "Part 1" }, allowed_types: ["single_choice"] },
            { key: null, title: { ru: "Часть 2", en: "Part 2" }, allowed_types: ["single_choice", "true_false"] }] },
        });
        await admin.goto(`${base}/${fresh.id}?tab=sample`);
        const gate = admin.getByRole("button", { name: tl("examTemplates.sandbox.create") });
        await expect(gate).toBeVisible();
        await shot(admin, `ctor-sample-gate-${sfx}`);
        await gate.click();
        await admin.getByRole("button", { name: tl("examTemplates.preview.launch") }).click();
        await expect(admin.getByText(tl("examTemplates.errors.preview_not_ready"))).toBeVisible();
        await shot(admin, `ctor-preview-not-ready-${sfx}`);
        await top(admin);
        await tabL(admin, "structure").click();
        await admin.getByRole("button", { name: tl("examTemplates.publish.action") }).first().click();
        const pubDlg = dialog(admin, tl("examTemplates.publish.title"));
        await expect(pubDlg).toBeVisible();
        await shot(admin, `ctor-publish-dialog-${sfx}`);
        await pubDlg.getByRole("button", { name: tl("ui.cancel") }).click();
        const cur = await apiOk(c.org_admin, `/exam-templates/${fresh.id}`);
        await apiOk(c.org_admin, `/exam-templates/${fresh.id}`, "PATCH", { draft_rev: cur.draft_rev, title: cur.title });
        await admin.locator("textarea").first().fill(lang === "ru" ? "Пробный тест для 9 классов" : "Practice test for grade 9");
        const conflict = admin.getByRole("alertdialog", { name: tl("examTemplates.constructor.conflict.title") });
        await expect(conflict).toBeVisible({ timeout: 20_000 });
        await shot(admin, `ctor-conflict-${sfx}`);
        await conflict.getByRole("button", { name: tl("examTemplates.constructor.conflict.takeTheirs") }).click();
        await expect(conflict).toBeHidden();
        await sectionCard(admin, 0).getByRole("button", { expanded: false }).first().click();
        await sectionCard(admin, 0).locator("#tplf-sections-0-allowed_types").getByRole("checkbox", { checked: true }).first().uncheck();
        await expect(admin.getByRole("status").filter({ hasText: rx(tl("examTemplates.constructor.saveState.invalid_one", { n: 1 }).split(":")[0]) })).toBeVisible({ timeout: 20_000 });
        await top(admin);
        await shot(admin, `ctor-issues-${sfx}`);

        // promote dialog (org admin, a teacher's template; cancelled)
        await admin.goto(`${base}/${t2.id}`);
        await admin.getByRole("button", { name: tl("examTemplates.editor.more") }).click();
        await admin.getByRole("menuitem", { name: rx(tl("examTemplates.promote.action")) }).click();
        await expect(dialog(admin, tl("examTemplates.promote.title"))).toBeVisible();
        await shot(admin, `ctor-promote-dialog-${sfx}`);
        await admin.context().close();

        // teacher: "Create from template" (a quiz assignment with the template picker) and the exam's card editor
        const teacher = await userPage(browser, c.teacher, vp, lang);
        await teacher.goto(`/${lang}/courses/${c.course_id}/assignments`);
        await teacher.getByRole("button", { name: tl("assignments.list.create") }).first().click();
        const newA = teacher.getByRole("dialog", { name: tl("assignments.create.title") });
        await newA.getByRole("radio", { name: rx(tl("assignments.kinds.quiz")) }).check();
        await newA.getByRole("textbox").first().fill(lang === "ru" ? "Вступительный тест, 10 класс" : "Entrance test, grade 10");
        await newA.getByLabel(tl("examTemplates.picker.startFrom")).selectOption({ label: `${TPL} · ${tl("examTemplates.versionShort", { n: 2 })}` });
        await expect(newA.getByText(rx(tl("examTemplates.picker.sections", { n: 3 })))).toBeVisible();
        await shot(teacher, `teacher-create-from-template-${sfx}`);
        await newA.getByRole("button", { name: tl("ui.cancel") }).click();
        await teacher.goto(`/${lang}/courses/${c.course_id}/assessments/${W.aid}/edit`);
        await expect(teacher.getByText(tl("examTemplates.lockedSections"))).toBeVisible();
        await shot(teacher, `teacher-template-exam-${sfx}`);
        await teacher.context().close();
      }
    }

    // student: the ORT-style result page of the template exam (general quiz), every language
    for (const lang of ["ru", "ky", "en"] as const) {
      for (const vp of ["desktop", "phone"] as const) {
        const student = await userPage(browser, c.students.walk, vp, lang);
        await student.goto(`/${lang}${W.resultPath}`);
        await expect(student.getByText(t("results.grade.sectionsTitle", {}, lang))).toBeVisible();
        await shot(student, `tpl-result-ort-${vp}-${lang}`, { fullPage: vp === "desktop" });
        await student.context().close();
      }
    }
  });
});
