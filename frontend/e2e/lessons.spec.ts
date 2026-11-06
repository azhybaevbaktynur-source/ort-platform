import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page, type Request } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5, §4.4) + F5b (docs/phases/COURSE_LESSONS_DESIGN.md L1-L7, 7):
 * course lessons. The platform admin adds three modules to the seeded ORT course (exam-prep, a platform course):
 * "Видеоуроки E2E" (a YouTube lesson with "mark as done", a Vimeo lesson, a page lesson, a plain link, a lookalike
 * host; with durations), "Закрытый модуль E2E" behind it (prerequisite) and "Pro модуль E2E" (`access_tier = paid`;
 * the ORT modules student has no pass). The student opens "Уроки" from the sidebar: the overview (cover banner, "Начать
 * курс" from up_next, "Пройдено N из M", the syllabus with the current module open, About), the Pro module shows the
 * gold chip and the unlock link and reveals no address (no href, no video id, no request), the locked lessons say why.
 * The lesson page: the outline aside, the click-to-load player (**no request reaches YouTube or Vimeo before the
 * tap**; the providers are stubbed by a route, nothing leaves the machine), the view recorded on the play tap (not on
 * open), the page lesson inline (view on open), "Следующий урок", the overview's "Продолжить курс" to the first
 * unviewed lesson. 375 px: the outline collapses under the lesson, no horizontal scroll. Cleanup deletes the modules
 * and pages (the ORT specs see the course as seeded).
 *
 * With U7_SHOTS=<dir>: overview, syllabus, lesson (video, page), locked (Pro, module) at 375 / 1440 / 1920 in ru.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.U7_SHOTS ? path.resolve(process.env.U7_SHOTS) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const YT = "dQw4w9WgXcQ";
const PRO_YT = "M7lc1UVf-VE";
const PRO_URL = `https://www.youtube.com/watch?v=${PRO_YT}`;
const M1 = "Видеоуроки E2E";
const M2 = "Закрытый модуль E2E";
const M3 = "Pro модуль E2E";
const V1 = "Сравнение величин: основы";
const V2 = "Приёмы быстрого сравнения";
const PG = "Разбор задач на дроби";
const PG_TEXT = "Текст урока про дроби E2E";
const LINK = "Дополнительное чтение";
const FAKE = "Похожий адрес";
const V3 = "Разбор задач";
const V4 = "Секреты аналогий";
const PG_PRO = "Аналогии: конспект";
const THIRD_PARTY = /youtube|youtu\.be|ytimg|googlevideo|vimeo|vimeocdn/i;

async function api(user: SeedUser, method: string, p: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect([200, 201, 204], `${method} ${p} -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

async function shoot(page: Page, name: string, network = true) {
  if (!SHOTS) return;
  await settle(page, network);
  await page.screenshot({ path: path.join(SHOTS, `${name}-${page.viewportSize()!.width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
}

/** Every width of the UX check: no horizontal scroll, a screenshot each. */
async function widths(page: Page, name: string, network = true) {
  for (const width of [1440, 1920, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page, network);
    await noHorizontalScroll(page);
    await shoot(page, name, network);
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

test.describe("course lessons (ru)", () => {
  test("overview, syllabus, Pro lock, lesson page with outline, view on engagement, next lesson", async ({ browser }) => {
    test.setTimeout(300_000);
    const s = seed();
    const cid = s.course_id;
    const base = `/${L}/courses/${cid}`;
    const admin = s.admin;
    const student = s.modules.ort_student;
    const created: string[] = [];
    const pages: string[] = [];
    try {
      const item = (m: string, url: string, title: string, minutes: number | null = null) =>
        api(admin, "POST", `/courses/${cid}/modules/${m}/items`, {
          kind: "url", url, title_override: { ru: title }, published: true, duration_s: minutes ? minutes * 60 : null,
        });
      const pageItem = async (m: string, title: string, text: string, minutes: number) => {
        const pg = await api(admin, "POST", `/courses/${cid}/pages`, { title, language: "ru", body_md: text, published: true });
        pages.push(pg.id);
        const it = await api(admin, "POST", `/courses/${cid}/modules/${m}/items`, { kind: "page", page_id: pg.id, published: true, duration_s: minutes * 60 });
        return { page: pg, item: it };
      };
      const m1 = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: M1 }, published: true });
      created.push(m1.id);
      const v1 = await item(m1.id, `https://www.youtube.com/watch?v=${YT}`, V1, 6);
      await api(admin, "PUT", `/courses/${cid}/modules/${m1.id}/items/${v1.id}/requirement`, { type: "mark_done" });
      const v2 = await item(m1.id, "https://vimeo.com/76979871", V2, 8);
      const pg = await pageItem(m1.id, PG, PG_TEXT, 10);
      const link = await item(m1.id, "https://example.org/reading", LINK);
      await item(m1.id, `https://youtube.com.evil.example/watch?v=${YT}`, FAKE);
      const m2 = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: M2 }, published: true });
      created.push(m2.id);
      await api(admin, "PUT", `/courses/${cid}/modules/${m2.id}/prerequisites`, { module_ids: [m1.id] });
      const v3 = await item(m2.id, `https://youtu.be/${YT}`, V3, 5);
      const m3 = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: M3 }, published: true, access_tier: "paid" });
      created.push(m3.id);
      const v4 = await item(m3.id, PRO_URL, V4, 7);
      const pgPro = await pageItem(m3.id, PG_PRO, "Конспект Pro", 4);

      const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
      // the providers are stubbed: the test proves the iframe is requested after the tap, nothing leaves the machine
      await ctx.route(THIRD_PARTY, (route) => route.fulfill({
        status: 200, contentType: "text/html",
        body: "<!doctype html><html><body style=\"margin:0;background:#000;color:#fff;font:16px sans-serif;display:flex;align-items:center;justify-content:center;height:100vh\">player</body></html>",
      }));
      const thirdParty: string[] = [];
      ctx.on("request", (r: Request) => { if (THIRD_PARTY.test(new URL(r.url()).hostname)) thirdParty.push(r.url()); });
      const page = await ctx.newPage();
      await signIn(page, student);
      const itemOut = async (moduleId: string, itemId: string) => {
        const out = await api(student, "GET", `/courses/${cid}/modules`);
        const mod = (out.modules as { id: string; items: { id: string; done?: boolean }[] }[]).find((m) => m.id === moduleId)!;
        return mod.items.find((i) => i.id === itemId)!;
      };

      // ---- the sidebar: "Уроки", already on Главная (U9: the course list carries what the course has); one Тесты link
      await page.goto(`/${L}/courses`);
      const nav = page.getByRole("navigation", { name: t("student.nav.label") });
      const lessonsLink = nav.getByRole("link", { name: t("student.nav.lessons"), exact: true });
      await expect(lessonsLink).toBeVisible();
      await expect(nav.getByRole("link", { name: t("student.nav.tests"), exact: true })).toHaveCount(1);
      await lessonsLink.click();
      await page.waitForURL(new RegExp(`${base}/modules$`));
      await expect(lessonsLink).toHaveAttribute("aria-current", "page");
      await expect(nav.getByRole("link", { name: M1, exact: true })).toHaveCount(0);

      // ---- the overview: banner (one h1: the course), "Начать курс" to the first lesson, "Пройдено 0 из 8", About
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(page.getByText(t("modules.overview.nextUp", { title: V1 }))).toBeVisible();
      const cta = page.getByRole("link", { name: t("modules.syllabus.start"), exact: true });
      await expect(cta).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${v1.id}`);
      const bar = page.getByRole("progressbar", { name: t("modules.syllabus.progressLabel") });
      await expect(bar).toHaveAttribute("aria-valuenow", "0");
      await expect(bar).toHaveAttribute("aria-valuemax", "8");
      await expect(page.getByText(t("modules.syllabus.doneCount", { done: 0, total: 8 }))).toBeVisible();
      await expect(page.getByRole("heading", { name: t("modules.syllabus.aboutTitle") })).toBeVisible();
      await expect(page.getByRole("heading", { name: t("modules.overview.syllabusTitle"), exact: true })).toBeVisible();
      const sec1 = page.locator(`#module-${m1.id}`);
      const sec2 = page.locator(`#module-${m2.id}`);
      const sec3 = page.locator(`#module-${m3.id}`);
      // the current module is open, the others closed; M1: 0 of 5 · 24 min
      await expect(sec1.getByRole("button", { name: M1, exact: true })).toHaveAttribute("aria-expanded", "true");
      await expect(sec2.getByRole("button", { name: M2, exact: true })).toHaveAttribute("aria-expanded", "false");
      await expect(sec1).toContainText(t("modules.overview.moduleDone", { done: 0, total: 5 }));
      await expect(sec1).toContainText(t("modules.overview.durationMin", { n: 24 }));
      // lessons open the lesson page (the page lesson too); a plain link and a lookalike host stay links to the address
      await expect(sec1.getByRole("link", { name: new RegExp(V1) })).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${v1.id}`);
      await expect(sec1.getByRole("link", { name: new RegExp(PG) })).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${pg.item.id}`);
      await expect(sec1.getByRole("link", { name: new RegExp(LINK) })).toHaveAttribute("href", "https://example.org/reading");
      await expect(sec1.getByRole("link", { name: new RegExp(FAKE) })).toHaveAttribute("href", `https://youtube.com.evil.example/watch?v=${YT}`);
      await expect(sec1.getByRole("link", { name: new RegExp(FAKE) })).toHaveAttribute("target", "_blank");
      await expect(sec1.getByRole("link", { name: new RegExp(V1) })).toContainText(t("modules.overview.durationMin", { n: 6 }));
      await widths(page, "overview");
      // the locked module: the reason, no link
      await expect(sec2).toContainText(t("modules.reason.prerequisite", { title: M1 }));
      await sec2.getByRole("button", { name: M2, exact: true }).click();
      await expect(sec2.getByText(V3)).toBeVisible();
      await expect(sec2.getByRole("link")).toHaveCount(0);
      // the Pro module: the gold chip, the unlock link and titles with durations only (no address anywhere)
      await expect(sec3.getByText(t("modules.overview.pro"), { exact: true })).toBeVisible();
      await expect(sec3.getByRole("link", { name: t("modules.overview.unlock") })).toHaveAttribute("href", `/${L}/unlock`);
      await sec3.getByRole("button", { name: M3, exact: true }).click();
      await expect(sec3.getByText(V4)).toBeVisible();
      await expect(sec3.getByText(PG_PRO)).toBeVisible();
      await expect(sec3).toContainText(t("modules.overview.durationMin", { n: 7 }));
      await expect(sec3.getByRole("link")).toHaveCount(1); // the unlock pill only
      // Pro rows: title and duration only, no guessed kind ("Ссылка") for a video the server does not name
      await expect(sec3).not.toContainText(t("modules.kinds.url"));
      await expect(sec3).not.toContainText(t("modules.kinds.page"));
      expect(await page.content()).not.toContain(PRO_YT);
      expect(await page.content()).not.toContain(pgPro.page.id);
      await expect(page.locator(`a[href*="${PRO_YT}"]`)).toHaveCount(0);
      await widths(page, "syllabus");

      // ---- the locked lesson by URL (M2 waits for M1): why, the way back, no player, no video id in the page
      await page.goto(`${base}/modules/${m2.id}/items/${v3.id}`);
      await expect(page.getByText(t("modules.lesson.lockedTitle"))).toBeVisible();
      await expect(page.getByText(t("modules.reason.prerequisite", { title: M1 }))).toBeVisible();
      await expect(page.getByRole("link", { name: t("modules.overview.toSyllabus") })).toHaveAttribute("href", `${base}/modules`);
      await expect(page.getByRole("button", { name: t("modules.lesson.play", { title: V3 }) })).toHaveCount(0);
      expect(await page.content()).not.toContain(YT);
      await widths(page, "locked-module");

      // ---- the Pro lesson by URL: the lock card with the gold unlock pill; no iframe, no video id, no request
      await page.goto(`${base}/modules/${m3.id}/items/${v4.id}`);
      await expect(page.getByText(t("modules.overview.proLockTitle"))).toBeVisible();
      await expect(page.getByRole("main").getByRole("link", { name: t("modules.overview.unlock") })).toHaveAttribute("href", `/${L}/unlock`);
      await expect(page.locator("iframe")).toHaveCount(0);
      await expect(page.getByRole("button", { name: t("modules.lesson.play", { title: V4 }) })).toHaveCount(0);
      expect(await page.content()).not.toContain(PRO_YT);
      await widths(page, "locked-pro");
      expect(thirdParty, "no request to YouTube / Vimeo on the overview or a locked lesson").toEqual([]);

      // ---- the lesson: the outline aside, the player card, nothing fetched before the tap
      await page.goto(`${base}/modules`);
      await page.getByRole("link", { name: t("modules.syllabus.start"), exact: true }).click();
      await page.waitForURL(new RegExp(`/modules/${m1.id}/items/${v1.id}$`));
      await expect(page.getByRole("heading", { level: 1, name: V1 })).toBeVisible();
      const outline = page.getByRole("navigation", { name: t("modules.overview.outlineTitle") });
      await expect(outline).toHaveCount(1);
      await expect(outline.getByRole("link", { name: new RegExp(V1) })).toHaveAttribute("aria-current", "page");
      await expect(outline.getByRole("button", { name: new RegExp(`^${M1}`) })).toHaveAttribute("aria-expanded", "true");
      await expect(outline.getByRole("button", { name: new RegExp(`^${M3}`) })).toHaveAttribute("aria-expanded", "false");
      const play = page.getByRole("button", { name: t("modules.lesson.play", { title: V1 }) });
      await expect(play).toBeVisible();
      await expect(page.locator("iframe")).toHaveCount(0);
      await widths(page, "lesson-video");
      expect(thirdParty, "no request to YouTube / Vimeo before the tap").toEqual([]);

      await play.click();
      const frame = page.locator(`iframe[title="${V1}"]`);
      await expect(frame).toHaveAttribute("src", `https://www.youtube-nocookie.com/embed/${YT}?autoplay=1&rel=0`);
      await expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation");
      await expect.poll(() => thirdParty.some((u) => u.startsWith(`https://www.youtube-nocookie.com/embed/${YT}`))).toBe(true);
      await expect(page.frameLocator(`iframe[title="${V1}"]`).getByText("player")).toBeVisible(); // CSP frame-src allows it

      // ---- mark as done, then "Следующий урок" (Vimeo): the view is recorded on the tap, not on open
      await page.getByRole("button", { name: t("modules.lesson.markDone") }).click();
      await expect(page.getByRole("button", { name: t("modules.lesson.undo") })).toBeVisible();
      const pager = page.getByRole("navigation", { name: t("modules.lesson.pagerLabel") });
      await pager.getByRole("link", { name: new RegExp(t("modules.lesson.next")) }).click();
      await page.waitForURL(new RegExp(`/modules/${m1.id}/items/${v2.id}$`));
      const play2 = page.getByRole("button", { name: t("modules.lesson.play", { title: V2 }) });
      await expect(play2).toBeVisible();
      await expect(page.locator("iframe")).toHaveCount(0);
      await settle(page);
      expect((await itemOut(m1.id, v2.id)).done, "opening a video lesson is not its view").toBe(false);
      await play2.click();
      await expect.poll(async () => (await itemOut(m1.id, v2.id)).done).toBe(true);

      // ---- the page lesson inline (view on open); "Назад" goes back
      await pager.getByRole("link", { name: new RegExp(t("modules.lesson.next")) }).click();
      await page.waitForURL(new RegExp(`/modules/${m1.id}/items/${pg.item.id}$`));
      await expect(page.getByRole("heading", { level: 1, name: PG })).toBeVisible();
      await expect(page.getByText(PG_TEXT)).toBeVisible();
      await expect.poll(async () => (await itemOut(m1.id, pg.item.id)).done).toBe(true);
      await widths(page, "lesson-page");
      // an old syllabus link to the page forwards to the lesson page
      await page.goto(`${base}/pages/${pg.page.id}?from=module&m=${m1.id}&i=${pg.item.id}`);
      await page.waitForURL(new RegExp(`/modules/${m1.id}/items/${pg.item.id}$`));
      await expect(page.getByText(PG_TEXT)).toBeVisible();

      // ---- the overview counts it: "Продолжить курс" to the first lesson not done (the plain link)
      await page.goto(`${base}/modules`);
      await expect(bar).toHaveAttribute("aria-valuenow", "3");
      const cont = page.getByRole("link", { name: t("modules.syllabus.continue"), exact: true });
      await expect(cont).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${link.id}`);
      await expect(page.getByText(t("modules.overview.nextUp", { title: LINK }))).toBeVisible();
      await expect(sec1).toContainText(t("modules.overview.moduleDone", { done: 3, total: 5 }));

      // ---- M1 complete (its one requirement): M2 opens, its lesson plays after a tap
      await page.goto(`${base}/modules/${m2.id}/items/${v3.id}`);
      await expect(page.getByRole("button", { name: t("modules.lesson.play", { title: V3 }) })).toBeVisible();

      // ---- phone: the outline is a collapsible under the lesson, the pager stays on screen, no horizontal scroll
      await page.setViewportSize(VIEWPORTS.phone);
      await page.goto(`${base}/modules/${m1.id}/items/${v2.id}`);
      await expect(page.getByRole("heading", { level: 1, name: V2 })).toBeVisible();
      // the phone breadcrumb names the module and leads back to it in the syllabus
      await expect(page.getByRole("navigation", { name: t("modules.overview.breadcrumbLabel") }).getByRole("link", { name: M1 }))
        .toHaveAttribute("href", `${base}/modules#module-${m1.id}`);
      const summary =page.locator("summary").filter({ hasText: t("modules.overview.outlineTitle") });
      await expect(summary).toBeVisible();
      await expect(page.getByRole("navigation", { name: t("modules.overview.outlineTitle") })).toBeHidden();
      await summary.click();
      await expect(page.getByRole("navigation", { name: t("modules.overview.outlineTitle") })).toBeVisible();
      await expect(page.getByRole("navigation", { name: t("modules.lesson.pagerLabel") }).getByRole("link", { name: new RegExp(t("modules.lesson.next")) })).toBeInViewport();
      await settle(page);
      await noHorizontalScroll(page);
      await page.goto(`${base}/modules`);
      await expect(page.getByRole("heading", { name: M1 })).toBeVisible();
      await settle(page);
      await noHorizontalScroll(page);
      expect(thirdParty.some((u) => u.includes(PRO_YT)), "nothing of the Pro video was requested").toBe(false);
      await ctx.close();
    } finally {
      for (const id of created.reverse()) await api(admin, "DELETE", `/courses/${cid}/modules/${id}`);
      for (const id of pages) await api(admin, "DELETE", `/courses/${cid}/pages/${id}`);
    }
  });

  test("overview banner states: no lessons, only locked left, only Pro left, all done", async ({ browser }) => {
    test.setTimeout(180_000);
    const s = seed();
    const cid = s.course_id;
    const base = `/${L}/courses/${cid}`;
    const admin = s.admin;
    const student = s.modules.ort_student;
    const created: string[] = [];
    const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    try {
      const page = await ctx.newPage();
      await signIn(page, student);
      const hero = page.locator('section[aria-labelledby="course-overview-title"]');
      const open = async () => {
        await page.goto(`${base}/modules`);
        await expect(hero).toBeVisible();
        await settle(page);
      };
      /** One state: its line, no empty paragraph, never "Продолжим?" / "Готовы начать?" next to it. */
      const only = async (text: string) => {
        await expect(hero.getByText(text, { exact: true })).toBeVisible();
        await expect(hero.getByText(t("modules.syllabus.continueTitle"))).toHaveCount(0);
        await expect(hero.getByText(t("modules.syllabus.readyTitle"))).toHaveCount(0);
        expect(await hero.locator("p:empty").count()).toBe(0);
      };

      // a published module without any row: "no lessons yet", no action, no bar
      const empty = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: "Пустой модуль E2E" }, published: true });
      created.push(empty.id);
      await open();
      await only(t("modules.overview.emptyTitle"));
      await expect(hero.getByRole("link")).toHaveCount(0);
      await expect(page.getByRole("progressbar")).toHaveCount(0);
      await api(admin, "DELETE", `/courses/${cid}/modules/${created.pop()}`);

      // one lesson the student has seen, one in a module that opens later: "the next lessons open later", no action
      const a = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: "Открытый модуль E2E" }, published: true });
      created.push(a.id);
      const la = await api(admin, "POST", `/courses/${cid}/modules/${a.id}/items`, { kind: "url", url: "https://example.org/a", title_override: { ru: "Урок А" }, published: true });
      const b = await api(admin, "POST", `/courses/${cid}/modules`, {
        title: { ru: "Модуль позже E2E" }, published: true, unlock_at: new Date(Date.now() + 3 * 86_400_000).toISOString(),
      });
      created.push(b.id);
      await api(admin, "POST", `/courses/${cid}/modules/${b.id}/items`, { kind: "url", url: "https://example.org/b", title_override: { ru: "Урок Б" }, published: true });
      await api(student, "GET", `/courses/${cid}/modules`);
      await api(student, "POST", `/courses/${cid}/modules/${a.id}/items/${la.id}/view`, {});
      await open();
      await only(t("modules.overview.later"));
      await expect(hero.getByRole("link")).toHaveCount(0);

      // a Pro module left as well: the gold unlock pill
      const c = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: "Pro позже E2E" }, published: true, access_tier: "paid" });
      created.push(c.id);
      await api(admin, "POST", `/courses/${cid}/modules/${c.id}/items`, { kind: "url", url: "https://example.org/c", title_override: { ru: "Урок В" }, published: true });
      await open();
      await only(t("modules.overview.proLeft"));
      await expect(hero.getByRole("link", { name: t("modules.overview.unlock") })).toHaveAttribute("href", `/${L}/unlock`);

      // everything open is done: "Курс пройден" and "Повторить с начала" to the first lesson
      await api(admin, "DELETE", `/courses/${cid}/modules/${created.pop()}`);
      await api(admin, "DELETE", `/courses/${cid}/modules/${created.pop()}`);
      await open();
      await only(t("modules.overview.completed"));
      await expect(hero.getByRole("link", { name: t("modules.overview.restart") })).toHaveAttribute("href", `${base}/modules/${a.id}/items/${la.id}`);
      await expect(page.getByRole("progressbar", { name: t("modules.syllabus.progressLabel") })).toHaveAttribute("aria-valuenow", "1");
    } finally {
      await ctx.close();
      for (const id of created.reverse()) await api(admin, "DELETE", `/courses/${cid}/modules/${id}`);
    }
  });
});
