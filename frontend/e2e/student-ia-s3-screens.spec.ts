import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, seed, settle, signIn, tr } from "./helpers";
import { joinEightCourses } from "./hubCourses";

/**
 * Step 3a S3 (docs/phases/STUDENT_IA_DESIGN.md §2, §7.1-§7.3): screenshots of the global frame and the hub for the
 * orchestrator's UX check (ru, 375 and 1440): the hub with 0, 1 and 8 courses, «Мои курсы» with 8, the phone «Ещё»
 * sheet and a course page with the new sidebar. Not compared with a baseline. Runs only with
 * `STUDENT_IA_S3_SHOTS=<dir>` and in its own run (it joins the seed's many-course student to eight courses and keeps
 * them): `npx playwright test e2e/student-ia-s3-screens.spec.ts`. Names are the seed's fake ones.
 */

const OUT = process.env.STUDENT_IA_S3_SHOTS;
const L = "ru";
const WIDTHS = [375, 1440] as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);

async function shoot(page: Page, url: string, name: string) {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
    await page.goto(url);
    await settle(page);
    await page.waitForTimeout(400);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(OUT as string, `${name}-${width}.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
}

test.describe("global frame and hub screenshots (ru)", () => {
  test.skip(!OUT, "STUDENT_IA_S3_SHOTS is not set");

  test("hub 0 / 1 / 8, my courses, the Ещё sheet, a course page", async ({ page, browser }) => {
    test.setTimeout(300_000);
    fs.mkdirSync(OUT as string, { recursive: true });
    const s = seed();
    // 0 and 1 course (own browser contexts: each person's own device storage)
    for (const [user, name] of [[s.hub.empty, "home-0"], [s.hub.one, "home-1"]] as const) {
      const ctx = await browser.newContext({ locale: "ru-RU", timezoneId: "UTC" });
      const p = await ctx.newPage();
      await signIn(p, user);
      await shoot(p, `/${L}/home`, name);
      await ctx.close();
    }
    // 8 courses: an exam date on ORT (Russian), a lesson opened, an announcement
    const user = s.hub.many;
    const hub = await joinEightCourses(user);
    const date = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
    await api(s.admin, "PATCH", `/courses/${s.course_id}`, { exam_date: date });
    await api(s.admin, "POST", `/courses/${hub.maths}/announcements`, { title: "Разбор задач в субботу", body_md: "Встречаемся в 18:00.", publish: true });
    await signIn(page, user);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/${L}/courses/${hub.maths}/lessons`);
    await settle(page);
    await shoot(page, `/${L}/home`, "home-8");
    await shoot(page, `/${L}/courses`, "courses-8");
    await shoot(page, `/${L}/courses/${s.course_id}`, "course-ort-overview");
    await shoot(page, `/${L}/courses/${hub.teacher}`, "course-teacher-overview");
    // the phone «Ещё» sheet
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`/${L}/home`);
    await settle(page);
    await page.getByRole("navigation", { name: t("student.nav.tabBar") }).getByRole("button", { name: t("student.nav.more") }).click();
    await expect(page.getByRole("dialog", { name: t("student.nav.more") })).toBeVisible();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT as string, "more-sheet-375.png"), animations: "disabled", caret: "hide" });
  });
});
