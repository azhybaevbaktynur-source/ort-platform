import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { seed, settle, signIn, tr } from "./helpers";

/**
 * Student UI U3 (docs/phases/STUDENT_UI_DESIGN.md §3.1): the home. A student of an exam-prep course without results
 * (`access.home_student` of the S3 course: a free and a paid exam, no pass, never takes a test) gets the greeting, the Next card with the page's only
 * primary button (brand blue; gold is the only accent), U9: the slim score line, the streak strip, the short gold unlock card, no
 * section card, no date message, no course grid and no getting-started card; the catalog, the code and leaving are
 * in the shell's exam sheet; a student of a general course only keeps the dashboard ("Панель"), whose course cards stay at least
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
  test("exam-prep home without results: greeting, Next, score line, streak, unlock card, exam sheet", async ({ page }) => {
    const s = seed();
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, s.access!.home_student); // own user: access.spec.ts gives `access.student` results first
    await page.goto(`/${L}/courses`);
    const greeting = page.getByRole("heading", { level: 1 });
    await expect(greeting).toContainText("Access"); // the first word of the display name
    const next = page.getByRole("region", { name: t("examPrep.next.title") });
    await expect(next).toContainText("ОРТ S3 бесплатный");
    const start = next.getByRole("link", { name: t("examPrep.next.action.start") });
    await expect(start).toBeVisible();
    await expect(start).toHaveClass(/bg-brand-600/); // owner 2026-11-07: one blue primary, no violet accent
    await expect(page.getByText(t("examPrep.goal.daysLabel"), { exact: true })).toHaveCount(0); // U9 (review 12): no date, no countdown
    // U9 (review 4): before the first result, score and goal are one slim line with the edit button
    const scores = page.getByRole("region", { name: t("home.prep.score.title") });
    await expect(scores).toContainText(t("examPrep.goal.latestLabel"));
    await expect(scores).toContainText(t("examPrep.goal.targetLabel"));
    await expect(scores.getByRole("button", { name: t("examPrep.goal.setTarget") })).toBeVisible();
    const streak = page.getByRole("region", { name: t("progress.analytics.tiles.streak") });
    await expect(streak).toContainText(t("home.prep.streak.none"));
    await expect(streak.getByRole("listitem")).toHaveCount(7);
    const unlock = page.getByRole("region", { name: t("home.prep.unlock.title") });
    await expect(unlock.getByRole("link", { name: t("access.needsPassLink") })).toHaveAttribute("href", `/${L}/pro`);
    await expect(unlock.getByRole("listitem")).toHaveCount(0); // the bullets stay on /pro
    await expect(page.getByRole("region", { name: t("examPrep.sections.title") })).toHaveCount(0);
    await expect(page.getByRole("region", { name: t("home.courses.title") })).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 2, name: t("student.nav.gettingStarted") })).toHaveCount(0);
    // one primary action: the platform courses' join buttons are secondary here
    const platform = page.getByRole("region", { name: t("home.platform.title") });
    if (await platform.count()) {
      await expect(platform.getByRole("button", { name: t("catalog.join") }).first()).not.toHaveClass(/bg-brand-600/);
    }
    await noOverflowAndShoot(page, "home-prep-locked");
    // U9 (review 1, 2): the exam sheet (sidebar "+") has the catalog, the code and leaving the course
    await page.getByRole("button", { name: t("student.switcher.add") }).click();
    const sheet = page.getByRole("dialog", { name: t("student.switcher.label") });
    await expect(sheet.getByRole("link", { name: t("home.prep.addCourse") })).toHaveAttribute("href", `/${L}/courses/catalog`);
    await expect(sheet.getByRole("link", { name: t("home.primary.join") })).toHaveAttribute("href", `/${L}/courses/join`);
    await sheet.getByRole("button", { name: t("courses.home.leave") }).click();
    const confirm = page.getByRole("alertdialog", { name: t("courses.home.leaveTitle") });
    await expect(confirm).toBeVisible();
    await confirm.getByRole("button", { name: t("ui.cancel") }).click(); // read-only: never leaves
    await expect(confirm).toBeHidden();
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
