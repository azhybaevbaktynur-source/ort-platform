import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, type SeedUser } from "./helpers";
import { chooseCoursesHref } from "../src/lib/lms/chooseCourses"; // the catalog until S4

/**
 * One course card everywhere (the hub, catalog, Teaching list), the last result with its maximum, and the hub order:
 * cards left, «К выполнению» right. Step 3a S3: the hub `/home` groups the cards (ОРТ · НЦТ · Другие курсы); once the
 * student joins ORT its card heads the ОРТ group and, on a phone, the to-do follows the courses. Screenshots only with
 * UX_SCREENS_DIR set.
 */
const OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const ti = (v: string) => ({ ru: v });
const WITH_ALL = "Математика для 9 класса";
const LONG = "Подготовка к олимпиаде по русскому языку и литературе для старших классов школы";
const BARE = "Без описания";
const DESCRIPTION = "Дроби, проценты и уравнения: разбираем темы шаг за шагом и готовимся к контрольным работам в конце каждой четверти.";

async function call(user: SeedUser | null, method: string, apiPath: string, body?: unknown): Promise<Response> {
  return fetch(`${seed().api}/api/v1${apiPath}`, {
    method,
    headers: { ...(user ? { Authorization: `Bearer ${user.token}` } : {}), "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function api(user: SeedUser | null, method: string, apiPath: string, body?: unknown) {
  const r = await call(user, method, apiPath, body);
  const text = await r.text();
  expect(r.status, `${method} ${apiPath}: ${text.slice(0, 200)}`).toBeLessThan(300);
  return text ? JSON.parse(text) : null;
}

async function emailedCode(email: string): Promise<string> {
  for (let i = 0; i < 100; i += 1) {
    const log = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8");
    const at = log.lastIndexOf(`[EMAIL console] To: ${email} `);
    const code = (at >= 0 ? log.slice(log.indexOf("\n", at)) : "").match(/\b(\d{6})\b/);
    if (code) return code[1];
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`no code for ${email}`);
}

async function newStudent(name: string): Promise<SeedUser> {
  const email = `e2e-cards-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  const password = `pw-${Math.random().toString(36).slice(2)}-${Date.now()}`;
  const policies = (await api(null, "GET", "/privacy/policies/current")) as { id: string; kind: string }[];
  await api(null, "POST", "/auth/register", {
    email, password, displayName: name, lang: "ru", ageBand: "18_plus",
    policyVersionIds: policies.filter((p) => p.kind !== "guardian_consent").map((p) => p.id),
  });
  const out = await api(null, "POST", "/auth/verify-email", { email, password, code: await emailedCode(email) });
  const user = { email, name, token: out.access_token, profile: { id: "" } } as SeedUser;
  user.profile = await api(user, "GET", "/auth/me");
  return user;
}

async function open(browser: Browser, user: SeedUser, width: number, height: number): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width, height }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function look(page: Page, name: string) {
  await settle(page);
  await page.waitForTimeout(300);
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, `${name} scrolls sideways`).toBeLessThanOrEqual(0);
  if (OUT) {
    fs.mkdirSync(OUT, { recursive: true });
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true, animations: "disabled" });
  }
}

// step 3a S3: the hub's sections
const courses = (page: Page) => page.locator('section[aria-labelledby="hub-courses"]');
const todo = (page: Page) => page.locator('section[aria-labelledby="home-todo"]');
const group = (page: Page, key: string) => page.locator(`section[aria-labelledby="group-${key}"]`);
const card = (page: Page, title: string) => courses(page).locator("li", { has: page.getByRole("link", { name: title, exact: true }) });

test.describe("course cards", () => {
  test.describe.configure({ mode: "serial" });
  let student: SeedUser;
  let empty: SeedUser;
  const teacher = () => seed().course_nav.teacher;

  test("fill", async () => {
    test.setTimeout(180_000);
    student = await newStudent("Айдана Токтосунова");
    empty = await newStudent("Новый ученик");
    const T = teacher();
    const make = async (title: string, extra: object = {}) => {
      const c = await api(T, "POST", "/courses", { title: ti(title), languages: ["ru"], default_language: "ru", ...extra });
      await api(T, "POST", `/courses/${c.id}/publish`, {});
      await api(student, "POST", "/courses/join", { code: c.join_code });
      return c.id as string;
    };
    const main = await make(WITH_ALL, { description: ti(DESCRIPTION) });
    await make(LONG, { description: ti("Короткое описание."), languages: ["ru", "ky"], title: { ru: LONG, ky: LONG } });
    await make(BARE);
    // an organization course, with a teacher and the school's name
    const school = seed().org_admin;
    const inSchool = await api(school.maths, "GET", `/courses/${school.maths_course_id}`);
    await api(student, "POST", "/courses/join", { code: inSchool.join_code });

    // progress: one of two requirements met, read from the caches the student's own Modules page writes
    const m = await api(T, "POST", `/courses/${main}/modules`, { title: ti("Неделя 1"), published: true });
    const page1 = await api(T, "POST", `/courses/${main}/pages`, { title: "Введение", language: "ru", body_md: "Текст.", published: true });
    const page2 = await api(T, "POST", `/courses/${main}/pages`, { title: "Дроби", language: "ru", body_md: "Текст.", published: true });
    const item = await api(T, "POST", `/courses/${main}/modules/${m.id}/items`, { kind: "page", page_id: page1.id, published: true, requirement: { type: "view" } });
    await api(T, "POST", `/courses/${main}/modules/${m.id}/items`, { kind: "page", page_id: page2.id, published: true, requirement: { type: "view" } });
    await api(student, "GET", `/courses/${main}/modules`);
    await api(student, "POST", `/courses/${main}/modules/${m.id}/items/${item.id}/view`, {});

    // a zero and a next due date
    const zero = await api(T, "POST", `/courses/${main}/assignments`, { title: ti("Контрольная по дробям"), kind: "text", points_possible: "10" });
    await api(T, "PATCH", `/courses/${main}/assignments/${zero.id}`, { published: true });
    await api(student, "POST", `/courses/${main}/assignments/${zero.id}/submissions`, { body_text: "Ответ." });
    const roster = await api(T, "GET", `/courses/${main}/assignments/${zero.id}/submissions`);
    const row = roster.rows.find((r: { user_id: string }) => r.user_id === student.profile.id);
    await api(T, "PUT", `/courses/${main}/assignments/${zero.id}/grades/${row.enrollment_id}`, { points: "0" });
    await api(T, "POST", `/courses/${main}/assignments/${zero.id}/grades/release`, {});
    const next = await api(T, "POST", `/courses/${main}/assignments`, {
      title: ti("Эссе о процентах"), kind: "text", points_possible: "10", due_at: new Date(Date.now() + 5 * 86_400_000).toISOString(),
    });
    await api(T, "PATCH", `/courses/${main}/assignments/${next.id}`, { published: true });
  });

  test("desktop: cards on the left, side lists on the right, every field on the card", async ({ browser }) => {
    test.setTimeout(120_000);
    const page = await open(browser, student, 1440, 900);
    await page.goto("/ru/home");
    await expect(courses(page).getByRole("link", { name: WITH_ALL, exact: true })).toBeVisible();
    await look(page, "dashboard-1440");

    const main = card(page, WITH_ALL);
    await expect(main).toContainText(teacher().name);
    await expect(main).toContainText(t("courses.languages.ru"));
    await expect(main).not.toContainText(DESCRIPTION.slice(0, 30)); // F7c: the bar replaces the description of a joined course
    await expect(card(page, LONG)).toContainText("Короткое описание."); // nothing to finish: the description stays
    await expect(main.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    await expect(main.getByRole("progressbar")).toHaveAttribute("aria-valuemax", "2");
    await expect(main).toContainText(t("modules.progressCount", { done: 1, total: 2 }));
    await expect(main).toContainText(t("home.todo.due", { date: "" }).trim()); // the next due line
    // nothing to finish: no bar
    await expect(card(page, BARE).getByRole("progressbar")).toHaveCount(0);

    // a personal organization's name never shows; the teacher does
    const row = (await api(student, "GET", "/me/home")).courses.find((c: { title: { ru?: string } }) => c.title.ru === WITH_ALL);
    expect(row.organization_display_name).toBeNull();

    // a zero has its maximum (the card's last result line; step 3a S3: no results list on the hub)
    await expect(main).toContainText(t("home.hub.card.lastResult", { value: "0 / 10" }));

    // the side lists sit right of the cards; cards of one row are equally high
    const left = (await courses(page).boundingBox())!;
    const right = (await todo(page).boundingBox())!;
    expect(right.x).toBeGreaterThan(left.x + left.width - 1);
    const boxes = await courses(page).locator("ul > li").evaluateAll((els) => els.map((e) => e.getBoundingClientRect()).map((b) => ({ top: b.top, height: b.height })));
    for (const a of boxes) for (const b of boxes) if (a.top === b.top) expect(a.height).toBe(b.height);
    await page.context().close();
  });

  test("phone, after joining ORT: the ОРТ group first, then the other courses, then the to-do; no sideways scroll", async ({ browser }) => {
    test.setTimeout(120_000);
    await api(student, "POST", `/courses/${seed().course_id}/join`, {}); // the platform's ORT course
    const page = await open(browser, student, 375, 812);
    await page.goto("/ru/home");
    await expect(group(page, "other").getByRole("link", { name: WITH_ALL, exact: true })).toBeVisible();
    await look(page, "dashboard-375");
    // step 3a S3: the ORT course is a card of the ОРТ group (no exam-prep home, no sections card on the hub)
    await expect(group(page, "ort").locator(`a[href="/ru/courses/${seed().course_id}"]`).first()).toBeVisible();
    await expect(group(page, "other").locator(`a[href="/ru/courses/${seed().course_id}"]`)).toHaveCount(0);
    const o = (await group(page, "ort").boundingBox())!;
    const d = (await group(page, "other").boundingBox())!;
    const b = (await todo(page).boundingBox())!;
    expect(o.y + o.height).toBeLessThanOrEqual(d.y);
    expect(d.y + d.height).toBeLessThanOrEqual(b.y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await page.context().close();
  });

  test("the catalog shows the same card for the same course", async ({ browser }) => {
    test.setTimeout(120_000);
    const catalog = await api(student, "GET", "/catalog/courses?limit=50");
    const home = await api(student, "GET", "/me/home");
    const inBoth = catalog.items.find((c: { id: string }) => home.courses.some((h: { id: string }) => h.id === c.id));
    const same = home.courses.find((h: { id: string }) => h.id === inBoth.id);
    expect(inBoth.organization_display_name).toBe(same.organization_display_name);
    expect(inBoth.is_platform_course).toBe(same.is_platform_course);
    expect(inBoth.description).toEqual(same.description);
    for (const [w, h] of [[1440, 900], [375, 812]]) {
      const page = await open(browser, student, w, h);
      await page.goto("/ru/courses/catalog");
      await expect(page.getByRole("heading", { name: t("catalog.title") })).toBeVisible();
      await look(page, `catalog-${w}`);
      await page.context().close();
    }
  });

  test("the Teaching list uses the card; an empty hub offers the choose step and the code", async ({ browser }) => {
    test.setTimeout(120_000);
    const tp = await open(browser, teacher(), 1440, 900);
    await tp.goto("/ru/courses");
    await expect(tp.getByRole("link", { name: WITH_ALL })).toBeVisible();
    await expect(tp.locator("li", { has: tp.getByRole("link", { name: WITH_ALL }) })).toContainText(t("courses.status.published"));
    await look(tp, "teaching-1440");
    await tp.context().close();

    const ep = await open(browser, empty, 375, 812);
    await ep.goto("/ru/home");
    // step 3a S3 (§2.2): the platform courses moved to the choose step; the empty hub has «Выбрать курсы» and the code
    await expect(ep.getByText(t("home.hub.emptyTitle"))).toBeVisible();
    await expect(ep.locator("main#main").getByRole("link", { name: t("home.hub.choose") })).toHaveAttribute("href", chooseCoursesHref("ru"));
    await expect(ep.locator("main#main").getByRole("link", { name: t("home.hub.join") })).toHaveAttribute("href", "/ru/courses/join");
    await look(ep, "dashboard-empty-375");
    await ep.context().close();
  });
});
