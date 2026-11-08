import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * TEACHER_TO_STUDENT_MAP S2 (docs/phases/TEACHER_TO_STUDENT_MAP.md §2.4-§2.6): screenshots only, with
 * ITEM3_S2_SHOTS=<dir>; run it alone (it attaches two lesson courses to the seeded ORT (Russian) course and leaves
 * them published, which the other specs do not expect). The platform admin creates "Мастеркласс: математика" (a module
 * with lessons; the ORT modules student joins it) and "Мастеркласс: аналогии" (not joined), both linked to the exam.
 * Shots (ru, 375 / 1440 / 1920): the student sidebar with the УРОКИ group (375: the "Ещё" sheet), the joined lesson
 * course's overview in the exam shell, the admin's exam select in the course settings (Access / Pro).
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.ITEM3_S2_SHOTS ? path.resolve(process.env.ITEM3_S2_SHOTS) : null;

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

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

async function widths(page: Page, name: string, at375?: (page: Page) => Promise<void>) {
  for (const width of [1440, 1920, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    if (width === 375 && at375) await at375(page);
    await noHorizontalScroll(page);
    await page.screenshot({ path: path.join(SHOTS!, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

test.describe("item 3 S2 screens (ru)", () => {
  test.skip(!SHOTS, "ITEM3_S2_SHOTS only");

  test("sidebar УРОКИ group, lesson course overview in the exam shell, exam select", async ({ browser }) => {
    test.setTimeout(240_000);
    fs.mkdirSync(SHOTS!, { recursive: true });
    const s = seed();
    const exam = s.course_id;
    const admin = s.admin;
    const student = s.modules.ort_student;
    const ort = await api(admin, "GET", `/courses/${exam}`);
    const mk = async (title: string) => {
      const c = await api(admin, "POST", "/courses", {
        title: { ru: title }, languages: ["ru"], default_language: "ru", organization_id: ort.organization_id, enrollment_mode: "open",
      });
      await api(admin, "POST", `/courses/${c.id}/publish`);
      await api(admin, "PATCH", `/courses/${c.id}`, { exam_course_id: exam, enrollment_mode: "open", visibility: "catalog" });
      return c as { id: string };
    };
    const maths = await mk("Мастеркласс: математика");
    const analogies = await mk("Мастеркласс: аналогии");
    const m1 = await api(admin, "POST", `/courses/${maths.id}/modules`, { title: { ru: "Дроби и проценты" }, published: true });
    for (const [title, minutes] of [["Дроби: основы", 6], ["Проценты за 10 минут", 10], ["Разбор задач", 8]] as const) {
      const pg = await api(admin, "POST", `/courses/${maths.id}/pages`, { title, language: "ru", body_md: `Текст урока «${title}».`, published: true });
      const it = await api(admin, "POST", `/courses/${maths.id}/modules/${m1.id}/items`, { kind: "page", page_id: pg.id, published: true, duration_s: minutes * 60 });
      await api(admin, "PUT", `/courses/${maths.id}/modules/${m1.id}/items/${it.id}/requirement`, { type: "view" });
    }
    await api(student, "POST", `/courses/${maths.id}/join`, {});

    const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const page = await ctx.newPage();
    await signIn(page, student);

    // ---- the sidebar: the УРОКИ group with both lesson courses (joined: a ring; not joined: nothing on the right)
    await page.goto(`/${L}/courses`);
    const nav = page.getByRole("navigation", { name: t("student.nav.label") }).first();
    await expect(nav.getByRole("link", { name: "Мастеркласс: математика" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Мастеркласс: аналогии" })).toHaveAttribute("href", `/${L}/courses/catalog/${analogies.id}`);
    await widths(page, "sidebar-lesson-courses", async (p) => {
      await p.getByRole("button", { name: t("student.nav.more") }).click();
      await expect(p.getByRole("dialog").getByRole("link", { name: "Мастеркласс: математика" })).toBeVisible();
    });
    await page.keyboard.press("Escape");

    // ---- the joined lesson course: overview in the exam shell (no course sidebar), its row is the current page
    await page.goto(`/${L}/courses/${maths.id}/modules`);
    await expect(page.getByRole("heading", { level: 1, name: "Мастеркласс: математика" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Мастеркласс: математика" })).toHaveAttribute("aria-current", "page");
    await widths(page, "lesson-course-overview");
    await ctx.close();

    // ---- the admin: the exam select in the course settings
    const actx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const apage = await actx.newPage();
    await signIn(apage, admin);
    await apage.goto(`/${L}/courses/${maths.id}/settings?section=access`);
    const select = apage.getByLabel(t("courses.settings.examLink.label"));
    await expect(select).toBeEnabled();
    await expect(select).toHaveValue(exam);
    await widths(apage, "settings-exam-link");
    await actx.close();
  });
});
