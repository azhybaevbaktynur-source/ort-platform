import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * Records the real screens shown on the landing page into `public/landing/<name>-<lang>.webp` (en, ky, ru). Skipped
 * unless RECORD_LANDING=1. Build the frontend first (docs/phases/ORT_BASELINE/README.md, "Run"), then one command:
 *
 *   cd frontend && RECORD_LANDING=1 E2E_WEB_DIR=<build dir> E2E_PYTHON=<backend venv python> npx playwright test e2e/landing-screens.spec.ts
 *
 * The harness starts its own scratch backend and frontend; E2E_API_PORT, E2E_WEB_PORT and E2E_DIR work as usual. Needs
 * system `python3` with Pillow (e2e/landing_webp.py converts the PNGs: 1200 px wide, quality 78). Commit the new files.
 * The people and the courses come from `seed_landing` in e2e/seed_backend.py. The ORT exam is the suite's own, so `SHOW`
 * below only changes its display strings, in the browser, for these screenshots.
 */

const RECORD = process.env.RECORD_LANDING === "1";
const PNG_DIR = path.join(E2E_DIR, "landing-png");
const OUT_DIR = path.resolve(__dirname, "../public/landing");
const LANGS = ["en", "ky", "ru"] as const;
type L3 = (typeof LANGS)[number];

// 1024 CSS px: the desktop layout, with text large enough to read in the landing page's column. 1024 x 1.171875 = 1200.
const VIEWPORT = { width: 1024, height: 680 };
const SCALE = 1.171875;

const SHOW: Record<L3, [string, string][]> = {
  en: [["ОРТ E2E staff", "ORT practice test, version 2"], ["ОРТ E2E", "ORT practice test"]],
  ky: [["ОРТ E2E staff", "ЖРТ сынамыгы, 2-вариант"], ["ОРТ E2E", "ЖРТ сынамыгы"]],
  ru: [["ОРТ E2E staff", "Пробный ОРТ, вариант 2"], ["ОРТ E2E", "Пробный ОРТ"]],
};

const landing = () => (seed() as unknown as { landing: { course_id: string; teacher: SeedUser; student: SeedUser } }).landing;

async function open(browser: Browser, user: SeedUser, lang: L3): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext({
    viewport: VIEWPORT, deviceScaleFactor: SCALE, locale: lang === "en" ? "en-US" : "ru-RU", timezoneId: "Asia/Bishkek", colorScheme: "light",
  });
  await ctx.route("**/api/v1/**", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const res = await route.fetch();
    let body = await res.text();
    for (const [from, to] of SHOW[lang]) body = body.split(from).join(to);
    await route.fulfill({ response: res, body });
  });
  const page = await ctx.newPage();
  await signIn(page, user);
  await page.addInitScript((l) => { window.localStorage.setItem("ort_preferred_language", l); }, lang);
  return { ctx, page };
}

async function shoot(page: Page, name: string, lang: L3): Promise<void> {
  await settle(page);
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(PNG_DIR, `${name}-${lang}.png`), animations: "disabled", caret: "hide" });
}

test.describe("landing page screens", () => {
  test.skip(!RECORD, "set RECORD_LANDING=1");
  test.describe.configure({ mode: "serial" });

  test.beforeAll(() => {
    fs.rmSync(PNG_DIR, { recursive: true, force: true });
    fs.mkdirSync(PNG_DIR, { recursive: true });
  });

  // before the exam below starts, so the home page shows the exam as not started
  for (const lang of LANGS) {
    test(`student dashboard ${lang}`, async ({ browser }) => {
      const { ctx, page } = await open(browser, landing().student, lang);
      await page.goto(`/${lang}/courses`);
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
      await shoot(page, "student-dashboard", lang);
      await ctx.close();
    });
  }

  test("exam player", async ({ browser }) => {
    const s = seed();
    const student = landing().student;
    let attempt = "";
    for (const lang of LANGS) {
      const { ctx, page } = await open(browser, student, lang);
      if (!attempt) {
        await page.goto(`/${lang}/courses/${s.course_id}/assessments/${s.exam.id}`);
        await page.getByRole("button", { name: tr(lang, "assessments.lobby.start"), exact: true }).click();
        await page.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);
        attempt = new URL(page.url()).pathname.replace(/^\/[a-z]{2}/, "");
      } else {
        await page.goto(`/${lang}${attempt}`);
      }
      await expect(page.getByTestId("player-top-bar")).toBeVisible();
      // mid-question: the first comparison question (only math, so it reads the same in every language) with an answer chosen
      await page.getByRole("radiogroup", { name: tr(lang, "player.answers") }).getByRole("radio").nth(1).click();
      await expect(page.getByTestId("player-top-bar").getByText(tr(lang, "player.save.saved"))).toBeVisible();
      await shoot(page, "exam-player", lang);
      await ctx.close();
    }
  });

  for (const lang of LANGS) {
    test(`teacher course ${lang}`, async ({ browser }) => {
      const { ctx, page } = await open(browser, landing().teacher, lang);
      await page.goto(`/${lang}/courses/${landing().course_id}`);
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
      await shoot(page, "teacher-course", lang);
      await ctx.close();
    });
  }

  test("convert to WebP", () => {
    const out = execFileSync("python3", [path.resolve(__dirname, "landing_webp.py"), PNG_DIR, OUT_DIR], { encoding: "utf-8" });
    console.log(out);
    expect(fs.readdirSync(OUT_DIR).filter((f) => f.endsWith(".webp"))).toHaveLength(LANGS.length * 3);
  });
});
