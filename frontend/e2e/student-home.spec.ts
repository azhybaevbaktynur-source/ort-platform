import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { seed, settle, signIn, tr } from "./helpers";

/**
 * Student UI U3 (docs/phases/STUDENT_UI_DESIGN.md §3.1): the home. A student of an exam-prep course without results
 * (`access.home_student` of the S3 course: a free and a paid exam, no pass, never takes a test) gets the greeting, the Next card with the page's only
 * primary button, the score tiles, the streak strip, the gold unlock card, the section card's empty state and the
 * courses row; a student of a general course only keeps the dashboard ("Панель"), whose course cards stay at least
 * 16rem wide at 1920 px. Read-only. Screens at 375 / 1440 / 1920 (ru) go to $U3_SHOTS when set.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const WIDTHS = [375, 1440, 1920] as const;

async function noOverflowAndShoot(page: Page, name: string) {
  const dir = process.env.U3_SHOTS;
  if (dir) fs.mkdirSync(dir, { recursive: true });
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal scroll at ${width}px (${name})`).toBeLessThanOrEqual(0);
    if (dir) await page.screenshot({ path: path.join(dir, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.describe("student home (ru)", () => {
  test("exam-prep home without results: greeting, Next, scores, streak, unlock card, courses", async ({ page }) => {
    const s = seed();
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, s.access!.home_student); // own user: access.spec.ts gives `access.student` results first
    await page.goto(`/${L}/courses`);
    const greeting = page.getByRole("heading", { level: 1 });
    await expect(greeting).toContainText("Access"); // the first word of the display name
    const next = page.getByRole("region", { name: t("examPrep.next.title") });
    await expect(next).toContainText("ОРТ S3 бесплатный");
    await expect(next.getByRole("link", { name: t("examPrep.next.action.start") })).toBeVisible();
    await expect(page.getByText(t("home.prep.noDate"))).toBeVisible();
    const scores = page.getByRole("region", { name: t("home.prep.score.title") });
    await expect(scores).toContainText(t("examPrep.goal.noScore"));
    await expect(scores.getByRole("button", { name: t("examPrep.goal.setTarget") })).toBeVisible();
    const streak = page.getByRole("region", { name: t("home.prep.streak.title") });
    await expect(streak).toContainText(t("home.prep.streak.none"));
    await expect(streak.getByRole("listitem")).toHaveCount(7);
    const unlock = page.getByRole("region", { name: t("home.prep.unlock.title") });
    await expect(unlock.getByRole("link", { name: t("access.needsPassLink") })).toHaveAttribute("href", `/${L}/unlock`);
    await expect(page.getByRole("region", { name: t("examPrep.sections.title") })).toContainText(t("examPrep.sections.empty"));
    const courses = page.getByRole("region", { name: t("home.courses.title") });
    await expect(courses.locator(`a[href="/${L}/courses/${s.access!.course_id}"]`)).toHaveCount(1);
    await expect(courses.getByRole("link", { name: t("home.prep.addCourse") })).toBeVisible();
    // one primary action: the platform courses' join buttons are secondary here
    const platform = page.getByRole("region", { name: t("home.platform.title") });
    if (await platform.count()) {
      await expect(platform.getByRole("button", { name: t("catalog.join") }).first()).not.toHaveClass(/bg-brand-600/);
    }
    await noOverflowAndShoot(page, "home-prep-locked");
  });

  test("general course only: the dashboard, course cards not thin at 1920 px", async ({ page }) => {
    const s = seed();
    await page.setViewportSize({ width: 1920, height: 900 });
    await signIn(page, s.quiz_editor.student);
    await page.goto(`/${L}/courses`);
    await expect(page.getByRole("heading", { level: 1, name: t("home.dashboard") })).toBeVisible();
    const card = page.getByRole("region", { name: t("home.courses.title") }).locator("li").first();
    await expect(card).toBeVisible();
    expect((await card.boundingBox())!.width).toBeGreaterThanOrEqual(256);
    await expect(page.getByRole("region", { name: t("examPrep.next.title") })).toHaveCount(0);
    await noOverflowAndShoot(page, "home-general");
  });
});
