import { expect, test, type Locator, type Page } from "@playwright/test";
import { seed, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";
import { expectedArea, expectedFrame, expectsLearning, expectsPro, type Role } from "../src/lib/lms/roleLinks";

/**
 * Fix round 2026-11-12 1b: the automated per-role link check. For each role: open its entry pages, collect every link
 * of the account menu, the area switcher (and its choices), the sidebars, the tab bar, the "Ещё" sheet, the course
 * drawer and the course header (breadcrumbs); visit each and assert the landed page has the frame and the area the
 * shell's own rules give (`src/lib/lms/roleLinks.ts`, read from `data-shell` / `data-area` on the LmsShell root), no API
 * answer >= 400, no generic error text, and no dead link (a link to the page it sits on without `aria-current`).
 * Menu contents: Pro only for students; no «Учёба» for anyone who teaches (owner decision 2026-11-12: teachers and
 * students are separate accounts; `teacher_enrolled` is a teacher with a leftover student enrolment).
 * Read-only: no link that writes is followed (attempt pages are skipped; actions are buttons, never clicked here).
 * Step 3a S7 (STUDENT_IA_DESIGN v3 V14): on every page the student lands on, no link to `/ru/courses` (the old «Мои
 * курсы»; the entry itself redirects to the hub) and «Войти по коду» (`/ru/courses/join`) only on the catalog.
 */
const t = (key: string) => tr("ru", key);

/** The signed-in app's routes (LmsShell); any other page (help, policies) only has to load without an error. */
const LMS_ROUTE = /^\/ru\/(home|courses|admin|org|grading-schemes|exam-templates|invitations|parent|privacy|pro)(\/|\?|$)/; // step 3a S3: /home

interface Found { href: string; from: string; current: boolean; brand: boolean }

/** Path + query of a link or a URL on the web origin. */
function norm(href: string): string {
  const u = new URL(href, "http://x");
  return u.pathname.replace(/\/+$/, "") + u.search;
}

async function linksIn(scope: Locator, from: string, into: Map<string, Found>) {
  const rows = await scope.evaluateAll((els) => els.map((a) => ({
    href: a.getAttribute("href") || "",
    current: a.hasAttribute("aria-current"),
    label: `${a.getAttribute("aria-label") || ""} ${(a.textContent || "").trim()}`,
  })));
  for (const r of rows) {
    if (!r.href.startsWith("/ru/") && r.href !== "/ru") continue; // external, mailto, the skip link
    const key = norm(r.href);
    if (/\/attempts\//.test(key) || /\/(login|logout)$/.test(key)) continue;
    if (!into.has(key)) into.set(key, { href: key, from, current: r.current, brand: r.label.includes(t("common.appName")) });
  }
}

/** Every link of the frame on this page, with each menu, switcher, sheet and drawer opened once. */
async function collect(page: Page, from: string, into: Map<string, Found>) {
  await linksIn(page.locator("header a[href], aside a[href], nav a[href]"), from, into);
  const toggles = page.locator(`header button[aria-expanded="false"], aside button[aria-expanded="false"], nav button[aria-expanded="false"], main button[aria-expanded="false"]:has-text("${t("courseNav.menu")}")`);
  // pinned by a test-only attribute: the selector above stops matching a toggle once it is open
  const count = await toggles.evaluateAll((els) => { els.forEach((el, i) => el.setAttribute("data-rl-toggle", String(i))); return els.length; });
  for (let i = 0; i < count; i++) {
    const button = page.locator(`[data-rl-toggle="${i}"]`);
    if (!(await button.count())) continue;
    if (!(await button.isVisible().catch(() => false))) continue;
    await button.click();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    const controls = await button.getAttribute("aria-controls");
    if (controls) await linksIn(page.locator(`[id="${controls}"] a[href]`), from, into);
    await linksIn(page.locator("dialog[open] a[href], [role='dialog'] a[href]"), from, into);
    await page.keyboard.press("Escape");
    if ((await button.getAttribute("aria-expanded")) === "true") await button.click().catch(() => {});
    await expect(button).toHaveAttribute("aria-expanded", "false");
  }
}

/** Step 3a S7 (V1, V5): the student's page rules, on the page as it landed (frame and content). */
async function studentPageRules(page: Page, label: string, landed: string, problems: string[]) {
  const hrefs = await page.locator("a[href]").evaluateAll((els) => els.map((a) => a.getAttribute("href") || ""));
  const paths = hrefs.filter((h) => h.startsWith("/ru/")).map((h) => norm(h));
  if (paths.some((h) => h === "/ru/courses" || h.startsWith("/ru/courses?"))) problems.push(`${label}: a link to /ru/courses on ${landed}`);
  const code = paths.filter((h) => h === "/ru/courses/join" || h.startsWith("/ru/courses/join?"));
  const inCatalog = landed === "/ru/courses/catalog" || landed.startsWith("/ru/courses/catalog?") || landed.startsWith("/ru/courses/catalog/");
  if (code.length > 0 && !inCatalog) problems.push(`${label}: «Войти по коду» on ${landed}`);
  if ((landed === "/ru/courses/catalog" || landed.startsWith("/ru/courses/catalog?")) && code.length !== 1) {
    problems.push(`${label}: ${code.length} «Войти по коду» links on the catalog, expected 1`);
  }
}

/** Opens a URL and waits until the frame is decided and the network is quiet. */
async function open(page: Page, url: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  if (LMS_ROUTE.test(norm(page.url()))) {
    await expect(page.locator("[data-shell]").first()).not.toHaveAttribute("data-shell", "neutral");
  }
}

async function frameOf(page: Page): Promise<string> {
  const root = page.locator("[data-shell]").first();
  return `${await root.getAttribute("data-shell")}/${await root.getAttribute("data-area")}`;
}

/** The whole walk for one role; returns every problem found (empty: all links are right). */
async function walk(page: Page, role: Role, user: SeedUser, entries: string[]): Promise<{ problems: string[]; links: Map<string, Found> }> {
  const api = seed().api.replace(/\/+$/, "");
  const failed: string[] = [];
  page.on("response", (r) => {
    if (r.url().startsWith(api) && r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${r.url().slice(api.length)}`);
  });
  await signIn(page, user);
  const problems: string[] = [];
  const links = new Map<string, Found>();

  const check = async (label: string) => {
    const landed = norm(page.url());
    if (await page.locator("main, body").first().getByText(t("mascot.error.title")).count()) problems.push(`${label}: generic error text on ${landed}`);
    if (!LMS_ROUTE.test(landed)) return landed;
    const want = `${expectedFrame(role, landed)}/${expectedArea(role, landed)}`;
    try {
      await expect.poll(() => frameOf(page), { timeout: 5_000 }).toBe(want);
    } catch {
      problems.push(`${label}: ${landed} is ${await frameOf(page)}, expected ${want}`);
    }
    return landed;
  };

  for (const entry of entries) {
    failed.length = 0;
    await open(page, entry);
    const landed = await check(`entry ${entry}`);
    for (const f of failed) problems.push(`entry ${entry}: API ${f}`);
    if (role === "student") await studentPageRules(page, `entry ${entry}`, landed, problems);
    await collect(page, norm(page.url()), links);
  }
  // step 3a S7 (V5): no menu, sheet or sidebar carries «Войти по коду» any more (the catalog's page header does)
  const code = links.get("/ru/courses/join");
  if (role === "student" && code && !code.from.startsWith("/ru/courses/catalog")) problems.push(`«Войти по коду» in a menu (from ${code.from})`);
  for (const link of links.values()) {
    failed.length = 0;
    await open(page, link.href);
    const landed = await check(`link ${link.href} (from ${link.from})`);
    for (const f of failed) problems.push(`link ${link.href}: API ${f}`);
    if (role === "student") await studentPageRules(page, `link ${link.href}`, landed, problems);
    if (landed === link.from && norm(link.href) === link.from && !link.current && !link.brand) {
      problems.push(`link ${link.href} (from ${link.from}): a dead link to its own page`);
    }
  }

  // menu contents: Pro only for people who learn; no «Учёба» for anyone who teaches
  const pro = [...links.keys()].some((h) => h === "/ru/pro");
  if (pro !== expectsPro(role)) problems.push(`Pro in the menus: ${pro}, expected ${expectsPro(role)}`);
  if (!expectsLearning(role)) {
    if (links.has("/ru/courses?view=learning")) problems.push("a link to the Learning area (/ru/courses?view=learning)");
    await open(page, "/ru/courses");
    const learning = page.locator("header, aside, nav").getByRole("link", { name: t("shell.areas.learning"), exact: true });
    if (await learning.count()) problems.push("«Учёба» area on /ru/courses");
  }
  if (process.env.ROLE_LINKS_DEBUG) console.log(role, [...links.keys()].join("\n  "));
  return { problems, links };
}

// step 3a S7 (V14): every role opens the old choose step and «Мои курсы»: a learner lands in the catalog (with the
// welcome line) and on the hub, people who teach on their Teaching list
const ENTRY = {
  student: () => { const s = seed(); return { user: s.access!.student, entries: ["/ru/home", "/ru/courses", "/ru/courses/choose", "/ru/courses/catalog?welcome=1", `/ru/courses/${s.access!.course_id}`, "/ru/courses/catalog", "/ru/pro", "/ru/privacy"] }; },
  teacher: () => { const s = seed(); return { user: s.course_nav.teacher, entries: ["/ru/courses", "/ru/home", "/ru/courses/choose", `/ru/courses/${s.course_nav.course_id}`, "/ru/courses/catalog", `/ru/courses/catalog/${s.course_id}`, "/ru/pro"] }; },
  teacher_enrolled: () => {
    const s = seed();
    const u = s.teacher_enrolled;
    return { user: u, entries: ["/ru/courses", "/ru/home", "/ru/courses?view=learning", `/ru/courses/${u.course_id}`, `/ru/courses/${s.course_id}`, "/ru/courses/catalog", "/ru/courses/join", "/ru/pro"] };
  },
  org_admin: () => { const s = seed(); return { user: s.org_admin.org_admin, entries: ["/ru/courses", "/ru/home", "/ru/courses/choose", `/ru/org/${s.org_admin.organization_id}`, `/ru/courses/${s.org_admin.maths_course_id}`, "/ru/pro"] }; },
  platform_admin: () => { const s = seed(); return { user: s.admin, entries: ["/ru/courses", "/ru/home", "/ru/courses/choose", "/ru/admin", "/ru/admin/catalog", "/ru/admin/teachers", "/ru/org", `/ru/courses/${s.course_id}`, "/ru/pro"] }; },
} satisfies Record<Role, () => { user: SeedUser; entries: string[] }>;

for (const role of Object.keys(ENTRY) as Role[]) {
  test(`role links, desktop: ${role}`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize(VIEWPORTS.desktop);
    const { user, entries } = ENTRY[role]();
    const { problems, links } = await walk(page, role, user, entries);
    expect(links.size, "links found").toBeGreaterThan(3);
    expect(problems).toEqual([]);
  });
}

// 375 px: the tab bar, the "Ещё" sheet, the phone area menu and the course drawer
for (const role of ["student", "teacher"] as const) {
  test(`role links, phone 375: ${role}`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize(VIEWPORTS.phone);
    const { user, entries } = ENTRY[role]();
    const { problems, links } = await walk(page, role, user, entries.slice(0, 2));
    expect(links.size, "links found").toBeGreaterThan(3);
    expect(problems).toEqual([]);
  });
}

test("a teacher with a leftover student enrolment: the course they studied is not theirs, no Join in the catalog", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  await signIn(page, s.teacher_enrolled);
  await open(page, `/ru/courses/${s.course_id}`);
  await expect(page.getByRole("heading", { name: t("courses.notYours.title") })).toBeVisible();
  expect(await frameOf(page)).toBe("app/teaching");
  await open(page, `/ru/courses/catalog/${s.course_id}`);
  await expect(page.getByRole("button", { name: t("catalog.join") })).toHaveCount(0);
  await open(page, "/ru/courses/join");
  await expect(page.getByText(t("lms.errors.teacher_cannot_enroll"))).toBeVisible();
  // the account menu: Privacy, never Pro
  await page.getByRole("button", { name: new RegExp(`^${t("shell.account.menu").split("{name}")[0]}`) }).click();
  await expect(page.getByRole("link", { name: t("privacy.title") })).toBeVisible();
  await expect(page.getByRole("link", { name: t("access.pro.menu"), exact: true })).toHaveCount(0);
});

test("a teacher's course list: the whole card opens the course's management view; Student view only on the course page", async ({ page }) => {
  // owner 2026-11-12: no «Режим ученика» on the cards of «Курсы, которые я веду» (nor on the catalog's cards)
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  const teacher = s.course_nav.teacher;
  await signIn(page, teacher);
  await open(page, "/ru/courses");
  const cards = page.locator("main").getByRole("listitem");
  await expect(cards.first()).toBeVisible();
  await expect(page.locator("main").getByRole("button", { name: t("studentView.button") })).toHaveCount(0);
  await open(page, "/ru/courses/catalog");
  await expect(page.locator("main").getByRole("button", { name: t("studentView.button") })).toHaveCount(0);
  await open(page, "/ru/courses");
  const card = cards.filter({ has: page.locator(`a[href="/ru/courses/${s.course_nav.course_id}"]`) }).first();
  await card.locator(`a[href="/ru/courses/${s.course_nav.course_id}"]`).first().click();
  await expect(page).toHaveURL(new RegExp(`/ru/courses/${s.course_nav.course_id}$`));
  await expect(page.locator("[data-shell]").first()).not.toHaveAttribute("data-shell", "neutral");
  expect(await frameOf(page)).toBe(`${expectedFrame("teacher", `/ru/courses/${s.course_nav.course_id}`)}/${expectedArea("teacher", `/ru/courses/${s.course_nav.course_id}`)}`);
  await expect(page.getByRole("button", { name: t("studentView.button") })).toBeVisible(); // top right of the course page
});

test("Admin → Каталог: the platform admin's page, refused for everyone else; the Teaching list has no catalog link", async ({ page }) => {
  // step 3b S2 (CATALOG_AND_TEACHERS_DESIGN 2.4, 2.5): the server refuses `/platform/catalog`; the page says so
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  for (const user of [s.course_nav.teacher, s.org_admin.org_admin, s.access!.student]) {
    const r = await fetch(`${s.api}/api/v1/platform/catalog?state=pending`, { headers: { Authorization: `Bearer ${user.token}` } });
    expect(r.status, user.email).toBe(403);
  }
  const teacher = s.course_nav.teacher;
  await signIn(page, teacher);
  await open(page, "/ru/admin/catalog");
  await expect(page.locator("main").getByText(t("platformAdmin.notAuthorized.title"), { exact: true })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
  await open(page, "/ru/courses");
  await expect(page.locator("main").getByRole("listitem").first()).toBeVisible();
  await expect(page.locator(`main a[href="/ru/courses/catalog"]`)).toHaveCount(0);
});

test("Admin → Преподаватели: the platform admin's page, refused for everyone else; the old address redirects", async ({ page }) => {
  // step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2, D9): the server refuses `/platform/teachers`; the page says so
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  for (const user of [s.course_nav.teacher, s.org_admin.org_admin, s.access!.student]) {
    const r = await fetch(`${s.api}/api/v1/platform/teachers`, { headers: { Authorization: `Bearer ${user.token}` } });
    expect(r.status, user.email).toBe(403);
  }
  await signIn(page, s.course_nav.teacher);
  await open(page, "/ru/admin/teachers");
  await expect(page.locator("main").getByText(t("platformAdmin.notAuthorized.title"), { exact: true })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);

  await signIn(page, s.admin);
  await open(page, "/ru/admin/teacher-requests?status=rejected");
  await expect(page).toHaveURL(/\/ru\/admin\/teachers\?tab=requests&status=rejected$/);
  expect(await frameOf(page)).toBe("app/platform");
  await expect(page.getByRole("tab", { name: new RegExp(t("platformAdmin.teachers.tabs.requests")) })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel(t("platformAdmin.requests.filter"))).toHaveValue("rejected");
});

test("an independent teacher never sees the word «организация»: Teaching, course pages, new course, exam templates", async ({ page }) => {
  // step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.3, D4): the personal organization is an implementation detail; the only
  // exception (an invitation banner from a school) does not apply to this teacher
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  const cid = s.course_nav.course_id;
  await signIn(page, s.course_nav.teacher);
  for (const url of ["/ru/courses", "/ru/home", "/ru/courses/new", "/ru/exam-templates", `/ru/courses/${cid}`,
    `/ru/courses/${cid}/settings`, `/ru/courses/${cid}/people`]) {
    await open(page, url);
    await expect(page.locator("main").first()).toBeVisible();
    const text = await page.locator("body").innerText();
    expect(text, url).not.toMatch(/организац/i);
  }
});
