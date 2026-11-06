import path from "node:path";
import { expect, test } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS } from "./helpers";

/**
 * Student UI U2 (docs/phases/STUDENT_UI_DESIGN.md §2): the student shell. A student of the seeded ORT course gets the
 * navy sidebar (desktop) or the top bar + bottom tab bar (phone) with `aria-current` on the page's link, the "More"
 * sheet opens and closes with Esc (focus back on its button), nothing scrolls sideways at 375 px; the ORT lobby keeps
 * the old frame (no student navigation), and a teacher's Teaching area keeps the AppHeader. Read-only: no data changes.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);

test.describe("student shell (ru)", () => {
  test("desktop sidebar: links, aria-current, lobby keeps the old frame", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, s.students["vis-desktop-ru"]);
    await page.goto(`/${L}/courses`);
    const nav = page.getByRole("navigation", { name: t("student.nav.label") });
    await expect(nav).toBeVisible();
    await expect(nav.getByRole("link", { name: t("student.nav.home") })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("navigation", { name: t("student.nav.tabBar") })).toBeHidden();
    if (process.env.S2_SHOTS) {
      // UX check: the home of a student with an exam course at 375 / 1440 / 1920 (not compared)
      for (const width of [375, 1440, 1920]) {
        await page.setViewportSize({ width, height: 900 });
        await settle(page);
        await page.screenshot({ path: path.join(process.env.S2_SHOTS, `home-student-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
      }
      await page.setViewportSize(VIEWPORTS.desktop);
    }
    // the Тесты page (U4): "Тесты" is current; no course sidebar inside an exam-prep course
    await nav.getByRole("link", { name: t("student.nav.tests") }).click();
    await page.waitForURL(new RegExp(`/${L}/courses/${s.course_id}/tests$`));
    await expect(nav.getByRole("link", { name: t("student.nav.tests") })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("navigation", { name: t("courses.home.tabsLabel") })).toHaveCount(0);
    // the lobby: the AppHeader frame, no student navigation
    await page.goto(`/${L}/courses/${s.course_id}/assessments/${s.exam.id}`);
    // the lobby's own heading (not "Start": another spec may have used this student's one attempt)
    await expect(page.getByRole("heading", { name: "ОРТ E2E", exact: true })).toBeVisible();
    await expect(page.getByRole("navigation", { name: t("student.nav.label") })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: t("student.nav.tabBar") })).toHaveCount(0);
  });

  test("phone: tab bar, More sheet, no horizontal scroll", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.phone);
    await signIn(page, s.students["vis-phone-ru"]);
    await page.goto(`/${L}/courses/${s.course_id}`);
    await page.waitForURL(new RegExp(`/${L}/courses/${s.course_id}/tests$`)); // U4: the course page redirects
    const bar = page.getByRole("navigation", { name: t("student.nav.tabBar") });
    await expect(bar).toBeVisible();
    await expect(bar.getByRole("link", { name: t("student.nav.tests") })).toHaveAttribute("aria-current", "page");
    await settle(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    const more = bar.getByRole("button", { name: t("student.nav.more") });
    await more.click();
    const sheet = page.getByRole("dialog", { name: t("student.nav.more") });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("link", { name: t("student.nav.mistakes") })).toBeVisible();
    await expect(sheet.getByRole("button", { name: t("common.logout") })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(more).toBeFocused();
  });

  test("a teacher's Teaching area keeps the AppHeader", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, s.admin);
    await page.goto(`/${L}/courses?view=teaching`);
    await expect(page.getByRole("navigation", { name: t("shell.areas.label") })).toBeVisible();
    await expect(page.getByRole("navigation", { name: t("student.nav.label") })).toHaveCount(0);
  });
});
