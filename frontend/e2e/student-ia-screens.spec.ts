import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, seed, settle, signIn } from "./helpers";

/**
 * Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3, §7.4, §7.5): screenshots of the course space for the orchestrator's
 * UX check (ru, 375 and 1440): the exam course Обзор, Тесты, Аналитика, Повторение and the lobby; a lesson course
 * attached to the exam (Обзор, Уроки, Задания, a lesson page). Not compared with a baseline. Runs only with
 * `STUDENT_IA_SHOTS=<dir>` and in its own run (it publishes the seed's lesson course "Мастеркласс E2E" and links it to
 * the exam, which teacher-to-student.spec.ts does itself): `npx playwright test e2e/student-ia-screens.spec.ts`.
 * Names are the seed's fake ones.
 */

const OUT = process.env.STUDENT_IA_SHOTS;
const L = "ru";
const WIDTHS = [375, 1440] as const;

async function shoot(page: Page, url: string, name: string) {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
    await page.goto(url);
    await settle(page);
    await page.waitForTimeout(400);
    // the course space never scrolls sideways on a phone
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(OUT as string, `${name}-${width}.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
}

test.describe("course space screenshots (ru)", () => {
  test.skip(!OUT, "STUDENT_IA_SHOTS is not set");

  test("exam course and lesson course", async ({ page }) => {
    const s = seed();
    const admin = s.admin;
    const exam = s.item3.exam_course_id;
    const lc = s.item3.lesson_course_id;
    const student = s.item3.student;
    // the exam date in 30 days (countdown in the header)
    const date = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
    await api(admin, "PATCH", `/courses/${exam}`, { exam_date: date });
    // the lesson course: published, attached to the exam, two modules, a video, a page, a hand-in, an announcement
    await api(admin, "PATCH", `/courses/${lc}`, { description: { ru: "Дроби, проценты и пропорции с разбором задач ОРТ." } });
    await api(admin, "POST", `/courses/${lc}/publish`, {});
    await api(admin, "PATCH", `/courses/${lc}`, { exam_course_id: exam });
    const m1 = await api(admin, "POST", `/courses/${lc}/modules`, { title: { ru: "Дроби" }, published: true });
    const page1 = await api(admin, "POST", `/courses/${lc}/pages`, { title: "Что такое дробь", language: "ru", body_md: "Дробь показывает часть целого.\n\n**Пример:** 3/4 — три части из четырёх.", published: true });
    const pageItem = await api(admin, "POST", `/courses/${lc}/modules/${m1.id}/items`, { kind: "page", page_id: page1.id, published: true, duration_s: 300 });
    await api(admin, "POST", `/courses/${lc}/modules/${m1.id}/items`, { kind: "url", url: "https://www.youtube.com/watch?v=aqz-KE-bpKQ", title_override: { ru: "Видео: сложение дробей" }, published: true, duration_s: 360 });
    const m2 = await api(admin, "POST", `/courses/${lc}/modules`, { title: { ru: "Проценты" }, published: true });
    const page2 = await api(admin, "POST", `/courses/${lc}/pages`, { title: "Проценты за 5 минут", language: "ru", body_md: "Процент — сотая часть числа.", published: true });
    await api(admin, "POST", `/courses/${lc}/modules/${m2.id}/items`, { kind: "page", page_id: page2.id, published: true, duration_s: 300 });
    const essay = await api(admin, "POST", `/courses/${lc}/assignments`, { title: { ru: "Эссе: дроби вокруг нас" }, kind: "text", points_possible: 10 });
    await api(admin, "PATCH", `/courses/${lc}/assignments/${essay.id}`, { published: true });
    await api(admin, "POST", `/courses/${lc}/announcements`, { title: "Вебинар в субботу", body_md: "Разбираем задачи на дроби в 18:00.", publish: true });
    await api(student, "POST", `/courses/${lc}/join`, {});

    await signIn(page, student);
    const ex = `/${L}/courses/${exam}`;
    await shoot(page, ex, "exam-overview");
    await expect(page.getByRole("navigation", { name: "Вкладки курса" })).toBeVisible();
    await shoot(page, `${ex}/tests`, "exam-tests");
    await shoot(page, `${ex}/analytics`, "exam-analytics");
    await shoot(page, `${ex}/saved`, "exam-saved");
    await shoot(page, `${ex}/lessons`, "exam-lessons");
    await shoot(page, `${ex}/assessments/${s.exam.id}`, "exam-lobby");
    const lcBase = `/${L}/courses/${lc}`;
    await shoot(page, lcBase, "lesson-overview");
    await shoot(page, `${lcBase}/lessons`, "lesson-lessons");
    await shoot(page, `${lcBase}/tests`, "lesson-assignments");
    await shoot(page, `${lcBase}/modules/${m1.id}/items/${pageItem.id}`, "lesson-page");
  });
});
