import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser } from "@playwright/test";
import { seed, settle, signIn, type SeedUser } from "./helpers";

/**
 * UX rework check (UR-6): the changed screens in ru at 375, 1440 and 1920 px. Skipped unless UX_SCREENS_DIR is set.
 * Also fails on sideways page scroll at any of the three widths.
 */
const OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
const SIZES = [[375, 812], [1440, 900], [1920, 1080]] as const;
const ti = (v: string) => ({ ru: v, ky: v, en: v });

async function api(user: SeedUser, method: string, p: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method, headers: { Authorization: `Bearer ${user.token}`, "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(r.status, `${method} ${p}: ${text.slice(0, 200)}`).toBeLessThan(300);
  return text ? JSON.parse(text) : null;
}

async function walk(browser: Browser, user: SeedUser, shots: [string, string][]) {
  for (const [w, h] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ru-RU", timezoneId: "UTC" });
    const page = await ctx.newPage();
    await signIn(page, user);
    for (const [name, url] of shots) {
      await page.goto(url);
      await settle(page);
      await page.waitForTimeout(300);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over, `${name} at ${w}px scrolls sideways`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: path.join(OUT!, `${name}-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
    }
    await ctx.close();
  }
}

test.describe("ux rework screens", () => {
  test.skip(!OUT, "set UX_SCREENS_DIR");
  test.describe.configure({ mode: "serial" });

  test("fill", async () => {
    fs.mkdirSync(OUT!, { recursive: true });
    const c = seed().course_nav;
    const T = c.teacher;
    const cid = c.course_id;
    const m1 = await api(T, "POST", `/courses/${cid}/modules`, { title: ti("Неделя 1: дроби"), published: true });
    const m2 = await api(T, "POST", `/courses/${cid}/modules`, { title: ti("Неделя 2: проценты"), published: true });
    await api(T, "POST", `/courses/${cid}/modules`, { title: ti("Неделя 3 (черновик)"), published: false });
    const pg = await api(T, "POST", `/courses/${cid}/pages`, { title: "Введение", language: "ru", body_md: "Текст.", published: true });
    await api(T, "POST", `/courses/${cid}/modules/${m1.id}/items`, { kind: "page", page_id: pg.id, published: true });
    const due = new Date(Date.now() + 5 * 86400000).toISOString();
    const text = await api(T, "POST", `/courses/${cid}/assignments`, { kind: "text", title: ti("Эссе о дробях"), points_possible: 10, due_at: due });
    await api(T, "PATCH", `/courses/${cid}/assignments/${text.id}`, { published: true });
    await api(T, "POST", `/courses/${cid}/modules/${m1.id}/items`, { kind: "assignment", assignment_id: text.id, published: true });
    const list = await api(T, "GET", `/courses/${cid}/assignments?limit=100`);
    const quiz = list.items.find((a: { assessment_id: string | null }) => a.assessment_id === c.view_quiz);
    await api(T, "POST", `/courses/${cid}/modules/${m2.id}/items`, { kind: "assignment", assignment_id: quiz.id, published: true });
    const loose = await api(T, "POST", `/courses/${cid}/assignments`, { kind: "file", title: ti("Проект"), points_possible: 20 });
    await api(T, "PATCH", `/courses/${cid}/assignments/${loose.id}`, { published: true });
    await api(c.students.handin, "POST", `/courses/${cid}/assignments/${text.id}/submissions`, { body_text: "Мой ответ." });
  });

  test("student", async ({ browser }) => {
    test.setTimeout(300_000);
    const c = seed().course_nav;
    await walk(browser, c.students.handin, [["student-dashboard", "/ru/courses"], ["student-course", `/ru/courses/${c.course_id}`]]);
  });

  test("teacher", async ({ browser }) => {
    test.setTimeout(300_000);
    const c = seed().course_nav;
    const b = `/ru/courses/${c.course_id}`;
    await walk(browser, c.teacher, [["teacher-course", b], ["teacher-people", `${b}/people`], ["teacher-assignments", `${b}/assignments`], ["teacher-settings", `${b}/settings`]]);
  });

  test("org admin and platform admin", async ({ browser }) => {
    test.setTimeout(300_000);
    const o = seed().org_admin;
    const org = `/ru/org/${o.organization_id}`;
    await walk(browser, o.org_admin, [["org-summary", org], ["org-teachers", `${org}/teachers`]]);
    const admin = seed().admin as SeedUser;
    await walk(browser, admin, [["admin-overview", "/ru/admin"], ["admin-org", `/ru/admin/organizations/${o.organization_id}`], ["admin-users", "/ru/admin/users"]]);
  });

  test("student view", async ({ browser }) => {
    test.setTimeout(300_000);
    const c = seed().course_nav;
    for (const [w, h] of SIZES) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ru-RU", timezoneId: "UTC" });
      const page = await ctx.newPage();
      await signIn(page, c.teacher);
      await page.goto(`/ru/courses/${c.course_id}`);
      await settle(page);
      await page.getByRole("button", { name: "Режим ученика" }).click();
      await expect(page.getByTestId("student-view-banner")).toBeVisible();
      await expect(page.getByText("Покинуть курс")).toHaveCount(0);
      await settle(page);
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(OUT!, `student-view-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
      await ctx.close();
    }
  });
});
