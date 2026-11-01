import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser } from "@playwright/test";
import { seed, settle, signIn, type SeedUser } from "./helpers";

/**
 * Phase 10 check (UR-6): the new screens in ru at 375, 1440 and 1920 px; fails on sideways page scroll.
 * Skipped unless UX_SCREENS_DIR is set. Builds its own course through the API.
 */
const OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
const SIZES = [[375, 812], [1440, 900], [1920, 1080]] as const;
const ids: Record<string, string> = {};

async function api(user: SeedUser, method: string, p: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method, headers: { Authorization: `Bearer ${user.token}`, "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(r.status, `${method} ${p}: ${text.slice(0, 300)}`).toBeLessThan(300);
  return text ? JSON.parse(text) : null;
}

async function walk(browser: Browser, user: SeedUser, shots: [string, string][]) {
  for (const [w, h] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ru-RU", timezoneId: "UTC" });
    const page = await ctx.newPage();
    await signIn(page, user);
    for (const [name, url] of shots) {
      await page.goto(url);
      await settle(page);
      await page.waitForTimeout(300);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over, `${name} at ${w}px scrolls sideways`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: path.join(OUT!, `${name}-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
    }
    await ctx.close();
  }
}

test.describe("phase 10 screens", () => {
  test.skip(!OUT, "set UX_SCREENS_DIR");
  test.describe.configure({ mode: "serial" });

  test("fill", async () => {
    fs.mkdirSync(OUT!, { recursive: true });
    const { teacher: T, student: S } = seed().quiz_editor;
    const title = { ru: "Практика: проверка", ky: "Практика: проверка", en: "Practice check" };
    const c = await api(T, "POST", "/courses", { title, languages: ["ru", "ky", "en"], default_language: "ru" });
    ids.c = c.id;
    await api(T, "POST", `/courses/${c.id}/publish`, {});
    const bank = await api(T, "POST", `/courses/${c.id}/banks`, { title: "Банк", default_language: "ru" });
    ids.bank = bank.id;
    const q = (type: string, stem: string, data: unknown) => api(T, "POST", `/courses/${c.id}/banks/${bank.id}/questions`, { type, language: "ru", stem, explanation: "Потому что так.", data });
    await q("matching", "Соедините столицы и страны", { pairs: [{ left: "Бишкек", right: "Кыргызстан" }, { left: "Астана", right: "Казахстан" }, { left: "Ташкент", right: "Узбекистан" }], distractors: ["Таджикистан"] });
    await q("fill_blank", "Заполните пропуски", { text: "Небо {{1}}, трава {{2}}.", blanks: [{ answers: ["синее"] }, { answers: ["зелёная"] }] });
    await q("ordering", "Расставьте по порядку", { items: [{ text: "Первый" }, { text: "Второй" }, { text: "Третий" }] });
    await api(S, "POST", "/courses/join", { code: c.join_code ?? (await api(T, "GET", `/courses/${c.id}`)).join_code });
    const set = await api(T, "POST", `/courses/${c.id}/practice`, { title: { ru: "Набор" }, languages: ["ru"], blocks: [{ bank_id: bank.id, count: 3 }] });
    ids.set = set.id;
    const a = await api(S, "POST", `/courses/${c.id}/assessments/${set.id}/attempts`, {});
    ids.attempt = a.attempt_id ?? a.id;
  });

  test("student", async ({ browser }) => {
    test.setTimeout(240_000);
    const S = seed().quiz_editor.student;
    const b = `/ru/courses/${ids.c}`;
    await walk(browser, S, [["player-practice", `${b}/attempts/${ids.attempt}`]]);
    // every structured item, answered in the player's own order
    for (const [w, h] of SIZES) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ru-RU", timezoneId: "UTC" });
      const page = await ctx.newPage();
      await signIn(page, S);
      await page.goto(`${b}/attempts/${ids.attempt}`);
      await settle(page);
      for (let i = 1; i <= 3; i++) {
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(OUT!, `player-item${i}-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
        const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(over, `item ${i} at ${w}px scrolls sideways`).toBeLessThanOrEqual(0);
        const next = page.getByRole("button", { name: /Далее|Следующ/ }).first();
        if (await next.count()) await next.click().catch(() => null);
      }
      await ctx.close();
    }
    await api(S, "POST", `/attempts/${ids.attempt}/submit`, {}).catch(() => null);
    await walk(browser, S, [["student-practice", `${b}/practice`], ["student-progress", `${b}/progress`]]);
  });

  test("org analytics and question editor", async ({ browser }) => {
    test.setTimeout(240_000);
    const o = seed().org_admin;
    await walk(browser, o.org_admin, [["org-analytics", `/ru/org/${o.organization_id}/analytics`]]);
    const T = seed().quiz_editor.teacher;
    const b = `/ru/courses/${ids.c}`;
    for (const [type, opt] of [["matching", "matching"], ["fill_blank", "fill_blank"], ["ordering", "ordering"]] as const) {
      for (const [w, h] of SIZES) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ru-RU", timezoneId: "UTC" });
        const page = await ctx.newPage();
        await signIn(page, T);
        await page.goto(`${b}/bank/${ids.bank}/new?type=${type}`);
        await settle(page);
        await expect(page.locator(`option[value="${opt}"]:checked`).first()).toHaveCount(1);
        await page.waitForTimeout(400);
        const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(over, `editor ${type} at ${w}px scrolls sideways`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: path.join(OUT!, `editor-${type}-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
        await ctx.close();
      }
    }
  });

  test("teacher", async ({ browser }) => {
    test.setTimeout(240_000);
    const T = seed().quiz_editor.teacher;
    const b = `/ru/courses/${ids.c}`;
    await walk(browser, T, [["teacher-practice", `${b}/practice`], ["teacher-analytics", `${b}/analytics`], ["teacher-quiz-stats", `${b}/analytics/quizzes/${ids.set}`]]);
  });
});
