import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { api, E2E_DIR, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";
import { ortKyrgyzId } from "./hubCourses";

/**
 * Step 3a S7 (docs/phases/STUDENT_IA_DESIGN.md v3 V3, V4, V5, V14, V15; was `choose-courses.spec.ts` of S4): a new
 * account lands in the catalog with the welcome line, and the catalog's family chips, in a real browser against the
 * scratch backend.
 *
 * - sign-up -> `/courses/catalog?welcome=1`: the line (`role="status"`), ОРТ first, the one «Войти по коду» in the
 *   header; «×» and a chip remove the line; nothing joined; old `/courses/choose[?first=1]` links redirect; the landing's
 *   «Записаться» lands on the course Обзор;
 * - under 14 -> the privacy page; `?redirect=` -> its target (a teacher-code sign-up lands on the join page);
 * - people who teach: `/courses/choose` -> Teaching, no welcome line or code button in the catalog; Student view's test
 *   student -> the hub;
 * - the catalog: ОРТ · НЦТ · Курсы преподавателей, subject sections, `?exam=` in the URL; read-only for a teacher.
 * Google's new account (`created`) -> the catalog welcome is in `oauth-google.spec.ts`.
 *
 * The ORT and НЦТ subject courses are made here (fake titles) and deleted afterwards, so other specs see the seed's
 * catalog. Screens for the orchestrator's UX check (ru, 375 and 1440) when `STUDENT_IA_S7_SHOTS=<dir>` is set.
 */

const L = "ru";
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const OUT = process.env.STUDENT_IA_S7_SHOTS;
const PASSWORD = `e2e-${Math.random().toString(36).slice(2)}-pass`;
const rand = () => Math.random().toString(36).slice(2, 8);

interface Made { maths: string; physics: string; chemistry: string; nctBiology: string; ortRu: string; ortKy: string; ortRuTitle: string; ortKyTitle: string }
let made: Made;
const toDelete: string[] = [];
let teacher: SeedUser & { course_id: string };

async function shot(page: Page, name: string, before?: () => Promise<void>) {
  if (!OUT) return;
  fs.mkdirSync(OUT, { recursive: true });
  for (const size of [VIEWPORTS.phone, VIEWPORTS.desktop]) {
    await page.setViewportSize(size);
    if (before) await before();
    await settle(page);
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(OUT, `${name}-${size.width}.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
}

async function noSideScroll(page: Page) {
  await page.setViewportSize(VIEWPORTS.phone);
  await settle(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), "side scroll at 375").toBeLessThanOrEqual(0);
}

async function emailCode(email: string): Promise<string> {
  const end = Date.now() + 30_000;
  while (Date.now() < end) {
    const log = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8");
    const blocks = log.split("[EMAIL console] To: ").filter((b) => b.startsWith(`${email} `));
    const m = blocks[blocks.length - 1]?.match(/\b(\d{6})\b/);
    if (m) return m[1];
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`no code for ${email}`);
}

async function fresh(browser: Browser, viewport: { width: number; height: number } = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  return ctx.newPage();
}

/** The sign-up form as a student of 18+ (fake name), up to the verified account. */
async function signUp(page: Page, email: string, url = `/${L}/register`) {
  await page.goto(url);
  await page.getByRole("button", { name: t("privacy.age.18_plus") }).click();
  await page.getByLabel(t("auth.displayName")).fill("Айдана Пробная");
  await page.getByLabel(t("auth.email")).fill(email);
  await page.getByLabel(t("auth.password")).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: t("auth.signUpButton") }).click();
  await expect(page.getByRole("heading", { name: t("auth.verify.title") })).toBeVisible();
  await page.getByLabel(t("auth.verify.codeLabel")).fill(await emailCode(email));
  await page.getByRole("button", { name: t("auth.verify.button") }).click();
}

/** A verified account through the API (the teacher of this spec). */
async function registerApi(email: string, name: string): Promise<SeedUser> {
  const base = `${seed().api.replace(/\/+$/, "")}/api/v1`;
  const json = async (r: Response) => { const text = await r.text(); expect(r.ok, text.slice(0, 300)).toBe(true); return text ? JSON.parse(text) : null; };
  const policies = await json(await fetch(`${base}/privacy/policies/current`));
  const ids = (policies as { id: string; kind: string }[]).filter((p) => p.kind === "privacy" || p.kind === "terms").map((p) => p.id);
  const password = `e2e-${rand()}-${rand()}`;
  await json(await fetch(`${base}/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, displayName: name, lang: "ru", ageBand: "18_plus", policyVersionIds: ids }) }));
  const out = await json(await fetch(`${base}/auth/verify-email`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, code: await emailCode(email) }) }));
  const user = { email, name, token: out.access_token } as SeedUser;
  user.profile = await api(user, "GET", "/auth/me");
  return user;
}

/** The signed-in page's own API answer (its token from the device storage). */
async function apiAs(page: Page, p: string) {
  return page.evaluate(async ([base, url]) => {
    const r = await fetch(`${base}/api/v1${url}`, { headers: { Authorization: `Bearer ${localStorage.getItem("ort_token")}` } });
    return r.json();
  }, [seed().api.replace(/\/+$/, ""), p] as const);
}

const welcome = (page: Page) => page.getByRole("status").filter({ hasText: t("catalog.welcome") });

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const s = seed();
  const admin = s.admin;
  const ort = await api(admin, "GET", `/courses/${s.course_id}`);
  const ortKy = await ortKyrgyzId(admin);
  const ky = await api(admin, "GET", `/courses/${ortKy}`);
  const mk = async (title: string, patch: Record<string, unknown>) => {
    const c = await api(admin, "POST", "/courses", {
      title: { ru: title }, description: { ru: "Короткий курс к экзамену: темы, разборы и тесты." }, languages: ["ru"],
      default_language: "ru", organization_id: ort.organization_id,
    });
    toDelete.push(c.id);
    await api(admin, "POST", `/courses/${c.id}/publish`);
    await api(admin, "PATCH", `/courses/${c.id}`, { enrollment_mode: "open", visibility: "catalog", ...patch });
    return c.id as string;
  };
  made = {
    ortRu: s.course_id, ortKy, ortRuTitle: ort.title.ru, ortKyTitle: ky.title.ru ?? ky.title.ky,
    maths: await mk("ОРТ: Математика E2E", { exam_family: "ort", subject: "math" }),
    physics: await mk("ОРТ: Физика E2E", { exam_family: "ort", subject: "physics" }),
    chemistry: await mk("ОРТ: Химия E2E", { exam_family: "ort", subject: "chemistry" }),
    nctBiology: await mk("НЦТ: Биология E2E", { exam_family: "nct", subject: "biology" }),
  };
});

test.afterAll(async () => {
  for (const id of toDelete) await api(seed().admin, "DELETE", `/courses/${id}`);
});

test("sign-up: the catalog with the welcome line; «×» and a chip remove it; nothing joined; «Записаться» → Обзор", async ({ browser }) => {
  test.setTimeout(180_000);
  const page = await fresh(browser);
  await signUp(page, `e2e-welcome-${rand()}@example.com`);
  await expect(page).toHaveURL(new RegExp(`/${L}/courses/catalog\\?welcome=1$`));
  await expect(page.getByRole("heading", { level: 1, name: t("catalog.title") })).toBeVisible();
  await expect(welcome(page)).toBeVisible();
  // N9: a student with no course sees ОРТ first; the one «Войти по коду» is the header's
  const chips = page.getByRole("group", { name: t("catalog.groups.label") });
  await expect(chips.getByRole("link", { name: t("exam.family.ort") })).toHaveAttribute("aria-current", "page");
  const main = page.locator("main#main");
  await expect(main.getByRole("link", { name: t("home.primary.join") })).toHaveCount(1);
  await expect(main.getByRole("link", { name: t("home.primary.join") })).toHaveAttribute("href", `/${L}/courses/join`);
  await expect(main.locator(`a[href="/${L}/courses/choose"]`)).toHaveCount(0); // no «Подобрать курсы»
  await shot(page, "catalog-welcome");
  await noSideScroll(page);
  await page.setViewportSize(VIEWPORTS.desktop);
  expect((await apiAs(page, "/me/home")).courses).toHaveLength(0); // nothing joined without a tap

  // «×» replaces the URL without the parameter
  await page.getByRole("button", { name: t("catalog.welcomeClose") }).click();
  await expect(page).toHaveURL(new RegExp(`/${L}/courses/catalog$`));
  await expect(welcome(page)).toHaveCount(0);
  // a reload keeps it while the parameter is there; any chip drops it
  await page.goto(`/${L}/courses/catalog?welcome=1`);
  await expect(welcome(page)).toBeVisible();
  await chips.getByRole("link", { name: t("exam.family.nct") }).click();
  await expect(page).toHaveURL(new RegExp(`/${L}/courses/catalog\\?exam=nct$`));
  await expect(welcome(page)).toHaveCount(0);

  // the old choose step's links redirect (V15)
  await page.goto(`/${L}/courses/choose?first=1`);
  await page.waitForURL(new RegExp(`/${L}/courses/catalog\\?welcome=1$`));
  await page.goto(`/${L}/courses/choose?x=1`);
  await page.waitForURL(new RegExp(`/${L}/courses/catalog$`));

  // the catalog landing's «Записаться» lands on the course Обзор
  await page.goto(`/${L}/courses/catalog/${made.physics}`);
  await page.getByRole("button", { name: t("catalog.join"), exact: true }).click();
  await page.waitForURL(new RegExp(`/${L}/courses/${made.physics}$`));
  await expect(page.getByRole("navigation", { name: t("course.tabs.label") }).getByRole("link", { name: t("course.tabs.overview"), exact: true }))
    .toHaveAttribute("aria-current", "page");
  await page.context().close();
});

test("sign-up under 14: the privacy page wins over the catalog", async ({ browser }) => {
  test.setTimeout(120_000);
  const page = await fresh(browser, VIEWPORTS.phone);
  await page.route("**/me/guardians", (r) => r.fulfill({ json: [] }));
  await page.goto(`/${L}/register`);
  await page.getByRole("button", { name: t("privacy.age.under_14") }).click();
  const email = `e2e-welcome-child-${rand()}@example.com`;
  await page.getByLabel(t("auth.displayName")).fill("Бала Пробный");
  await page.getByLabel(t("auth.email")).fill(email);
  await page.getByLabel(t("auth.password")).fill(PASSWORD);
  await page.getByRole("button", { name: t("auth.signUpButton") }).click();
  await expect(page.getByRole("heading", { name: t("auth.verify.title") })).toBeVisible();
  await page.getByLabel(t("auth.verify.codeLabel")).fill(await emailCode(email));
  await page.getByRole("button", { name: t("auth.verify.button") }).click();
  await expect(page).toHaveURL(new RegExp(`/${L}/privacy$`));
  await page.context().close();
});

test("people who teach: /courses/choose → Teaching, no welcome line or code button; Student view's test student → the hub", async ({ browser }) => {
  test.setTimeout(180_000);
  const s = seed();
  const u = await registerApi(`e2e-welcome-teacher-${rand()}@example.com`, "Бектур Учитель");
  await api(s.admin, "POST", `/platform/users/${u.profile.id}/teacher-status`, { status: "approved" });
  u.profile = await api(u, "GET", "/auth/me");
  const course = await api(u, "POST", "/courses", { title: { ru: "Курс каталога E2E" }, languages: ["ru"], default_language: "ru" });
  await api(u, "POST", `/courses/${course.id}/publish`);
  teacher = { ...u, course_id: course.id };

  const page = await fresh(browser);
  await signIn(page, teacher);
  await page.goto(`/${L}/courses/choose?first=1`);
  await page.waitForURL(new RegExp(`/${L}/courses$`));
  await expect(page.getByRole("heading", { level: 1, name: t("courses.list.title") })).toBeVisible();
  await page.goto(`/${L}/courses/catalog?welcome=1`);
  await expect(page.getByRole("heading", { level: 1, name: t("catalog.title") })).toBeVisible();
  await expect(welcome(page)).toHaveCount(0);
  await expect(page.locator("main#main").getByRole("link", { name: t("home.primary.join") })).toHaveCount(0);

  // Student view: the test student has no catalog; the old step leads to the hub
  await page.goto(`/${L}/courses/${course.id}`);
  await page.getByRole("button", { name: t("studentView.button") }).click();
  await expect(page.getByRole("status").filter({ hasText: t("studentView.banner") })).toBeVisible();
  await page.goto(`/${L}/courses/choose`);
  await page.waitForURL(new RegExp(`/${L}/home$`));
  await page.context().close();
});

test("?redirect= wins over the catalog: a teacher-code sign-up lands on the join page", async ({ browser }) => {
  test.setTimeout(120_000);
  const page = await fresh(browser, VIEWPORTS.phone);
  await signUp(page, `e2e-welcome-code-${rand()}@example.com`, `/${L}/register?redirect=${encodeURIComponent(`/${L}/courses/join?code=E2EJOIN1`)}`);
  await expect(page).toHaveURL(new RegExp(`/${L}/courses/join\\?code=E2EJOIN1$`));
  await page.context().close();
});

test("the catalog: family chips, subject sections, ?exam= in the URL; read-only for a teacher", async ({ browser }) => {
  test.setTimeout(180_000);
  const page = await fresh(browser);
  await signIn(page, seed().hub.empty);
  await page.goto(`/${L}/courses/catalog`);
  const chips = page.getByRole("group", { name: t("catalog.groups.label") });
  await expect(chips.getByRole("link")).toHaveText([t("exam.family.ort"), t("exam.family.nct"), t("catalog.groups.teachers")]);
  await expect(chips.getByRole("link", { name: t("exam.family.ort") })).toHaveAttribute("aria-current", "page"); // N9: ОРТ
  const main = page.locator("main");
  for (const name of [t("catalog.groups.mainCourse"), t("exam.subject.math"), t("exam.subject.physics"), t("exam.subject.chemistry")]) {
    await expect(main.getByRole("heading", { level: 2, name, exact: true })).toBeVisible();
  }
  // the main course section first, both languages
  const first = main.getByRole("region", { name: t("catalog.groups.mainCourse") });
  await expect(first.locator(`a[href="/${L}/courses/catalog/${made.ortRu}"]`)).toHaveCount(1);
  await expect(first.locator(`a[href="/${L}/courses/catalog/${made.ortKy}"]`)).toHaveCount(1);
  await expect(welcome(page)).toHaveCount(0); // no `?welcome=1`: no line
  await expect(page.locator("#catalog-q")).toHaveCount(0); // a family view has no search
  await shot(page, "catalog-ort");
  await noSideScroll(page);
  await page.setViewportSize(VIEWPORTS.desktop);

  await chips.getByRole("link", { name: t("exam.family.nct") }).click();
  await expect(page).toHaveURL(new RegExp(`/${L}/courses/catalog\\?exam=nct$`));
  await expect(main.getByRole("heading", { level: 2, name: t("exam.subject.biology"), exact: true })).toBeVisible();
  await expect(main.locator(`a[href="/${L}/courses/catalog/${made.ortRu}"]`)).toHaveCount(0);
  await chips.getByRole("link", { name: t("catalog.groups.teachers") }).click();
  await expect(page).toHaveURL(new RegExp(`/${L}/courses/catalog\\?exam=other$`));
  await expect(page.locator("#catalog-q")).toBeVisible();
  await expect(main.locator(`a[href="/${L}/courses/catalog/${made.maths}"]`)).toHaveCount(0);
  await page.context().close();

  // a teacher: the chips, no join buttons
  const tp = await fresh(browser);
  await signIn(tp, teacher);
  await tp.goto(`/${L}/courses/catalog?exam=ort`);
  await expect(tp.getByRole("group", { name: t("catalog.groups.label") })).toBeVisible();
  await expect(tp.locator("main").locator(`a[href="/${L}/courses/catalog/${made.maths}"]`)).toHaveCount(1);
  await expect(tp.getByRole("button", { name: t("catalog.join"), exact: true })).toHaveCount(0);
  await tp.context().close();
});
