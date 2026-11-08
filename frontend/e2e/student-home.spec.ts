import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * Student UI U3 (docs/phases/STUDENT_UI_DESIGN.md §3.1): the home. A student of an exam-prep course without results
 * (`access.home_student` of the S3 course: a free and a paid exam, no pass, never takes a test) gets the greeting, the Next card with the page's only
 * primary button (brand blue; gold is the only accent), U9: the slim score line, the streak strip, the short gold unlock card, no
 * section card, no date message, no course grid and no getting-started card; the catalog, the code and leaving are
 * in the shell's exam sheet; a student of a general course only keeps the dashboard ("Панель"), whose course cards stay at least
 * 16rem wide at 1920 px. Read-only. Screens at 375 / 1440 / 1920 (ru) go to $U3_SHOTS when set.
 * TEACHER_TO_STUDENT_MAP S3: lesson courses attached to the ORT (Russian) course appear once, in "Уроки" (not under
 * "От платформы" or "Другие курсы"), and the "Продолжить урок" strip names the joined one's first unviewed lesson; no
 * strip without lessons. That test deletes its two lesson courses at the end; its screens go to $ITEM3_S3_SHOTS.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const WIDTHS = [375, 1440, 1920] as const;

async function api(user: SeedUser, method: string, p: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect([200, 201, 204], `${method} ${p} -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

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
    // S3 (G1): no lessons in this exam: no "Продолжить урок" strip, no "Уроки" section
    await expect(page.locator('section[aria-labelledby="home-continue"]')).toHaveCount(0);
    await expect(page.locator('section[aria-labelledby="home-lesson-courses"]')).toHaveCount(0);
  });

  test("lesson courses of the exam: once, in «Уроки»; the «Продолжить урок» strip", async ({ page }) => {
    const s = seed();
    const admin = s.admin;
    const student = s.modules.ort_student;
    const ort = await api(admin, "GET", `/courses/${s.course_id}`);
    const made: string[] = [];
    const mk = async (title: string) => {
      const c = await api(admin, "POST", "/courses", {
        title: { ru: title }, languages: ["ru"], default_language: "ru", organization_id: ort.organization_id, enrollment_mode: "open",
      });
      made.push(c.id);
      await api(admin, "POST", `/courses/${c.id}/publish`);
      await api(admin, "PATCH", `/courses/${c.id}`, { exam_course_id: s.course_id, enrollment_mode: "open", visibility: "catalog" });
      return c as { id: string };
    };
    try {
      const maths = await mk("Мастеркласс: математика");
      const analogies = await mk("Мастеркласс: аналогии");
      const m1 = await api(admin, "POST", `/courses/${maths.id}/modules`, { title: { ru: "Дроби и проценты" }, published: true });
      for (const [title, minutes] of [["Дроби: основы", 6], ["Проценты за 10 минут", 10]] as const) {
        const pg = await api(admin, "POST", `/courses/${maths.id}/pages`, { title, language: "ru", body_md: `Текст урока «${title}».`, published: true });
        const it = await api(admin, "POST", `/courses/${maths.id}/modules/${m1.id}/items`, { kind: "page", page_id: pg.id, published: true, duration_s: minutes * 60 });
        await api(admin, "PUT", `/courses/${maths.id}/modules/${m1.id}/items/${it.id}/requirement`, { type: "view" });
      }
      await api(student, "POST", `/courses/${maths.id}/join`, {});

      await page.setViewportSize({ width: 1440, height: 900 });
      await signIn(page, student);
      // the strip reads the stored module states (never evaluates): the student has opened the course once
      await page.goto(`/${L}/courses/${maths.id}/modules`);
      await expect(page.getByRole("heading", { level: 1, name: "Мастеркласс: математика" })).toBeVisible();
      await settle(page);
      await page.goto(`/${L}/courses`);
      const lessons =page.locator('section[aria-labelledby="home-lesson-courses"]');
      await expect(lessons.getByRole("heading", { level: 2, name: t("student.nav.lessonsGroup") })).toBeVisible();
      await expect(lessons.getByRole("link", { name: "Мастеркласс: математика" })).toHaveAttribute("href", `/${L}/courses/${maths.id}/modules`);
      await expect(lessons.getByRole("link", { name: "Мастеркласс: аналогии" })).toHaveAttribute("href", `/${L}/courses/catalog/${analogies.id}`);
      const join = lessons.getByRole("button", { name: t("catalog.join") });
      await expect(join).toHaveCount(1); // only the one not joined
      await expect(join).not.toHaveClass(/bg-brand-600/); // the Next card keeps the page's only primary button
      // nowhere else on the page (owner 2026-11-08: «аналогии» was under От платформы, «математика» under Другие курсы)
      for (const other of ['section[aria-labelledby="home-platform"]', 'section[aria-labelledby="home-other-courses"]']) {
        await expect(page.locator(other).getByText(/Мастеркласс/)).toHaveCount(0);
      }
      const main = page.locator("main#main");
      await expect(main.getByRole("link", { name: "Мастеркласс: аналогии" })).toHaveCount(1);
      // G1: the strip opens the first unviewed lesson of the joined lesson course
      const strip = page.locator('section[aria-labelledby="home-continue"]');
      await expect(strip.getByRole("heading", { level: 2, name: t("home.prep.continueLesson.title") })).toBeVisible();
      const row = strip.getByRole("link", { name: /Дроби: основы/ });
      await expect(row).toContainText("Мастеркласс: математика · Дроби и проценты");
      expect(await row.getAttribute("href")).toMatch(new RegExp(`^/${L}/courses/${maths.id}/modules/${m1.id}/items/`));
      await noOverflowAndShoot(page, "home-lesson-courses", process.env.ITEM3_S3_SHOTS);
    } finally {
      for (const id of made) await api(admin, "DELETE", `/courses/${id}`);
    }
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
