import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { expect, test, type Browser, type Locator, type Page, type Request } from "@playwright/test";
import { api, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * TEACHER_TO_STUDENT_MAP S5 (docs/phases/TEACHER_TO_STUDENT_MAP.md §1, §3; owner 2026-11-08: "create a lesson course
 * with 2 modules (video, page, file, test), publish, check every student page"). The platform admin builds the seeded
 * lesson course "Мастеркласс E2E" (`seed.item3`, a draft of the platform organization) in the browser: cover, publish,
 * the exam link (Settings → Доступ и Pro), module "Математика I" (video, page, PDF file, test) and module "Аналогии"
 * (video, page) behind the Pro lock, the test made free on Admin → Pro → Тесты, an announcement, and at the end one
 * lesson unpublished. The student of ORT (Russian) only (`seed.item3.student`, no pass) checks each step: the УРОКИ
 * sidebar row and the home «Уроки» section (catalog landing until joined), the landing and the one-tap join, the
 * overview (cover banner, «Начать курс», «Пройдено 0 из 6», two modules, the Pro chip, no address of a Pro lesson in
 * the page), the home «Продолжить урок» strip (after the overview was opened once), the lesson page (outline aside, the
 * click-to-load player: no request to YouTube before the tap, the view recorded on the tap, «Следующий урок»), the
 * page lesson inline, the file lesson's download card, the module test's lobby in the exam shell, the Pro lesson
 * locked, the exam's Тесты page without the lesson course's test (D6), the announcement on the home and its list with
 * the student page header (G2), and the unpublished lesson gone with the totals recounted. 375 px: no horizontal
 * scroll on each student page. Cleanup deletes the lesson course (no other spec sees it).
 *
 * With ITEM3_SHOTS=<dir> (docs/phases/STAFF_FEEDBACK_screens/item3/): one pair per teacher action, the map's shot names:
 * `<nn>-<slug>-teacher-1440-ru.png`, `<nn>-<slug>-student-1440-ru.png` and `-student-375-ru.png`.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.ITEM3_SHOTS ? path.resolve(process.env.ITEM3_SHOTS) : null;

const COURSE = "Мастеркласс E2E";
const M1 = "Математика I";
const M2 = "Аналогии";
const YT = "dQw4w9WgXcQ";
const PRO_YT = "M7lc1UVf-VE";
const V1 = "Сравнение величин: видео";
const PG1 = "Сравнение величин: конспект";
const PG1_TEXT = "Конспект урока про сравнение величин E2E";
const FILE = "Сравнение величин: задачи";
const QUIZ = "Тест: сравнение величин";
const V2 = "Аналогии: видео";
const PG2 = "Аналогии: конспект";
const ANN = "Новый урок в мастерклассе E2E";
const THIRD_PARTY = /youtube|youtu\.be|ytimg|googlevideo|vimeo|vimeocdn/i;
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

// ---------------------------------------------------------------- a small PNG for the cover (same as course-cover.spec)
const CRC = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const b of buf) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}
function png(w: number, h: number): Buffer {
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y += 1) {
    const row = y * (w * 3 + 1);
    for (let x = 0; x < w; x += 1) {
      const f = x / (w - 1);
      raw[row + 1 + x * 3] = Math.round(14 + 20 * f);
      raw[row + 2 + x * 3] = Math.round(120 + 60 * f);
      raw[row + 3 + x * 3] = Math.round(200 - 40 * f);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ---------------------------------------------------------------- pages, shots

async function open(browser: Browser, user: SeedUser): Promise<Page> {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light", acceptDownloads: true });
  // the providers are stubbed: nothing leaves the machine; the student test proves nothing is asked before the tap
  await ctx.route(THIRD_PARTY, (route) => route.fulfill({
    status: 200, contentType: "text/html",
    body: "<!doctype html><html><body style=\"margin:0;background:#000;color:#fff;font:16px sans-serif;display:flex;align-items:center;justify-content:center;height:100vh\">player</body></html>",
  }));
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

const hideToasts = (page: Page, v: string) => page.evaluate((vis) => document.querySelectorAll<HTMLElement>('div[aria-live="polite"].fixed')
  .forEach((e) => { e.style.visibility = vis; }), v);

async function snap(page: Page, file: string, opts: { fullPage?: boolean; element?: Locator } = {}) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await settle(page);
  await hideToasts(page, "hidden");
  const o = { path: path.join(SHOTS, file), animations: "disabled" as const, caret: "hide" as const };
  if (opts.element) await opts.element.screenshot(o);
  else await page.screenshot({ ...o, fullPage: opts.fullPage !== false });
  await hideToasts(page, "");
}

/** The teacher half of a pair (1440 px; `fullPage: false` keeps an open dialog in view). */
async function teacherShot(page: Page, slug: string, opts: { fullPage?: boolean; element?: Locator } = {}) {
  await snap(page, `${slug}-teacher-1440-ru.png`, opts);
}

/** The student half: 1440 and 375 px, no horizontal scroll at 375 (checked with or without shots). */
async function studentShot(page: Page, slug: string, element?: () => Locator) {
  await settle(page);
  await snap(page, `${slug}-student-1440-ru.png`, { element: element?.() });
  await page.setViewportSize(VIEWPORTS.phone);
  await settle(page);
  await noHorizontalScroll(page);
  await snap(page, `${slug}-student-375-ru.png`, { element: element?.() });
  await page.setViewportSize(VIEWPORTS.desktop);
  await settle(page);
}

// ---------------------------------------------------------------- the teacher's module editor (FB8 S2)

const tCard = (page: Page, title: string) =>
  page.locator('[id^="m-"]').filter({ has: page.getByRole("heading", { name: title, exact: true }) }).first();

async function createModule(page: Page, title: string) {
  await page.getByRole("button", { name: t("modules.editor.newModule") }).first().click();
  const input = page.getByRole("textbox", { name: t("modules.settings.titleLabel") });
  await input.fill(title);
  await input.press("Enter");
  await expect(tCard(page, title)).toBeVisible();
  await expect(input).toHaveCount(0);
}

async function addVia(page: Page, module: string, label: string) {
  await tCard(page, module).getByRole("button", { name: t("coursePage.add", { title: module }) }).first().click();
  await page.getByRole("menu").getByRole("menuitem", { name: label, exact: true }).click();
}

async function addVideo(page: Page, module: string, url: string, title: string, minutes: number, shot?: string) {
  await addVia(page, module, t("modules.editor.addVideo"));
  const dlg = page.getByRole("dialog", { name: t("modules.editor.video.title") });
  await dlg.getByLabel(t("modules.editor.video.url")).fill(url);
  await expect(dlg.getByText(t("modules.editor.video.detected", { provider: "YouTube" }))).toBeVisible();
  await dlg.getByLabel(t("modules.editor.video.name")).fill(title);
  await dlg.getByLabel(t("modules.editor.video.minutes")).fill(String(minutes));
  if (shot) await teacherShot(page, shot, { fullPage: false });
  await dlg.getByRole("button", { name: t("modules.add.submit") }).click();
  await expect(dlg).toHaveCount(0);
  await expect(tCard(page, module)).toContainText(title);
}

/** "+ Добавить → Страница" (a draft page placed in the module), its minutes, then the page editor: text, published. */
async function addPage(page: Page, base: string, module: string, title: string, text: string, minutes: number, shot?: string) {
  const created = page.waitForResponse((r) => r.request().method() === "POST" && /\/api\/v1\/courses\/[0-9a-f-]{36}\/pages$/.test(r.url()));
  await addVia(page, module, t("coursePage.addItems.page"));
  const input = tCard(page, module).getByRole("textbox", { name: t("coursePage.inlineTitle", { kind: t("coursePage.addItems.page") }) });
  await input.fill(title);
  await input.press("Enter");
  const pageId = (await (await created).json()).id as string;
  const card = tCard(page, module);
  await card.getByRole("button", { name: t("modules.editor.durationSet", { title }) }).click();
  const field = card.getByRole("spinbutton", { name: t("modules.editor.durationField", { title }) });
  await field.fill(String(minutes));
  await field.press("Enter");
  await expect(card.getByRole("button", { name: t("modules.editor.durationEdit", { title, value: t("modules.editor.minutes", { n: minutes }) }) })).toBeVisible();
  await page.goto(`${base}/pages/${pageId}?tab=edit`);
  await page.getByRole("textbox", { name: t("pages.editor.fieldBody") }).fill(text);
  const published = page.getByRole("switch", { name: t("pages.editor.fieldPublished") });
  await published.click();
  await expect(published).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: t("common.save") }).first().click();
  await expect(page.getByRole("button", { name: t("common.save") }).first()).toBeDisabled();
  if (shot) await teacherShot(page, shot);
  await page.goto(base);
  await expect(tCard(page, module)).toBeVisible();
  return pageId;
}

/** The module's publish switch (`aria-checked` = published), and the server stored it. */
async function publishModule(page: Page, admin: SeedUser, cid: string, module: string, on = true) {
  const sw = tCard(page, module).getByRole("switch", { name: t("modules.editor.publishToggle", { title: module }), exact: true });
  await sw.click();
  await expect(sw).toHaveAttribute("aria-checked", String(on));
  await expect.poll(async () => (await api(admin, "GET", `/courses/${cid}/modules`)).modules
    .find((m: { title: Record<string, string> }) => m.title.ru === module)?.published).toBe(on);
}

interface StudentItem { id: string; done?: boolean }
interface StudentModule { id: string; items: StudentItem[] }
interface StaffModule { id: string; title: Record<string, string>; items: { id: string; kind: string; position: number }[] }

test.describe("teacher builds a lesson course, the student sees each step (ru)", () => {
  test("cover, publish, exam link, two modules (video, page, file, test; Pro), announcement, unpublish", async ({ browser }) => {
    test.setTimeout(420_000);
    const s = seed();
    const { lesson_course_id: lc, exam_course_id: exam, student } = s.item3;
    const admin = s.admin;
    const base = `/${L}/courses/${lc}`;
    const tp = await open(browser, admin);
    const sp = await open(browser, student);
    const thirdParty: string[] = [];
    sp.context().on("request", (r: Request) => { if (THIRD_PARTY.test(new URL(r.url()).hostname)) thirdParty.push(r.url()); });
    const nav = sp.getByRole("navigation", { name: t("student.nav.label") }).first();
    const homeLessons = sp.locator('section[aria-labelledby="home-lesson-courses"]');
    try {
      // ---- 01 the course exists (a draft, no link): nothing for the student yet
      await tp.goto(base);
      await expect(tp.getByRole("heading", { level: 1, name: COURSE })).toBeVisible();
      await expect(tp.getByText(t("modules.editor.emptyTitle"))).toBeVisible();
      await teacherShot(tp, "01-create-course");
      await sp.goto(`/${L}/courses`);
      await expect(sp.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(nav.getByRole("link", { name: t("student.nav.tests"), exact: true })).toBeVisible();
      await expect(nav.getByRole("link", { name: COURSE })).toHaveCount(0);
      await expect(homeLessons).toHaveCount(0);
      await expect(sp.locator("main#main").getByText(COURSE)).toHaveCount(0);
      await studentShot(sp, "01-create-course");

      // ---- 18 cover (Settings → Обложка)
      await tp.goto(`${base}/settings?section=cover`);
      const cover = tp.getByTestId("course-cover-section");
      await cover.getByTestId("cover-file").setInputFiles({ name: "cover.png", mimeType: "image/png", buffer: png(960, 540) });
      await cover.getByRole("button", { name: t("courses.cover.save") }).click();
      await expect(cover.getByRole("status")).toHaveText(t("courses.cover.savedMsg"));
      await teacherShot(tp, "18-cover");
      const coverUrl = (await api(admin, "GET", `/courses/${lc}`)).cover_url as string;
      expect(coverUrl).toMatch(/\.webp$/);

      // ---- 02 publish and link to the exam (Settings → Доступ и Pro)
      await tp.goto(`${base}/settings?section=access`);
      await tp.getByRole("button", { name: t("courses.settings.publish") }).click();
      await expect(tp.getByRole("button", { name: t("courses.settings.publish") })).toHaveCount(0);
      const select = tp.getByLabel(t("courses.settings.examLink.label"));
      await expect(select).toBeEnabled();
      await select.selectOption(exam);
      await select.locator("xpath=ancestor::div[contains(@class,'space-y-2')][1]").getByRole("button", { name: t("common.save") }).click();
      await expect.poll(async () => (await api(admin, "GET", `/courses/${lc}`)).exam_course_id).toBe(exam);
      await teacherShot(tp, "02-publish-course");
      // the student: a УРОКИ row and a «Уроки» card, both to the catalog landing (not joined: no ring, no strip)
      await sp.goto(`/${L}/courses`);
      await expect(nav.getByRole("link", { name: COURSE })).toHaveAttribute("href", `/${L}/courses/catalog/${lc}`);
      await expect(homeLessons.getByRole("link", { name: COURSE })).toHaveAttribute("href", `/${L}/courses/catalog/${lc}`);
      for (const other of ['section[aria-labelledby="home-platform"]', 'section[aria-labelledby="home-other-courses"]']) {
        await expect(sp.locator(other).getByText(COURSE)).toHaveCount(0);
      }
      await expect(sp.locator('section[aria-labelledby="home-continue"]')).toHaveCount(0);
      await studentShot(sp, "02-publish-course");

      // ---- 06 + 07 + 08 + 09 + 11 + 16: two modules through the "+ Добавить" menu
      await tp.goto(base);
      await createModule(tp, M1);
      await createModule(tp, M2);
      await addVideo(tp, M1, `https://www.youtube.com/watch?v=${YT}`, V1, 6, "07-video");
      await addPage(tp, base, M1, PG1, PG1_TEXT, 10, "08-page");
      // the file: "+ Добавить → Файл" → upload a PDF (published), it goes straight into the module
      await addVia(tp, M1, t("coursePage.addItems.file"));
      const pick = tp.getByRole("dialog", { name: t("modules.add.title") });
      await pick.getByRole("button", { name: t("modules.add.uploadFile") }).click();
      const up = tp.getByRole("dialog", { name: t("courseFiles.uploadTitle") });
      await up.locator("input[type=file]").setInputFiles({ name: "zadachi.pdf", mimeType: "application/pdf", buffer: PDF });
      await up.getByRole("textbox", { name: t("courseFiles.fieldTitle") }).fill(FILE);
      await teacherShot(tp, "09-file", { fullPage: false });
      await up.getByRole("button", { name: t("courseFiles.upload") }).click();
      await expect(up).toHaveCount(0);
      await expect(pick).toHaveCount(0);
      await expect(tCard(tp, M1)).toContainText(FILE);
      // the test: "+ Добавить → Тест" creates the quiz and its row; one question in the quiz editor, published
      const quizResp = tp.waitForResponse((r) => r.request().method() === "POST" && /\/modules\/[0-9a-f-]{36}\/quiz$/.test(r.url()));
      await addVia(tp, M1, t("coursePage.addItems.quiz"));
      const quizTitle = tCard(tp, M1).getByRole("textbox", { name: t("coursePage.inlineTitle", { kind: t("coursePage.addItems.quiz") }) });
      await quizTitle.fill(QUIZ);
      await quizTitle.press("Enter");
      const aid = (await (await quizResp).json()).assessment_id as string;
      await tCard(tp, M1).getByRole("link", { name: QUIZ, exact: true }).click();
      await tp.waitForURL(new RegExp(`/assessments/${aid}/edit`));
      await tp.getByRole("button", { name: t("quizEditor.card.addQuestion") }).last().click();
      await tp.getByLabel(t("bank.editor.stem")).fill("Что больше: 3/4 или 2/3?");
      await tp.getByLabel(t("quizEditor.card.answerLabel", { letter: "A" })).fill("2/3");
      await tp.getByLabel(t("quizEditor.card.answerLabel", { letter: "A" })).press("Enter");
      await tp.keyboard.type("3/4");
      await tp.getByRole("radio", { name: t("quizEditor.card.markCorrect", { letter: "B" }) }).check();
      await tp.getByRole("button", { name: t("quizEditor.card.done") }).click();
      await expect(tp.getByLabel(t("bank.editor.stem"))).toHaveCount(0);
      await settle(tp);
      await tp.getByRole("button", { name: t("quizEditor.publishBar.publish") }).click();
      await expect(tp.getByText(t("assessments.status.published")).first()).toBeVisible();
      await teacherShot(tp, "11-module-test");
      // 15: a new test of a platform course starts Pro (S3 access); Admin → Pro → Тесты makes this one free
      await tp.goto(`/${L}/admin/access/exams`);
      await tp.getByLabel(t("access.admin.exams.course")).selectOption(lc);
      const paid = tp.getByRole("switch", { name: t("access.admin.exams.paidToggle", { title: QUIZ }) });
      await expect(paid).toBeChecked();
      await paid.click();
      await expect(paid).not.toBeChecked();
      await expect.poll(async () => (await api(admin, "GET", `/platform/access/exams?course_id=${lc}`)).items
        .find((e: { id: string }) => e.id === aid)?.access_tier).toBe("free");
      await teacherShot(tp, "15-pro-test");
      // module 2: a video and a page, behind the Pro lock (asks first, turns gold)
      await tp.goto(base);
      await addVideo(tp, M2, `https://youtu.be/${PRO_YT}`, V2, 7);
      await addPage(tp, base, M2, PG2, "Конспект Pro E2E", 4);
      const lock = tCard(tp, M2).getByRole("button", { name: t("modules.editor.proSwitch", { title: M2 }) });
      await lock.click();
      await tp.getByRole("alertdialog", { name: t("modules.editor.proConfirmTitle") }).getByRole("button", { name: t("modules.editor.proConfirm") }).click();
      await expect(lock).toHaveAttribute("aria-pressed", "true");
      await publishModule(tp, admin, lc, M1);
      await publishModule(tp, admin, lc, M2);
      await teacherShot(tp, "16-pro-module", { element: tCard(tp, M2) });
      await teacherShot(tp, "06-module");
      const mods = (await api(admin, "GET", `/courses/${lc}/modules`)).modules as StaffModule[];
      for (const m of mods) m.items.sort((a, b) => a.position - b.position);
      const m1 = mods.find((m) => m.title.ru === M1)!;
      const m2 = mods.find((m) => m.title.ru === M2)!;
      expect(m1.items.map((i) => i.kind)).toEqual(["url", "page", "file", "assignment"]);

      // ---- the student: the УРОКИ row → the landing (18: the cover) → one-tap join → the overview (06)
      await sp.goto(`/${L}/courses`);
      await nav.getByRole("link", { name: COURSE }).click();
      await sp.waitForURL(new RegExp(`/courses/catalog/${lc}$`));
      await expect(sp.getByRole("heading", { level: 1, name: COURSE })).toBeVisible();
      await studentShot(sp, "18-cover");
      await sp.getByRole("button", { name: t("catalog.join") }).click();
      await sp.waitForURL(new RegExp(`${base}(/modules)?$`));
      const hero = sp.locator('section[aria-labelledby="course-overview-title"]');
      await expect(hero.getByRole("heading", { level: 1, name: COURSE })).toBeVisible();
      await expect(hero.locator("img").first()).toHaveAttribute("src", coverUrl);
      await expect(nav.getByRole("link", { name: COURSE })).toHaveAttribute("href", `${base}/modules`);
      await expect(sp.getByRole("navigation", { name: t("courses.home.tabsLabel") })).toHaveCount(0); // exam shell, no course sidebar
      const v1Id = m1.items[0].id;
      const pg1Id = m1.items[1].id;
      const fileId = m1.items[2].id;
      const v2Id = m2.items[0].id;
      const start = sp.getByRole("link", { name: t("modules.syllabus.start"), exact: true });
      await expect(start).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${v1Id}`);
      const bar = sp.getByRole("progressbar", { name: t("modules.syllabus.progressLabel") });
      await expect(bar).toHaveAttribute("aria-valuenow", "0");
      await expect(bar).toHaveAttribute("aria-valuemax", "6");
      await expect(sp.getByText(t("modules.syllabus.doneCount", { done: 0, total: 6 }))).toBeVisible();
      const sec1 = sp.locator(`#module-${m1.id}`);
      const sec2 = sp.locator(`#module-${m2.id}`);
      await expect(sec1.getByRole("button", { name: M1, exact: true })).toHaveAttribute("aria-expanded", "true");
      await expect(sec1).toContainText(t("modules.overview.moduleDone", { done: 0, total: 4 }));
      await expect(sec1.getByRole("link", { name: new RegExp(V1) })).toContainText(t("modules.overview.durationMin", { n: 6 }));
      await expect(sec1.getByRole("link", { name: new RegExp(PG1) })).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${pg1Id}`);
      await expect(sec1.getByRole("link", { name: new RegExp(FILE) })).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${fileId}`);
      await expect(sec1.getByRole("link", { name: new RegExp(QUIZ) })).toHaveAttribute("href", `${base}/assessments/${aid}`);
      // the Pro module: gold chip and unlock link; titles only, no address or video id anywhere in the page
      await expect(sec2.getByText(t("modules.overview.pro"), { exact: true })).toBeVisible();
      await expect(sec2.getByRole("link", { name: t("modules.overview.unlock") })).toHaveAttribute("href", `/${L}/pro`);
      await sec2.getByRole("button", { name: M2, exact: true }).click();
      await expect(sec2.getByText(V2)).toBeVisible();
      await expect(sec2.getByText(PG2)).toBeVisible();
      await expect(sec2.getByRole("link")).toHaveCount(1); // the unlock pill only
      expect(await sp.content()).not.toContain(PRO_YT);
      await studentShot(sp, "06-module");
      await studentShot(sp, "11-module-test", () => sec1);

      // ---- G1: the home «Продолжить урок» strip names the first lesson (the overview was opened once)
      await sp.goto(`/${L}/courses`);
      const strip = sp.locator('section[aria-labelledby="home-continue"]');
      await expect(strip.getByRole("heading", { level: 2, name: t("home.prep.continueLesson.title") })).toBeVisible();
      const row = strip.getByRole("link", { name: new RegExp(V1) });
      await expect(row).toContainText(`${COURSE} · ${M1}`);
      await expect(row).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${v1Id}`);
      await expect(homeLessons.getByRole("link", { name: COURSE })).toHaveAttribute("href", `${base}/modules`);
      await studentShot(sp, "g1-home-continue");

      // ---- 07 the video lesson: outline aside, click-to-load player, nothing fetched before the tap
      await row.click();
      await sp.waitForURL(new RegExp(`/modules/${m1.id}/items/${v1Id}$`));
      await expect(sp.getByRole("heading", { level: 1, name: V1 })).toBeVisible();
      const outline = sp.getByRole("navigation", { name: t("modules.overview.outlineTitle") });
      await expect(outline.getByRole("link", { name: new RegExp(V1) })).toHaveAttribute("aria-current", "page");
      const play = sp.getByRole("button", { name: t("modules.lesson.play", { title: V1 }) });
      await expect(play).toBeVisible();
      await expect(sp.locator("iframe")).toHaveCount(0);
      await studentShot(sp, "07-video");
      expect(thirdParty, "no request to YouTube before the tap").toEqual([]);
      const done = async (id: string) => {
        const out = (await api(student, "GET", `/courses/${lc}/modules`)).modules as StudentModule[];
        return out.flatMap((m) => m.items).find((i) => i.id === id)?.done;
      };
      expect(await done(v1Id), "opening a video lesson is not its view").toBe(false);
      await play.click();
      await expect(sp.locator(`iframe[title="${V1}"]`)).toHaveAttribute("src", `https://www.youtube-nocookie.com/embed/${YT}?autoplay=1&rel=0`);
      await expect.poll(() => done(v1Id)).toBe(true);

      // ---- 08 «Следующий урок» → the page lesson inline (its view on open)
      const pager = sp.getByRole("navigation", { name: t("modules.lesson.pagerLabel") });
      await pager.getByRole("link", { name: new RegExp(t("modules.lesson.next")) }).click();
      await sp.waitForURL(new RegExp(`/modules/${m1.id}/items/${pg1Id}$`));
      await expect(sp.getByRole("heading", { level: 1, name: PG1 })).toBeVisible();
      await expect(sp.getByText(PG1_TEXT)).toBeVisible();
      await expect.poll(() => done(pg1Id)).toBe(true);
      await studentShot(sp, "08-page");

      // ---- 09 the file lesson: the download card
      await pager.getByRole("link", { name: new RegExp(t("modules.lesson.next")) }).click();
      await sp.waitForURL(new RegExp(`/modules/${m1.id}/items/${fileId}$`));
      await expect(sp.getByRole("heading", { level: 1, name: FILE })).toBeVisible();
      await expect(sp.getByText(t("modules.lesson.fileBody"))).toBeVisible();
      const dl = sp.getByRole("button", { name: t("modules.download") });
      await expect(dl).toBeVisible();
      await studentShot(sp, "09-file");
      await dl.click(); // the view of a file lesson is its download
      await expect.poll(() => done(fileId)).toBe(true);

      // ---- 15 / 11 the module test: the lobby in the exam shell, free, can start
      await sp.goto(`${base}/modules`);
      await sp.locator(`#module-${m1.id}`).getByRole("link", { name: new RegExp(QUIZ) }).click();
      await sp.waitForURL(new RegExp(`${base}/assessments/${aid}$`));
      await expect(sp.getByRole("heading", { level: 1, name: QUIZ })).toBeVisible();
      await expect(sp.getByRole("button", { name: t("assessments.lobby.start") })).toBeEnabled();
      await expect(nav).toBeVisible();
      await expect(sp.getByRole("navigation", { name: t("courses.home.tabsLabel") })).toHaveCount(0);
      await studentShot(sp, "15-pro-test");

      // ---- 16 the Pro lesson by URL: the lock card, no player, no video id, no request
      await sp.goto(`${base}/modules/${m2.id}/items/${v2Id}`);
      await expect(sp.getByText(t("modules.overview.proLockTitle"))).toBeVisible();
      await expect(sp.locator("iframe")).toHaveCount(0);
      expect(await sp.content()).not.toContain(PRO_YT);
      await studentShot(sp, "16-pro-module");
      expect(thirdParty.some((u) => u.includes(PRO_YT)), "nothing of the Pro video was requested").toBe(false);

      // ---- D6: the exam's Тесты page does not list the lesson course's test
      await sp.goto(`/${L}/courses/${exam}/tests`);
      await expect(sp.getByRole("region", { name: t("examPrep.library.title") })).toBeVisible();
      await expect(sp.getByText(QUIZ)).toHaveCount(0);
      await studentShot(sp, "d6-exam-tests");

      // ---- 13 announcement: posted in the lesson course → the home side list → the list with the student header
      await tp.goto(`${base}/announcements/new`);
      await tp.getByRole("textbox", { name: t("announcements.fieldTitle") }).fill(ANN);
      await tp.getByRole("textbox", { name: t("announcements.fieldBody") }).fill("Во втором модуле появился конспект по аналогиям.");
      await teacherShot(tp, "13-announcement");
      await tp.getByRole("button", { name: t("announcements.postNow") }).click();
      await tp.waitForURL(new RegExp(`${base}/announcements$`));
      await sp.goto(`/${L}/courses`);
      const news = sp.locator('section[aria-labelledby="home-announcements"]');
      await news.getByRole("link", { name: new RegExp(ANN) }).click();
      await sp.waitForURL(new RegExp(`${base}/announcements$`));
      await expect(sp.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(sp.getByRole("heading", { level: 1, name: t("announcements.title") })).toBeVisible();
      await expect(sp.getByText(ANN)).toBeVisible();
      await studentShot(sp, "13-announcement");

      // ---- 12 unpublish a lesson: the row leaves the syllabus, the totals recount
      await tp.goto(base);
      const itemSwitch = tCard(tp, M1).getByRole("switch", { name: t("modules.editor.publishToggle", { title: V1 }), exact: true });
      await expect(itemSwitch).toHaveAttribute("aria-checked", "true");
      await itemSwitch.click();
      await expect(itemSwitch).toHaveAttribute("aria-checked", "false");
      await teacherShot(tp, "12-unpublish-module");
      await sp.goto(`${base}/modules`);
      await expect(bar).toHaveAttribute("aria-valuemax", "5");
      const progress = (await api(student, "GET", `/courses/${lc}/modules`)).progress as { done: number; total: number };
      expect(progress.total).toBe(5);
      expect(progress.done).toBeGreaterThanOrEqual(2); // the page and the file (the test row may count as seen)
      await expect(bar).toHaveAttribute("aria-valuenow", String(progress.done));
      await expect(sp.getByText(t("modules.syllabus.doneCount", progress))).toBeVisible();
      await expect(sp.locator(`#module-${m1.id}`).getByText(V1)).toHaveCount(0);
      await studentShot(sp, "12-unpublish-module");
    } finally {
      await tp.context().close();
      await sp.context().close();
      await api(admin, "DELETE", `/courses/${lc}`);
    }
  });
});
