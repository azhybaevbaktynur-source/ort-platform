import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, seed, settle, signIn, tr, VIEWPORTS } from "./helpers";
import { joinEightCourses } from "./hubCourses";
import { chooseCoursesHref } from "../src/lib/lms/chooseCourses";

/**
 * Step 3a S3 (docs/phases/STUDENT_IA_DESIGN.md §2.2, §2.3, §7.1-§7.3): Главная `/home` is a hub only. With no course:
 * the greeting and the empty state («Выбрать курсы», «Войти по коду»), no to-do; the sidebar's «Выбрать курсы» row and
 * the phone bar's «Продолжить» lead to the choose step. With one course: the «Продолжить» card (the course's Обзор,
 * then the remembered last place), one group with one card, «К выполнению». With eight courses: groups ОРТ · НЦТ ·
 * Другие курсы (4 cards + «Все курсы ОРТ (5)»), the continue fallback order (exam Обзор → next lesson → in-progress
 * attempt; a remembered place first), the to-do with an announcement row, «Мои курсы» `/courses` with every card.
 * The hub is one API round on a fresh load (P2). Screens at 375 / 1440 / 1920 (ru) go to $U3_SHOTS when set.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const WIDTHS = [375, 1440, 1920] as const;

async function noOverflowAndShoot(page: Page, name: string, dir = process.env.U3_SHOTS) {
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

const continueCard = (page: Page) => page.getByRole("region", { name: t("home.hub.continue") });
const sidebar = (page: Page) => page.getByRole("navigation", { name: t("student.nav.label") });

/** Forget this device's last place (the server fallback decides again). */
async function forgetPlace(page: Page, userId: string) {
  await page.evaluate((id) => { window.localStorage.removeItem(`ort_last_place:${id}`); }, userId);
}

test.describe("student hub (ru)", () => {
  test("no course: the empty state, «Выбрать курсы» everywhere, no to-do", async ({ page }) => {
    const s = seed();
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, s.hub.empty);
    await page.goto(`/${L}/home`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Айгерим"); // the first word of the display name
    await expect(page.getByText(t("home.hub.emptyTitle"))).toBeVisible();
    const main = page.locator("main#main");
    await expect(main.getByRole("link", { name: t("home.hub.choose") })).toHaveAttribute("href", chooseCoursesHref(L));
    await expect(main.getByRole("link", { name: t("home.hub.join") })).toHaveAttribute("href", `/${L}/courses/join`);
    await expect(page.getByRole("heading", { level: 2, name: t("home.todo.title") })).toHaveCount(0);
    await expect(continueCard(page)).toHaveCount(0);
    await expect(sidebar(page).getByRole("link", { name: t("student.nav.chooseCourses") })).toHaveAttribute("href", chooseCoursesHref(L));
    await expect(sidebar(page).getByRole("link", { name: t("student.nav.home") })).toHaveAttribute("aria-current", "page");
    await noOverflowAndShoot(page, "hub-empty");
    await page.setViewportSize(VIEWPORTS.phone);
    const bar = page.getByRole("navigation", { name: t("student.nav.tabBar") });
    await expect(bar.getByRole("link", { name: t("student.nav.continue") })).toHaveAttribute("href", chooseCoursesHref(L));
  });

  test("one course: the continue card (Обзор, then the last place), one group, the to-do", async ({ page }) => {
    const s = seed();
    const user = s.hub.one;
    await page.setViewportSize(VIEWPORTS.desktop);
    await signIn(page, user);
    await page.goto(`/${L}/home`);
    const card = continueCard(page);
    // a fresh student: the course's next step, not its Обзор: the hub's main button starts the test
    const startTest = card.getByRole("link", { name: t("home.hub.step.start") });
    await expect(startTest).toHaveAttribute("href", new RegExp(`^/${L}/courses/${s.course_id}/assessments/[^/]+$`));
    await expect(card).not.toContainText(t("home.hub.overview"));
    await expect(card.getByRole("link").first()).toHaveClass(/bg-brand-600/); // the page's one primary button
    const courses = page.getByRole("region", { name: t("home.hub.coursesTitle") });
    await expect(courses.getByRole("heading", { level: 3 })).toHaveText([`${t("home.hub.groups.ort")} (1)`]);
    await expect(courses.getByRole("listitem")).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 2, name: t("home.todo.title") })).toBeVisible();
    // no test list, no results list, no statistics on the hub
    for (const key of ["examPrep.next.title", "home.results.title", "examPrep.sections.title", "progress.analytics.tiles.streak"]) {
      await expect(page.getByRole("region", { name: t(key) })).toHaveCount(0);
    }
    await expect(sidebar(page).getByRole("link", { name: /ОРТ/ })).toHaveCount(1); // one «Мои курсы» row
    await noOverflowAndShoot(page, "hub-one");
    // the last place wins once the student opened a tab
    await page.goto(`/${L}/courses/${s.course_id}/tests`);
    await expect(page.getByRole("navigation", { name: t("course.tabs.label") })).toBeVisible();
    await sidebar(page).getByRole("link", { name: t("student.nav.home") }).click();
    await page.waitForURL(new RegExp(`/${L}/home$`));
    await expect(card.getByRole("link", { name: t("home.hub.open") })).toHaveAttribute("href", `/${L}/courses/${s.course_id}/tests`);
    await expect(card).toContainText(t("home.hub.place.tests"));
    // ...and the sidebar row reopens that tab
    await expect(sidebar(page).getByRole("link", { name: /ОРТ/ })).toHaveAttribute("href", `/${L}/courses/${s.course_id}/tests`);
  });

  test("eight courses: groups, the continue fallback order, the to-do, «Мои курсы»", async ({ page }) => {
    test.setTimeout(240_000);
    const s = seed();
    const user = s.hub.many;
    const hub = await joinEightCourses(user);
    try {
      await api(s.admin, "POST", `/courses/${hub.maths}/announcements`, { title: "Разбор задач в субботу", body_md: "Встречаемся в 18:00.", publish: true });
      const homeAnswer = await api(user, "GET", "/me/home");
      type Step = { kind: string; assessment_id: string | null; assignment_id: string | null } | null;
      const exam = (homeAnswer.courses as { id: string; student_layout?: string; next_step?: Step }[]).find((c) => c.student_layout === "exam_prep")!;
      const newestExam = exam.id;
      // the newest exam course's Обзор stands for its next step when it has one (a test to start)
      const fallback3 = exam.next_step?.kind === "start" && exam.next_step.assessment_id
        ? { href: `/${L}/courses/${newestExam}/assessments/${exam.next_step.assessment_id}`, name: t("home.hub.step.start") }
        : { href: `/${L}/courses/${newestExam}`, name: t("home.hub.open") };

      await page.setViewportSize(VIEWPORTS.desktop);
      await signIn(page, user);
      await page.goto(`/${L}/home`);
      const courses = page.getByRole("region", { name: t("home.hub.coursesTitle") });
      await expect(courses.getByRole("heading", { level: 3 })).toHaveText([
        `${t("home.hub.groups.ort")} (5)`, `${t("home.hub.groups.nct")} (2)`, `${t("home.hub.groups.other")} (1)`,
      ]);
      const ort = page.getByRole("region", { name: new RegExp(`^${t("home.hub.groups.ort")}`) });
      await expect(ort.getByRole("listitem")).toHaveCount(4);
      await expect(ort.getByRole("link", { name: t("home.hub.allInGroup.ort", { n: 5 }) })).toHaveAttribute("href", `/${L}/courses#ort`);
      await expect(page.getByRole("region", { name: new RegExp(`^${t("home.hub.groups.nct")}`) }).getByRole("listitem")).toHaveCount(2);
      await expect(courses.getByRole("link", { name: t("home.hub.addCourse") })).toHaveAttribute("href", chooseCoursesHref(L));
      // the sidebar: 6 rows + «Все курсы (8)»
      const all = sidebar(page).getByRole("link", { name: t("student.nav.allCourses", { n: 8 }) });
      await expect(all).toHaveAttribute("href", `/${L}/courses`);
      // the to-do across courses, with the announcement row
      const todo = page.locator('section[aria-labelledby="home-todo"]');
      await expect(todo.getByRole("link", { name: /Разбор задач в субботу/ })).toHaveAttribute("href", `/${L}/courses/${hub.maths}/announcements`);

      // continue fallback 3: nothing remembered, no attempt, no lesson state: the newest exam course's Обзор
      const card = continueCard(page);
      await expect(card.getByRole("link", { name: fallback3.name })).toHaveAttribute("href", fallback3.href);
      // fallback 2: the next lesson (the module states are stored once the student opened the course)
      await page.goto(`/${L}/courses/${hub.maths}/lessons`);
      await expect(page.getByRole("navigation", { name: t("course.tabs.label") })).toBeVisible();
      await settle(page);
      await forgetPlace(page, user.profile.id);
      await page.goto(`/${L}/home`);
      const lesson = card.getByRole("link", { name: t("home.hub.continueLesson") });
      await expect(lesson).toHaveAttribute("href", new RegExp(`^/${L}/courses/${hub.maths}/modules/${hub.mathsModule}/items/`));
      await expect(card).toContainText("Урок 1 · Что такое процент");
      // the lesson course attached to ORT (Russian): once, in the ORT group, its own next step into the lesson
      // (replaces the old home's «Уроки» section and «Продолжить урок» strip)
      const mathsCard = ort.getByRole("listitem").filter({ hasText: "ОРТ: Математика" });
      await expect(mathsCard).toHaveCount(1);
      await expect(page.locator("main#main").getByRole("heading", { name: "ОРТ: Математика" })).toHaveCount(1);
      await expect(mathsCard).toContainText(t("home.hub.card.forExam", { exam: "" }).trim());
      await expect(mathsCard.getByRole("link", { name: t("home.hub.step.continue_lesson") }))
        .toHaveAttribute("href", new RegExp(`^/${L}/courses/${hub.maths}/modules/${hub.mathsModule}/items/`));
      // fallback 1: an attempt in progress beats the lesson
      const attempt = await api(user, "POST", `/courses/${s.course_id}/assessments/${s.exam.id}/attempts`, { language: "ru" });
      await page.reload();
      await expect(card.getByRole("link", { name: t("home.hub.continueTest") })).toHaveAttribute("href", `/${L}/courses/${s.course_id}/attempts/${attempt.id}`);
      await expect(todo).toContainText(t("home.todo.inProgress"));
      // the remembered place beats every fallback; the sidebar puts that course first
      await page.goto(`/${L}/courses/${hub.teacher}`);
      await expect(page.getByRole("navigation", { name: t("course.tabs.label") })).toBeVisible();
      await sidebar(page).getByRole("link", { name: t("student.nav.home") }).click();
      await page.waitForURL(new RegExp(`/${L}/home$`));
      // (its Обзор stands for the course's next step when it has one: either way the button stays in that course)
      await expect(card.getByRole("link")).toHaveAttribute("href", new RegExp(`^/${L}/courses/${hub.teacher}(/|$)`));
      const hrefs = await sidebar(page).locator("a[href]").evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? ""));
      const courseRows = hrefs.filter((h) => /^\/ru\/courses\/[^/]+/.test(h) && !h.startsWith("/ru/courses/catalog"));
      expect(courseRows[0], "the course opened last is the first row").toBe(`/${L}/courses/${hub.teacher}`);
      expect(courseRows.length).toBe(6);
      await noOverflowAndShoot(page, "hub-eight");

      // «Мои курсы»: every card, grouped, with the anchors; the header actions
      await all.click();
      await page.waitForURL(new RegExp(`/${L}/courses$`));
      await expect(page.getByRole("heading", { level: 1, name: t("courses.mine.title") })).toBeVisible();
      await expect(page.locator("main#main section#ort").getByRole("listitem")).toHaveCount(5);
      await expect(page.locator("main#main section#nct").getByRole("listitem")).toHaveCount(2);
      await expect(page.locator("main#main section#other").getByRole("listitem")).toHaveCount(1);
      await expect(page.locator("main#main").getByRole("link", { name: t("courses.mine.addCourse") })).toHaveAttribute("href", chooseCoursesHref(L));
      await expect(page.locator("main#main").getByRole("link", { name: t("courses.mine.join") })).toHaveAttribute("href", `/${L}/courses/join`);
      // the lesson course attached to the exam names it
      await expect(page.locator("main#main section#ort")).toContainText(`${t("home.hub.card.forExam", { exam: "" }).trim()}`);
      await noOverflowAndShoot(page, "my-courses-eight");
    } finally {
      await hub.cleanup();
    }
  });

  // PERFORMANCE_AUDIT P2: a fresh load of the hub is one API round: the shell's bootstrap carries `/me/home` and the
  // cross-course activity (`?include=home`); none of them is asked again, on a cold load or a reload
  test("P2: a fresh load of the hub is one API round (the bootstrap brings the home)", async ({ page }) => {
    const s = seed();
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, s.access!.home_student);
    const apiBase = `${s.api}/api/v1/`;
    type Seen = { path: string; start: number; end: number };
    let seen: Seen[] = [];
    const byReq = new Map<object, Seen>();
    page.on("request", (r) => {
      if (!r.url().startsWith(apiBase) || r.method() === "OPTIONS") return;
      const row = { path: r.url().slice(apiBase.length - 1), start: Date.now(), end: Infinity };
      byReq.set(r, row);
      seen.push(row);
    });
    const finish = (r: object) => { const row = byReq.get(r); if (row) row.end = Date.now(); };
    page.on("requestfinished", finish);
    page.on("requestfailed", finish);
    const card = continueCard(page);
    const todo = page.getByRole("heading", { level: 2, name: t("home.todo.title") });
    for (const load of ["cold", "reload"] as const) {
      seen = [];
      if (load === "cold") await page.goto(`/${L}/home`); else await page.reload();
      await expect(card).toContainText("ОРТ S3 E2E");
      await expect(todo).toBeVisible();
      const content = Date.now();
      await settle(page);
      const boots = seen.filter((r) => r.path.startsWith("/me/bootstrap"));
      expect(boots.map((r) => r.path), `${load}: one bootstrap, with the home`).toEqual([expect.stringContaining("include=home")]);
      const own = seen.filter((r) => /^\/me\/home(\?|$)|\/exam-prep(\?|$)|\/my\/activity/.test(r.path)).map((r) => r.path);
      expect(own, `${load}: the hub asked nothing of its own`).toEqual([]);
      // one round before the first content: nothing that started before it waited for another API answer
      const before = seen.filter((r) => r.start <= content);
      const chained = before.filter((r) => before.some((o) => o !== r && o.end <= r.start)).map((r) => r.path);
      expect(chained, `${load}: requests asked after another API answer, before the first content`).toEqual([]);
    }
  });

  test("general course only: «Другие курсы», cards not thin at 1920 px", async ({ page }) => {
    const s = seed();
    await page.setViewportSize({ width: 1920, height: 900 });
    await signIn(page, s.quiz_editor.student);
    await page.goto(`/${L}/home`);
    const courses = page.getByRole("region", { name: t("home.hub.coursesTitle") });
    await expect(courses.getByRole("heading", { level: 3, name: t("home.hub.groups.other") })).toBeVisible();
    const card = courses.getByRole("listitem").first();
    await expect(card).toBeVisible();
    expect((await card.boundingBox())!.width).toBeGreaterThanOrEqual(256);
    await noOverflowAndShoot(page, "hub-general");
  });
});
