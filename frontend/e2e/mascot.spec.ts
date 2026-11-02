import { expect, test } from "@playwright/test";
import { sectionCounts, seed, settle, signIn, tr, VIEWPORTS } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * Mascot placement (docs: UX rework, slice 2): the 404 page shows a decorative cub with a link home, the exam player
 * never shows it, and on a 375 px phone an empty state keeps its action button on the first screen.
 * Run: same harness as the ORT specs (docs/phases/ORT_BASELINE/README.md "Run").
 */

const mascotImgs = (page: import("@playwright/test").Page) => page.locator('img[src*="/mascot/"]');

test("404 page: mascot with empty alt and a link home", async ({ page }) => {
  const res = await page.goto("/ru/this-page-does-not-exist");
  expect(res?.status()).toBe(404);
  const img = mascotImgs(page).first();
  await expect(img).toBeVisible();
  await expect(img).toHaveAttribute("alt", "");
  const home = page.getByRole("link", { name: tr("ru", "mascot.notFound.home"), exact: true });
  await expect(home).toHaveAttribute("href", "/ru");
});

let resultUrl = "";

test("no mascot in the exam player", async ({ browser }) => {
  test.setTimeout(120_000);
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, seed().students["mascot-player-ru"]);
  const exam = new OrtExam(page, "ru");
  await exam.openLobby();
  expect(await mascotImgs(page).count()).toBe(0);
  await exam.start();
  await settle(page);
  await expect(exam.topBar()).toBeVisible();
  expect(await mascotImgs(page).count()).toBe(0);
  await ctx.close();
});

test("phone: the empty state's action is on the first screen", async ({ browser }) => {
  test.setTimeout(120_000);
  const { teacher } = seed().quiz_editor;
  const headers = { Authorization: `Bearer ${teacher.token}`, "Content-Type": "application/json" };
  const r = await fetch(`${seed().api}/api/v1/courses`, {
    method: "POST", headers, body: JSON.stringify({ title: { ru: "Маскот E2E" }, languages: ["ru"], default_language: "ru" }),
  });
  expect(r.status).toBeLessThan(300);
  const course = await r.json();
  const ctx = await browser.newContext({ viewport: VIEWPORTS.phone, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, teacher);
  await page.goto(`/ru/courses/${course.id}/announcements`);
  const empty = page.locator(".border-dashed").filter({ hasText: tr("ru", "announcements.empty") });
  await expect(empty).toBeVisible();
  await expect(empty.locator('img[src*="/mascot/"]')).toHaveCount(1);
  const button = empty.getByRole("link", { name: tr("ru", "announcements.new") });
  await expect(button).toBeVisible();
  const box = await button.boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(VIEWPORTS.phone.height);
  await ctx.close();
});

test("result page: encouraging on a low score, celebrating on a high one, outside the result card", async ({ browser }) => {
  test.setTimeout(240_000);
  const out = process.env.UX_SCREENS_DIR;
  for (const viewport of [{ width: 375, height: 812 }, VIEWPORTS.desktop, { width: 1920, height: 1080 }]) {
    const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const page = await ctx.newPage();
    await signIn(page, seed().students["mascot-result-ru"]);
    if (viewport.width === 375) {
      const exam = new OrtExam(page, "ru");
      await exam.openLobby();
      await exam.start();
      for (const pos of [1, 2, 3, 4]) await exam.skipSection(pos);
      await exam.openSubmit({ unanswered: sectionCounts()[4], flagged: 0 });
      await exam.confirmSubmit();
      resultUrl = page.url();
    } else {
      await page.goto(resultUrl);
    }
    await settle(page);
    const row = page.getByTestId("result-mascot");
    await expect(row).toContainText(tr("ru", "mascot.result.encourage"));
    await expect(row.locator("img")).toHaveAttribute("alt", "");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    if (out) await page.screenshot({ path: `${out}/result-low-${viewport.width}.png` });

    await page.route("**/api/v1/attempts/*/result", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      await route.fulfill({ response: res, json: { ...body, raw_score: body.points_possible } });
    });
    await page.reload();
    await settle(page);
    await expect(page.getByTestId("result-mascot")).toContainText(tr("ru", "mascot.result.proud"));
    if (out) await page.screenshot({ path: `${out}/result-high-${viewport.width}.png` });
    await ctx.close();
  }
});
