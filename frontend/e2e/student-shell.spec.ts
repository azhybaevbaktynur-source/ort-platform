import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS } from "./helpers";

/**
 * Step 3a S3, S7 (docs/phases/STUDENT_IA_DESIGN.md §2.1, v3 V1, V5, V6): the global frame. One navigation: the sidebar
 * has Главная · Каталог (no course id in either, no exam switcher) and the «Мои курсы» rows; inside every course page
 * there is no second sidebar (the course tabs navigate the course); the phone bar Главная · Продолжить · Каталог · Ещё
 * is on every page (the «Ещё» sheet has no «Войти по коду»); «Продолжить» leads to the last place; the «Ещё» sheet opens and closes with Esc
 * (focus back on its button); nothing scrolls sideways at 375 px; people who teach keep the AppHeader, also on /home.
 * Read-only: no data changes.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const sidebar = (page: Page) => page.getByRole("navigation", { name: t("student.nav.label") });
const bar = (page: Page) => page.getByRole("navigation", { name: t("student.nav.tabBar") });

/** No second navigation inside a course: no course sidebar, no «Меню курса» drawer, one student menu. */
async function oneNavigation(page: Page, where: string) {
  await expect(page.getByRole("navigation", { name: t("courses.home.tabsLabel") }), `${where}: no course sidebar`).toHaveCount(0);
  await expect(page.getByRole("button", { name: t("courseNav.menu") }), `${where}: no course drawer`).toHaveCount(0);
  await expect(page.getByRole("group", { name: t("student.switcher.label") }), `${where}: no exam switcher`).toHaveCount(0);
}

test.describe("student frame (ru)", () => {
  test("desktop sidebar: two global links, the course rows, no switcher; one navigation in a course", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, s.students["vis-desktop-ru"]);
    await page.goto(`/${L}/home`);
    const nav = sidebar(page);
    await expect(nav).toBeVisible();
    await expect(nav.getByRole("link", { name: t("student.nav.home") })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: t("student.nav.home") })).toHaveAttribute("href", `/${L}/home`);
    // step 3a S7 (v3 V1): no «Мои курсы» link; the group label heads the course rows
    await expect(nav.locator(`a[href="/${L}/courses"]`)).toHaveCount(0);
    await expect(nav.getByRole("link", { name: t("student.nav.myCourses"), exact: true })).toHaveCount(0);
    await expect(nav.getByText(t("student.nav.myCourses"), { exact: true })).toBeVisible();
    await expect(nav.getByRole("link", { name: t("student.nav.catalog") })).toHaveAttribute("href", `/${L}/courses/catalog`);
    for (const key of ["student.nav.tests", "student.nav.analytics", "student.nav.saved", "student.nav.practice", "student.nav.lessonsGroup"]) {
      await expect(nav.getByText(t(key), { exact: true }), `no global ${key}`).toHaveCount(0);
    }
    await expect(bar(page)).toBeHidden();
    await oneNavigation(page, "/home");
    if (process.env.S2_SHOTS) {
      for (const width of [375, 1440, 1920]) {
        await page.setViewportSize({ width, height: 900 });
        await settle(page);
        await page.screenshot({ path: path.join(process.env.S2_SHOTS, `home-student-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
      }
      await page.setViewportSize(VIEWPORTS.desktop);
    }
    // the course row opens the course (Обзор); inside it the row is current and the course tabs navigate
    const row = nav.locator(`a[href^="/${L}/courses/${s.course_id}"]`);
    await row.click();
    await page.waitForURL(new RegExp(`/${L}/courses/${s.course_id}$`));
    await expect(row).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("navigation", { name: t("course.tabs.label") })).toBeVisible();
    await oneNavigation(page, "Обзор");
    // the lobby: inside the student frame, its navigation, no course sidebar
    await page.goto(`/${L}/courses/${s.course_id}/assessments/${s.exam.id}`);
    await expect(page.getByRole("heading", { name: "ОРТ E2E", exact: true })).toBeVisible();
    await expect(nav).toBeVisible();
    await oneNavigation(page, "lobby");
  });

  test("a general course: no second sidebar on any course page", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, s.modules.student);
    const base = `/${L}/courses/${s.modules.course_id}`;
    for (const p of ["", "/lessons", "/tests", "/announcements", "/files"]) {
      await page.goto(`${base}${p}`);
      await expect(sidebar(page)).toBeVisible();
      await expect(page.getByRole("navigation", { name: t("course.tabs.label") })).toBeVisible();
      await oneNavigation(page, `${base}${p}`);
      await expect(page.getByRole("navigation", { name: t("student.nav.label") })).toHaveCount(1);
    }
  });

  test("desktop sidebar: equal vertical rhythm between the global links (1440, 1920)", async ({ page }) => {
    const s = seed();
    await signIn(page, s.students["vis-desktop-ru"]);
    for (const width of [1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/${L}/home`);
      const nav = sidebar(page);
      await expect(nav).toBeVisible();
      await settle(page);
      // step 3a S7 (v3 V1): two global links (Главная · Каталог), then the «Мои курсы» group; the rows of one group
      // keep one rhythm (the gap between the two links is the list's own item gap, 0-8 px)
      const boxes = (await nav.getByRole("link").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; }))).slice(0, 2);
      expect(boxes.length).toBe(2);
      const gap = boxes[1].top - boxes[0].bottom;
      expect(gap).toBeGreaterThanOrEqual(0);
      expect(gap).toBeLessThanOrEqual(8);
      if (process.env.F1_SHOTS) await nav.screenshot({ path: path.join(process.env.F1_SHOTS, `sidebar-${width}.png`) });
    }
  });

  test("phone: the bar on every page, «Продолжить» to the last place, the «Ещё» sheet", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.phone);
    await signIn(page, s.students["vis-phone-ru"]);
    const c = `/${L}/courses/${s.course_id}`;
    for (const url of [`/${L}/home`, `/${L}/courses`, `/${L}/courses/catalog`, c, `${c}/tests`, `${c}/assessments/${s.exam.id}`, `/${L}/pro`]) {
      await page.goto(url);
      const b = bar(page);
      await expect(b, url).toBeVisible();
      // step 3a S7 (v3 V6): Главная · Продолжить · Каталог · Ещё
      await expect(b.getByRole("link"), url).toHaveText([t("student.nav.home"), t("student.nav.continue"), t("student.nav.catalog")]);
      await expect(b.getByRole("button", { name: t("student.nav.more") })).toBeVisible();
      await oneNavigation(page, url);
      await settle(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), url).toBeLessThanOrEqual(0);
    }
    // the last page inside the course was the lobby: «Продолжить» opens it (an attempt URL is never remembered)
    const cont = bar(page).getByRole("link", { name: t("student.nav.continue"), exact: true });
    await expect(cont).toHaveAttribute("href", `${c}/assessments/${s.exam.id}`);
    await page.goto(`${c}/tests`);
    await expect(cont).toHaveAttribute("href", `${c}/tests`);
    await expect(cont).toHaveAttribute("aria-current", "page"); // it leads to this very page
    await bar(page).getByRole("link", { name: t("student.nav.home"), exact: true }).click();
    await page.waitForURL(new RegExp(`/${L}/home$`));
    await cont.click();
    await page.waitForURL(new RegExp(`${c}/tests$`));
    const more = bar(page).getByRole("button", { name: t("student.nav.more") });
    await more.click();
    const sheet = page.getByRole("dialog", { name: t("student.nav.more") });
    await expect(sheet).toBeVisible();
    await expect(sheet.locator(`a[href^="${c}"]`)).toHaveCount(1); // the «Мои курсы» row
    await expect(sheet.locator(`a[href="/${L}/courses/join"]`)).toHaveCount(0); // V5: «Войти по коду» only in the catalog
    await expect(sheet.getByRole("button", { name: t("common.logout") })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(more).toBeFocused();
  });

  test("people who teach keep the AppHeader, also on /home", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, s.admin);
    await page.goto(`/${L}/courses`);
    await expect(page.getByRole("navigation", { name: t("shell.areas.label") })).toBeVisible();
    await expect(page.getByRole("navigation", { name: t("student.nav.label") })).toHaveCount(0);
    await page.goto(`/${L}/home`);
    await page.waitForURL(new RegExp(`/${L}/courses$`));
    await expect(page.locator("[data-shell]").first()).toHaveAttribute("data-shell", "app");
    await expect(page.getByRole("navigation", { name: t("student.nav.label") })).toHaveCount(0);
    // an old link: ?view=teaching opens the same list without the parameter
    await page.goto(`/${L}/courses?view=teaching`);
    await page.waitForURL(new RegExp(`/${L}/courses$`));
  });

  test("old links: /courses and ?view=learning open the hub for a learner, #catalog the catalog", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, s.students["vis-desktop-ru"]);
    await page.goto(`/${L}/courses?view=learning`);
    await page.waitForURL(new RegExp(`/${L}/home$`));
    await page.goto(`/${L}/courses`);
    await page.waitForURL(new RegExp(`/${L}/home$`));
    await page.goto(`/${L}/courses#catalog`);
    await page.waitForURL(new RegExp(`/${L}/courses/catalog$`));
  });
});
