import { expect, test } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS } from "./helpers";
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

test("no mascot in the exam player", async ({ browser }) => {
  test.setTimeout(120_000);
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, seed().modules.ort_student);
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
