import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page, type Request } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Student UI U7 (docs/phases/STUDENT_UI_DESIGN.md §3.5, §4.4): video lessons. The platform admin adds two modules to the
 * seeded ORT course (exam-prep): "Видеоуроки E2E" (a YouTube lesson with "mark as done", a Vimeo lesson, a plain link,
 * a lookalike host) and "Закрытый модуль E2E" behind it (a YouTube lesson, locked). The extra ORT student of the
 * modules walk (`seed().modules.ort_student`) opens the syllabus from the sidebar, the lesson page shows the player card and **no request reaches
 * YouTube or Vimeo before the tap** (network log); the tap inserts the no-cookie player (CSP `frame-src` allows it;
 * the provider is stubbed by a route, nothing leaves the machine), "mark as done" counts, next / previous lesson work,
 * the plain and lookalike URLs stay links, the locked lesson says why and has no player. 375 px: no horizontal scroll.
 * Cleanup deletes both modules (the ORT specs see the course as seeded).
 *
 * With U7_SHOTS=<dir>: syllabus and lesson (before / after the tap) at 375 / 1440 / 1920 in ru.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.U7_SHOTS ? path.resolve(process.env.U7_SHOTS) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const YT = "dQw4w9WgXcQ";
const M1 = "Видеоуроки E2E";
const M2 = "Закрытый модуль E2E";
const V1 = "Сравнение величин: основы";
const V2 = "Приёмы быстрого сравнения";
const LINK = "Дополнительное чтение";
const FAKE = "Похожий адрес";
const V3 = "Разбор задач";
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

test.describe("video lessons (ru)", () => {
  test("syllabus, click-to-load player, mark as done, prev / next, locks", async ({ browser }) => {
    test.setTimeout(240_000);
    const s = seed();
    const cid = s.course_id;
    const base = `/${L}/courses/${cid}`;
    const admin = s.admin;
    const created: string[] = [];
    try {
      const m1 = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: M1 }, published: true });
      created.push(m1.id);
      const item = (m: string, url: string, title: string) =>
        api(admin, "POST", `/courses/${cid}/modules/${m}/items`, { kind: "url", url, title_override: { ru: title }, published: true });
      const v1 = await item(m1.id, `https://www.youtube.com/watch?v=${YT}`, V1);
      await api(admin, "PUT", `/courses/${cid}/modules/${m1.id}/items/${v1.id}/requirement`, { type: "mark_done" });
      const v2 = await item(m1.id, "https://vimeo.com/76979871", V2);
      await item(m1.id, "https://example.org/reading", LINK);
      await item(m1.id, `https://youtube.com.evil.example/watch?v=${YT}`, FAKE);
      const m2 = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: M2 }, published: true });
      created.push(m2.id);
      await api(admin, "PUT", `/courses/${cid}/modules/${m2.id}/prerequisites`, { module_ids: [m1.id] });
      const v3 = await item(m2.id, `https://youtu.be/${YT}`, V3);

      const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
      // the providers are stubbed: the test proves the iframe is requested after the tap, nothing leaves the machine
      await ctx.route(THIRD_PARTY, (route) => route.fulfill({
        status: 200, contentType: "text/html",
        body: "<!doctype html><html><body style=\"margin:0;background:#000;color:#fff;font:16px sans-serif;display:flex;align-items:center;justify-content:center;height:100vh\">player</body></html>",
      }));
      const thirdParty: string[] = [];
      ctx.on("request", (r: Request) => { if (THIRD_PARTY.test(new URL(r.url()).hostname)) thirdParty.push(r.url()); });
      const page = await ctx.newPage();
      await signIn(page, s.modules.ort_student);

      // ---- the sidebar: "Видеоуроки", already on Главная (U9: the course list carries what the course has)
      await page.goto(`/${L}/courses`);
      const nav = page.getByRole("navigation", { name: t("student.nav.label") });
      const lessonsLink = nav.getByRole("link", { name: t("student.nav.lessons"), exact: true });
      await expect(lessonsLink).toBeVisible();
      await lessonsLink.click();
      await page.waitForURL(new RegExp(`${base}/modules$`));
      await expect(lessonsLink).toHaveAttribute("aria-current", "page");
      // U9 (review 5): the same menu on every page, no module sub-links (the phone never had them)
      await expect(nav.getByRole("link", { name: M1, exact: true })).toHaveCount(0);

      // ---- the syllabus (exam-prep: its own title instead of the course header)
      await expect(page.getByRole("heading", { level: 1, name: t("student.nav.lessons") })).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(page.getByRole("heading", { name: t("modules.syllabus.readyTitle") })).toBeVisible();
      await expect(page.getByText(t("modules.syllabus.readyBody", { title: V1 }))).toBeVisible();
      await expect(page.getByRole("progressbar", { name: t("modules.syllabus.progressLabel") })).toHaveAttribute("aria-valuenow", "0");
      await expect(page.getByRole("heading", { name: t("modules.syllabus.aboutTitle") })).toBeVisible();
      const sec1 = page.locator(`#module-${m1.id}`);
      const sec2 = page.locator(`#module-${m2.id}`);
      await expect(sec1.getByRole("link", { name: new RegExp(V1) })).toHaveAttribute("href", `${base}/modules/${m1.id}/items/${v1.id}`);
      // a plain link and a lookalike host stay links to the stored address (new tab), never a lesson page
      await expect(sec1.getByRole("link", { name: new RegExp(LINK) })).toHaveAttribute("href", "https://example.org/reading");
      await expect(sec1.getByRole("link", { name: new RegExp(FAKE) })).toHaveAttribute("href", `https://youtube.com.evil.example/watch?v=${YT}`);
      await expect(sec1.getByRole("link", { name: new RegExp(FAKE) })).toHaveAttribute("target", "_blank");
      // the locked module: the reason, no link
      await expect(sec2).toContainText(t("modules.reason.prerequisite", { title: M1 }));
      await expect(sec2.getByRole("link")).toHaveCount(0);
      // collapse and expand
      const toggle = sec1.getByRole("button", { name: M1, exact: true });
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(sec1.getByRole("link", { name: new RegExp(V1) })).toBeHidden();
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await settle(page);
      for (const width of [1440, 1920, 375]) {
        await page.setViewportSize({ width, height: 900 });
        await settle(page);
        await noHorizontalScroll(page);
        await shoot(page, "syllabus");
      }
      await page.setViewportSize(VIEWPORTS.desktop);

      // ---- the locked lesson by URL (M2 waits for M1): why, no player, no video id in the page
      await page.goto(`${base}/modules/${m2.id}/items/${v3.id}`);
      await expect(page.getByText(t("modules.lesson.lockedTitle"))).toBeVisible();
      await expect(page.getByText(t("modules.reason.prerequisite", { title: M1 }))).toBeVisible();
      await expect(page.getByRole("button", { name: t("modules.lesson.play", { title: V3 }) })).toHaveCount(0);
      expect(await page.content()).not.toContain(YT);
      await page.goto(`${base}/modules`);

      // ---- the lesson: the player card, nothing fetched from a third party before the tap
      await page.getByRole("link", { name: t("modules.syllabus.start") }).click();
      await page.waitForURL(new RegExp(`/modules/${m1.id}/items/${v1.id}$`));
      await expect(page.getByRole("heading", { name: V1 })).toBeVisible();
      const play = page.getByRole("button", { name: t("modules.lesson.play", { title: V1 }) });
      await expect(play).toBeVisible();
      await expect(page.locator("iframe")).toHaveCount(0);
      for (const width of [1440, 1920, 375]) {
        await page.setViewportSize({ width, height: 900 });
        await settle(page);
        await noHorizontalScroll(page);
        await shoot(page, "lesson-before-tap");
      }
      await page.setViewportSize(VIEWPORTS.desktop);
      expect(thirdParty, "no request to YouTube / Vimeo before the tap").toEqual([]);

      await play.click();
      const frame = page.locator(`iframe[title="${V1}"]`);
      await expect(frame).toHaveAttribute("src", `https://www.youtube-nocookie.com/embed/${YT}?autoplay=1&rel=0`);
      await expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation");
      await expect.poll(() => thirdParty.some((u) => u.startsWith(`https://www.youtube-nocookie.com/embed/${YT}`))).toBe(true);
      await expect(page.frameLocator(`iframe[title="${V1}"]`).getByText("player")).toBeVisible(); // CSP frame-src allows it
      for (const width of [1440, 1920, 375]) {
        await page.setViewportSize({ width, height: 900 });
        await page.waitForTimeout(300);
        await shoot(page, "lesson-after-tap", false); // the stubbed player frame keeps the network busy
      }
      await page.setViewportSize(VIEWPORTS.desktop);

      // ---- mark as done, then the next lesson (Vimeo) and back
      await page.getByRole("button", { name: t("modules.lesson.markDone") }).click();
      await expect(page.getByText(t("modules.lesson.done"))).toBeVisible();
      const pager = page.getByRole("navigation", { name: t("modules.lesson.pagerLabel") });
      await pager.getByRole("link", { name: new RegExp(V2) }).click();
      await page.waitForURL(new RegExp(`/modules/${m1.id}/items/${v2.id}$`));
      await expect(page.getByRole("button", { name: t("modules.lesson.play", { title: V2 }) })).toBeVisible();
      await expect(page.locator("iframe")).toHaveCount(0);
      await pager.getByRole("link", { name: new RegExp(V1) }).click();
      await page.waitForURL(new RegExp(`/modules/${m1.id}/items/${v1.id}$`));
      await expect(page.getByText(t("modules.lesson.done"))).toBeVisible();

      // ---- the syllabus counts it: the only lesson with a requirement is done (1 of 1)
      await page.goto(`${base}/modules`);
      await expect(page.getByRole("heading", { name: t("modules.syllabus.doneTitle") })).toBeVisible();
      await expect(page.getByRole("progressbar", { name: t("modules.syllabus.progressLabel") })).toHaveAttribute("aria-valuenow", "1");

      // ---- M1 complete: M2 opens, its lesson plays after a tap
      await page.goto(`${base}/modules/${m2.id}/items/${v3.id}`);
      await expect(page.getByRole("button", { name: t("modules.lesson.play", { title: V3 }) })).toBeVisible();

      // ---- phone: the syllabus stacks, no horizontal scroll
      await page.setViewportSize(VIEWPORTS.phone);
      await page.goto(`${base}/modules`);
      await expect(page.getByRole("heading", { name: M1 })).toBeVisible();
      await settle(page);
      await noHorizontalScroll(page);
      await ctx.close();
    } finally {
      for (const id of created.reverse()) await api(admin, "DELETE", `/courses/${cid}/modules/${id}`);
    }
  });
});
