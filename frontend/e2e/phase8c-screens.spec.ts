import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Phase 8c UX-gate screenshots (PHASE_8C_DESIGN 15). Skipped unless PHASE8C_SCREENS_DIR is set:
 *   PHASE8C_SCREENS_DIR=docs/phases/PHASE_8C_screens E2E_WEB_DIR=... npx playwright test e2e/phase8c-screens.spec.ts
 * Data: the `course_nav` course (seed_course_nav) filled through the API, plus a fresh empty course and the ORT
 * course. 375x812 and 1440x900; teacher screens in ru and en, student screens in en, ky and ru. Viewport shots
 * (menus, sheets) except where the whole page is the point.
 */

const OUT = process.env.PHASE8C_SCREENS_DIR ? path.resolve(process.env.PHASE8C_SCREENS_DIR) : null;
type L3 = "ru" | "en" | "ky";
const nav = () => seed().course_nav;
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");
const ti = (v: string) => ({ ru: v, ky: v, en: v });

async function api(user: SeedUser, method: string, p: string, body?: unknown, ok = [200, 201, 204]) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method, headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(ok, `${method} ${p} -> ${r.status} ${text.slice(0, 200)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

async function ctxPage(browser: Browser, user: SeedUser, vp: "phone" | "desktop", lang: L3) {
  const ctx = await browser.newContext({ viewport: VIEWPORTS[vp], locale: lang === "en" ? "en-US" : "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return { ctx, page };
}

const shoot = async (page: Page, name: string, vp: string, lang: string, full = false) => {
  await settle(page);
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(OUT!, `${name}-${vp}-${lang}.png`), fullPage: full, animations: "disabled", caret: "hide" });
};

test.describe("phase 8c screens", () => {
  test.skip(!OUT, "set PHASE8C_SCREENS_DIR");
  test.describe.configure({ mode: "serial" });
  const ids: Record<string, string> = {};

  test("fill the course through the API", async () => {
    test.setTimeout(120_000);
    fs.mkdirSync(OUT!, { recursive: true });
    const c = nav();
    const cid = c.course_id;
    const T = c.teacher;
    const m1 = await api(T, "POST", `/courses/${cid}/modules`, { title: ti("Модуль 1"), published: true });
    const m2 = await api(T, "POST", `/courses/${cid}/modules`, { title: ti("Module 2 (draft)"), published: false });
    ids.m1 = m1.id;
    const pg = await api(T, "POST", `/courses/${cid}/pages`, { title: "Введение / Introduction", language: "ru", body_md: "Дробь $\\frac{a}{b}$.\n\n- один\n- два", published: true });
    ids.page = pg.id;
    await api(T, "POST", `/courses/${cid}/modules/${m1.id}/items`, { kind: "page", page_id: pg.id, published: true });
    const text = await api(T, "POST", `/courses/${cid}/assignments`, { kind: "text", title: ti("Эссе / Essay"), points_possible: 10 });
    await api(T, "PATCH", `/courses/${cid}/assignments/${text.id}`, { published: true });
    ids.text = text.id;
    await api(T, "POST", `/courses/${cid}/modules/${m1.id}/items`, { kind: "assignment", assignment_id: text.id, published: true });
    const list = await api(T, "GET", `/courses/${cid}/assignments?limit=100`);
    const quiz = list.items.find((a: { assessment_id: string | null }) => a.assessment_id === c.view_quiz);
    ids.quiz = quiz.id;
    await api(T, "POST", `/courses/${cid}/modules/${m1.id}/items`, { kind: "assignment", assignment_id: quiz.id, published: true });
    await api(T, "POST", `/courses/${cid}/modules/${m2.id}/items`, { kind: "header", title: "Заголовок" }, [200, 201]).catch(() => null);
    // loose targets (Unsorted)
    const loose = await api(T, "POST", `/courses/${cid}/assignments`, { kind: "file", title: ti("Проект / Project"), points_possible: 20 });
    await api(T, "PATCH", `/courses/${cid}/assignments/${loose.id}`, { published: true });
    await api(T, "POST", `/courses/${cid}/pages`, { title: "Заметки / Notes", language: "ru", body_md: "Текст.", published: false });
    const form = new FormData();
    form.append("file", new Blob([PDF], { type: "application/pdf" }), "notes.pdf");
    form.append("folder", ""); form.append("title", "Конспект / Handout"); form.append("published", "true");
    expect((await fetch(`${seed().api}/api/v1/courses/${cid}/course-files`, { method: "POST", headers: { Authorization: `Bearer ${T.token}` }, body: form })).status).toBe(201);
    await api(T, "POST", `/courses/${cid}/announcements`, { title: "Расписание / Schedule", body_md: "Занятия по вторникам.", pinned: false, publish: true });
    // a hand-in (To do: 1 to grade) and a draft assignment (Drafts)
    await api(c.students.handin, "POST", `/courses/${cid}/assignments/${text.id}/submissions`, { body_text: "Мой ответ." }, [200, 201]);
    await api(T, "POST", `/courses/${cid}/assignments`, { kind: "text", title: ti("Черновик задания / Draft task"), points_possible: 5 });
    // a fresh empty course
    const empty = await api(T, "POST", "/courses", { title: ti("Пустой курс / Empty course"), languages: ["ru", "ky", "en"], default_language: "ru" });
    await api(T, "POST", `/courses/${empty.id}/publish`, {});
    ids.empty = empty.id;
    ids.emptyCode = empty.join_code;
    await api(c.students.phone, "POST", "/courses/join", { code: empty.join_code });
  });

  for (const lang of ["ru", "en"] as const) {
    for (const vp of ["phone", "desktop"] as const) {
      test(`teacher screens ${vp} ${lang}`, async ({ browser }) => {
        test.setTimeout(300_000);
        const tl = (k: string, v: Record<string, string | number> = {}) => tr(lang, k, v);
        const c = nav();
        const base = `/${lang}/courses/${c.course_id}`;
        const { ctx, page } = await ctxPage(browser, c.teacher, vp, lang);
        // empty course
        await page.goto(`/${lang}/courses/${ids.empty}`);
        await expect(page.getByText(tl("modules.editor.emptyTitle"))).toBeVisible();
        await shoot(page, "teacher-course-empty", vp, lang);
        if (vp === "phone") {
          // 8c UX m10: the drawer of the empty course, so the "hidden from students" marks show
          await page.getByRole("button", { name: new RegExp(`^${tl("courseNav.menu")}`) }).click();
          await shoot(page, "teacher-drawer", vp, lang);
          await page.keyboard.press("Escape");
        }
        // filled course page: sidebar (desktop) / drawer button (phone), outline, Unsorted, To do
        await page.goto(base);
        await expect(page.getByRole("heading", { name: tl("todo.title") }).first()).toBeVisible().catch(() => null);
        await settle(page);
        await shoot(page, "teacher-course-filled", vp, lang);
        await shoot(page, "teacher-course-filled-full", vp, lang, true);
        if (vp === "phone") {
          // the collapsed To do line, then expanded
          const line = page.getByRole("button", { expanded: false }).filter({ hasText: /\d/ }).first();
          if (await line.count()) { await line.scrollIntoViewIfNeeded(); await shoot(page, "teacher-todo-collapsed", vp, lang); await line.click(); await shoot(page, "teacher-todo-expanded", vp, lang); }
        } else {
          await shoot(page, "teacher-sidebar", vp, lang);
        }
        // grouped "+ Add" and the "⋯" menus
        const card = page.locator(`#m-${ids.m1}`);
        await card.scrollIntoViewIfNeeded();
        await card.getByRole("button", { name: tl("modules.editor.addItem") }).first().click();
        await shoot(page, "teacher-add-menu", vp, lang);
        await page.keyboard.press("Escape");
        await card.getByRole("button", { name: tl("modules.editor.actions") }).first().click();
        await shoot(page, "teacher-module-menu", vp, lang);
        await page.keyboard.press("Escape");
        await card.locator("li").first().getByRole("button", { name: /./ }).last().click().catch(() => null);
        await shoot(page, "teacher-item-menu", vp, lang);
        await page.keyboard.press("Escape");
        const un = page.locator("section, details").filter({ has: page.getByRole("heading", { name: tl("coursePage.unsorted.title") }) }).first();
        await un.scrollIntoViewIfNeeded();
        await shoot(page, "teacher-unsorted", vp, lang);
        // assignment page: tabs
        const ap = `${base}/assignments/${ids.text}`;
        for (const [tab, extra] of [["details", ""], ["submissions", "&filter=to_grade"], ["settings", ""]] as const) {
          await page.goto(`${ap}?tab=${tab}${extra}`);
          await expect(page.getByRole("tab", { name: tl(`assignments.page.tabs.${tab}`) })).toHaveAttribute("aria-selected", "true");
          await shoot(page, `teacher-assignment-${tab}`, vp, lang);
        }
        await page.goto(`${base}/assignments/${ids.quiz}?tab=results`);
        await expect(page.getByRole("tab", { name: tl("assignments.page.tabs.results") })).toHaveAttribute("aria-selected", "true");
        await shoot(page, "teacher-quiz-results", vp, lang);
        await page.goto(`${base}/assignments/${ids.quiz}?tab=details`);
        await shoot(page, "teacher-quiz-details", vp, lang);
        // page object
        for (const tab of ["edit", "preview"]) {
          await page.goto(`${base}/pages/${ids.page}?tab=${tab}`);
          await expect(page.getByRole("tab", { name: tl(`pages.object.tabs.${tab}`) })).toHaveAttribute("aria-selected", "true");
          await shoot(page, `teacher-page-${tab}`, vp, lang);
        }
        // Assignments list with the quiz filter
        await page.goto(`${base}/assignments?kind=quiz`);
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
        await shoot(page, "teacher-assignments-quiz-filter", vp, lang);
        await ctx.close();
      });
    }
  }

  for (const vp of ["phone", "desktop"] as const) {
    test(`ORT course page ${vp}`, async ({ browser }) => {
      const { ctx, page } = await ctxPage(browser, seed().admin, vp, "ru");
      await page.goto(`/ru/courses/${seed().course_id}`);
      await expect(page.getByText("ОРТ E2E", { exact: true }).first()).toBeVisible();
      await shoot(page, "teacher-ort-course", vp, "ru");
      await shoot(page, "teacher-ort-course-full", vp, "ru", true);
      await ctx.close();
    });
  }

  for (const lang of ["en", "ky", "ru"] as const) {
    for (const vp of ["phone", "desktop"] as const) {
      test(`student screens ${vp} ${lang}`, async ({ browser }) => {
        test.setTimeout(240_000);
        const tl = (k: string, v: Record<string, string | number> = {}) => tr(lang, k, v);
        const c = nav();
        const base = `/${lang}/courses/${c.course_id}`;
        const { ctx, page } = await ctxPage(browser, c.students.sidebar, vp, lang);
        await page.goto(base);
        await expect(page.getByRole("heading", { name: "Модуль 1" })).toBeVisible();
        await shoot(page, "student-course", vp, lang);
        if (vp === "phone") {
          await page.getByRole("button", { name: new RegExp(`^${tl("courseNav.menu")}`) }).click();
          await shoot(page, "student-drawer", vp, lang);
          await page.keyboard.press("Escape");
        }
        // auto-hidden links: a student of a course with nothing published in Announcements / Files... here both are
        // published (shown); the empty course shows the hidden variant
        const e = await ctxPage(browser, c.students.phone, vp, lang);
        await e.page.goto(`/${lang}/courses/${ids.empty}`);
        await shoot(e.page, "student-course-hidden-links", vp, lang);
        await e.page.goto(`/${lang}/courses/${ids.empty}/announcements`);
        await expect(e.page.getByText(tl("courseNav.unavailable.title"))).toBeVisible();
        await shoot(e.page, "student-not-available", vp, lang);
        await e.ctx.close();
        // the owner teacher's Student view (8c fix 2): banner
        const a = await ctxPage(browser, c.teacher, vp, lang);
        await a.page.goto(base);
        await a.page.getByRole("button", { name: tl("studentView.button") }).click();
        await expect(a.page.getByRole("status").filter({ hasText: tl("studentView.banner") })).toBeVisible();
        await shoot(a.page, "student-view-banner", vp, lang);
        await a.page.goto(`${base}/assignments/${ids.text}`);
        await expect(a.page.getByText(tl("studentView.handInsOff"))).toBeVisible();
        await shoot(a.page, "student-view-handins-off", vp, lang);
        await a.ctx.close();
        await ctx.close();
      });
    }
  }
});
