import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Phase 8c navigation walk (PHASE_8C_DESIGN 12, S4a): the course sidebar and everything built on it.
 *
 *  1. sidebar links, order and active states for a teacher (staff-only links, "hidden from students" marks)
 *  2. phone drawer ("Course menu" button + sheet) for a student at 375 px
 *  3. auto-hide for students (Announcements and Files appear with published content; the "not available" page)
 *  4. redirects of the old URLs (section 4.2), query strings kept
 *  5. Student view: banner, student sidebar, a write is refused (403 `student_view_read_only`), "Start" in view mode
 *     starts a preview attempt, hand-ins are off
 *  6. To do panel -> assignment page on the Submissions tab with `filter=to_grade`
 *  7. "Unsorted" group and "Move to module"
 *  8. grouped "+ Add -> Quiz": lands in the 7c editor, Back returns to the module (`from=...#m-{id}`)
 *
 * Parts 1-3 and the S1 half of 4 and 5 run against the S1 shell. The rest is written against the design's roles and
 * i18n keys (`todo.*`, `coursePage.*`, `assignments.page.*`) and waits for S2 (Course page) and S3 (one-page objects).
 *
 * Data: `seed_backend.py` (`seed_course_nav`, written after every other row): course "Навигация E2E" of an approved
 * teacher, published and empty, three enrolled students (`sidebar`, `handin`, `phone`). The tests create their own
 * content through the API with unique titles, in order (serial). Student view runs as the course ASSISTANT: the owner teacher administers their own organization, so the
 * server never downgrades them (org admins are not downgraded). "Start" uses the seeded published quiz.
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/course-nav.spec.ts
 * (in a git worktree add E2E_PYTHON=<main repo>/backend/venv/bin/python).
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);

const HAND_IN = "Работа для проверки";
const ANN_TITLE = "Объявление навигации";
const FILE_TITLE = "Файл навигации";
const PAGE_TITLE = "Страница вне модуля";
const LOOSE_TASK = "Задание вне модуля";
const QUIZ_VIEW = "Квиз из карточки";
const MOD_A = "Модуль навигации А";
const MOD_B = "Модуль навигации Б";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

const nav = () => seed().course_nav;
const base = () => `/${L}/courses/${nav().course_id}`;

async function api(user: SeedUser, method: string, path: string, body?: unknown, ok: number[] = [200, 201, 204]) {
  const r = await fetch(`${seed().api}/api/v1${path}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(ok, `${method} ${path} -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

async function open(browser: Browser, user: SeedUser, viewport: { width: number; height: number } = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

/** The course sidebar (desktop side nav) in any role: same landmark name as the old tab bar. */
const sidebar = (page: Page) => page.getByRole("navigation", { name: t("courses.home.tabsLabel") });
/** One sidebar link by label; a staff link with a "hidden from students" mark carries the mark's text in its name. */
const link = (page: Page, key: string) => sidebar(page).getByRole("link", { name: new RegExp(`^${esc(t(key))}(\\s|$)`) });
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** The "hidden from students" mark inside a link (`role=img`, design 2.3). */
const mark = (l: Locator) => l.locator('[role="img"]');
const linkNames = async (page: Page) => (await sidebar(page).getByRole("link").allInnerTexts()).map((s) => s.trim());

/** Sidebar link keys in design order (2.2). */
const LINKS = {
  course: "courses.home.tab",
  announcements: "announcements.title",
  assignments: "assignments.tab",
  grades: "gradebook.tab",
  people: "courses.people.tab",
  bank: "bank.tab",
  settings: "courses.settings.tab",
  files: "courseFiles.title",
} as const;

async function createTextAssignment(title: string, published = true): Promise<string> {
  const a = await api(nav().teacher, "POST", `/courses/${nav().course_id}/assignments`, { kind: "text", title: { ru: title }, points_possible: 10 });
  if (published) await api(nav().teacher, "PATCH", `/courses/${nav().course_id}/assignments/${a.id}`, { published: true });
  return a.id;
}

async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(over, "horizontal page scroll").toBeLessThanOrEqual(0);
}

test.describe("course navigation (ru)", () => {
  test.describe.configure({ mode: "serial" });

  let quizAssignment = "";
  let quizAssessment = "";
  let pageId = "";

  test("setup: a quiz and a page the checks below navigate to", async () => {
    const q = await api(nav().teacher, "POST", `/courses/${nav().course_id}/assignments`, {
      kind: "quiz", title: { ru: "Квиз навигации" }, quiz: { preset: "none", languages: ["ru"] },
    });
    quizAssignment = q.id;
    quizAssessment = q.assessment_id;
    expect(quizAssessment).toBeTruthy();
    const p = await api(nav().teacher, "POST", `/courses/${nav().course_id}/pages`, { title: "Страница навигации", language: "ru", body_md: "Текст.", published: false });
    pageId = p.id;
  });

  // ---------------------------------------------------------------- 1. sidebar, teacher
  test("teacher: sidebar links, order, hidden marks, active states, no Teaching sub-menu", async ({ browser }) => {
    const tp = await open(browser, nav().teacher);
    await tp.goto(base());
    await expect(sidebar(tp)).toBeVisible();
    // eight links in the design order; staff see them all (2.2)
    expect(await linkNames(tp)).toEqual(Object.values(LINKS).map((k) => t(k)));
    await expect(link(tp, LINKS.course)).toHaveAttribute("aria-current", "page");
    // Announcements and Files have nothing published: marked "hidden from students" (2.3) with a help line
    for (const k of [LINKS.announcements, LINKS.files]) {
      await expect(mark(link(tp, k))).toHaveAttribute("aria-label", t("courseNav.hiddenFromStudents"));
    }
    await expect(mark(link(tp, LINKS.assignments))).toHaveCount(0);
    await expect(tp.getByText(t("courseNav.hiddenHelp"))).toBeVisible();
    // the Teaching sub-menu (Courses / Create / Grading schemes / Exam templates) is gone inside a course (2.5)
    await expect(tp.getByRole("link", { name: t("lms.nav.gradingSchemes"), exact: true })).toHaveCount(0);
    // Student view button in the course bar (2.4)
    await expect(tp.getByRole("button", { name: t("studentView.button") })).toBeVisible();

    // clicking a link navigates and moves the active state
    for (const [k, path] of [["announcements", "announcements"], ["assignments", "assignments"], ["grades", "grades"], ["people", "people"],
      ["bank", "bank"], ["settings", "settings"], ["files", "files"]] as const) {
      await link(tp, LINKS[k]).click();
      await tp.waitForURL(new RegExp(`/courses/${nav().course_id}/${path}(\\?.*)?$`));
      await expect(link(tp, LINKS[k])).toHaveAttribute("aria-current", "page");
      await expect(sidebar(tp).locator('[aria-current="page"]')).toHaveCount(1);
    }
    // Assignments stays active on the quiz builder, the quiz lobby / attempts list (/assessments/**) and the objects
    for (const path of [`assessments/${quizAssessment}/edit`, `assessments/${quizAssessment}`, `assessments/${quizAssessment}/attempts`, `assignments/${quizAssignment}`]) {
      await tp.goto(`${base()}/${path}`);
      await expect(link(tp, LINKS.assignments)).toHaveAttribute("aria-current", "page");
    }
    // a page belongs to the Course link (pages are reached from the course page)
    await tp.goto(`${base()}/pages/${pageId}`);
    await expect(link(tp, LINKS.course)).toHaveAttribute("aria-current", "page");
    await tp.context().close();
  });

  // ---------------------------------------------------------------- 2. phone drawer, student
  test("phone: the sidebar is a 'Course menu' sheet", async ({ browser }) => {
    const sp = await open(browser, nav().students.phone, VIEWPORTS.phone);
    await sp.goto(base());
    const menu = sp.getByRole("button", { name: new RegExp(`^${t("courseNav.menu")}`) });
    await expect(menu).toBeVisible();
    await expect(menu).toContainText(t(LINKS.course)); // "Course menu · Course": the active link is named
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await expect(link(sp, LINKS.assignments)).toBeHidden(); // the side nav is for md and up
    await menu.click();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    const sheet = sp.getByRole("dialog");
    await expect(sheet.getByRole("link", { name: t(LINKS.assignments), exact: true })).toBeVisible();
    // Esc closes the sheet and keeps the page
    await sp.keyboard.press("Escape");
    await expect(sp.getByRole("dialog")).toHaveCount(0);
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    // choosing a link closes the sheet and the button names the new active link
    await menu.click();
    await sp.getByRole("dialog").getByRole("link", { name: t(LINKS.assignments), exact: true }).click();
    await sp.waitForURL(new RegExp(`/courses/${nav().course_id}/assignments`));
    await expect(sp.getByRole("dialog")).toHaveCount(0);
    await expect(menu).toContainText(t(LINKS.assignments));
    await noHorizontalScroll(sp);
    await sp.context().close();
  });

  // ---------------------------------------------------------------- 3. auto-hide for students
  test("student: Announcements and Files appear only with published content; 'not available' page before", async ({ browser }) => {
    const sp = await open(browser, nav().students.sidebar);
    await sp.goto(base());
    // before: Course, Assignments, Grades, Teachers (people) only
    await expect(link(sp, LINKS.course)).toHaveAttribute("aria-current", "page");
    expect(await linkNames(sp)).toEqual([t(LINKS.course), t(LINKS.assignments), t(LINKS.grades), t("courses.people.tabStudent")]);
    await expect(sp.getByText(t("courseNav.hiddenHelp"))).toHaveCount(0);
    // opening a hidden area by URL: the "not available" page, no list
    for (const area of ["announcements", "files"]) {
      await sp.goto(`${base()}/${area}`);
      await expect(sp.getByText(t("courseNav.unavailable.title"))).toBeVisible();
      await expect(sp.getByText(t("courseNav.unavailable.body"))).toBeVisible();
      await sp.getByRole("link", { name: t("courseNav.unavailable.back") }).click();
      await sp.waitForURL(new RegExp(`/courses/${nav().course_id}/?$`));
    }
    // a draft announcement changes nothing; posting it shows the link
    const ann = await api(nav().teacher, "POST", `/courses/${nav().course_id}/announcements`, { title: ANN_TITLE, body_md: "Текст объявления.", pinned: false, publish: false });
    await sp.goto(base());
    await expect(link(sp, LINKS.announcements)).toHaveCount(0);
    await api(nav().teacher, "POST", `/courses/${nav().course_id}/announcements/${ann.id}/publish`, {}, [200, 201, 204]);
    await sp.goto(base());
    await expect(link(sp, LINKS.announcements)).toBeVisible();
    await link(sp, LINKS.announcements).click();
    await expect(sp.getByRole("heading", { name: ANN_TITLE })).toBeVisible();
    await expect(link(sp, LINKS.announcements)).toHaveAttribute("aria-current", "page");
    // a published file shows Files
    const form = new FormData();
    form.append("file", new Blob([PDF], { type: "application/pdf" }), "nav.pdf");
    form.append("folder", "");
    form.append("title", FILE_TITLE);
    form.append("published", "true");
    const up = await fetch(`${seed().api}/api/v1/courses/${nav().course_id}/course-files`, { method: "POST", headers: { Authorization: `Bearer ${nav().teacher.token}` }, body: form });
    expect(up.status).toBe(201);
    await sp.goto(base());
    await expect(link(sp, LINKS.files)).toBeVisible();
    await expect(mark(link(sp, LINKS.files))).toHaveCount(0); // students get no "hidden" mark
    await link(sp, LINKS.files).click();
    await expect(sp.getByText(FILE_TITLE, { exact: true })).toBeVisible();
    // staff now see both links without the hidden mark
    const tp = await open(browser, nav().teacher);
    await tp.goto(base());
    await expect(mark(link(tp, LINKS.announcements))).toHaveCount(0);
    await expect(mark(link(tp, LINKS.files))).toHaveCount(0);
    await tp.context().close();
    await sp.context().close();
  });

  // ---------------------------------------------------------------- 4. redirects (design 4.2)
  test("old URLs redirect, query strings are kept", async ({ browser }) => {
    const tp = await open(browser, nav().teacher);
    const c = `/courses/${nav().course_id}`;
    const landed = async (from: string, to: RegExp) => {
      await tp.goto(`/${L}${c}${from}`);
      await tp.waitForURL((u) => to.test(u.pathname + u.search));
      await expect(sidebar(tp)).toBeVisible();
    };
    // S1: /assessments -> Assignments filtered to quizzes; ?new=1 -> the quiz form; staff /modules -> the Course page
    await landed("/assessments", new RegExp(`${c}/assignments\\?kind=quiz$`));
    await landed("/assessments?new=1", new RegExp(`${c}/assignments\\?new=quiz$`));
    await landed("/assessments?published=yes", new RegExp(`${c}/assignments\\?(published=yes&kind=quiz|kind=quiz&published=yes)$`));
    await landed("/modules", new RegExp(`${c}/?$`));
    // S3: the old assignment and page routes land on the object page
    await landed(`/assignments/${quizAssignment}/edit`, new RegExp(`${c}/assignments/${quizAssignment}\\?tab=settings`));
    await landed(`/assignments/${quizAssignment}/grade?filter=to_grade`, new RegExp(`${c}/assignments/${quizAssignment}\\?(tab=submissions&filter=to_grade|filter=to_grade&tab=submissions)`));
    await landed(`/pages/${pageId}/edit`, new RegExp(`${c}/pages/${pageId}\\?tab=edit`));
    // staff on /assignments/{id} stay on the object page (no redirect to /edit any more)
    await tp.goto(`/${L}${c}/assignments/${quizAssignment}`);
    await expect(tp).toHaveURL(new RegExp(`${c}/assignments/${quizAssignment}$`));
    await tp.context().close();

    // students: /assessments goes to the quiz filter, /modules stays (their outline), the object URL is unchanged
    const sp = await open(browser, nav().students.sidebar);
    await sp.goto(`/${L}${c}/assessments`);
    await sp.waitForURL(new RegExp(`${c}/assignments\\?kind=quiz$`));
    await sp.goto(`/${L}${c}/modules`);
    await expect(sp).toHaveURL(new RegExp(`${c}/modules$`));
    await sp.context().close();

    // ORT courses: ?new=1 goes to the Course page (exam list), which opens its create dialog
    const ap = await open(browser, seed().admin);
    await ap.goto(`/${L}/courses/${seed().course_id}/assessments?new=1`);
    await ap.waitForURL(new RegExp(`/courses/${seed().course_id}\\?new=1$`));
    await expect(ap.getByRole("dialog", { name: t("assessments.create.title") })).toBeVisible();
    await ap.context().close();
  });

  // ---------------------------------------------------------------- 5. Student view
  test("Student view: banner, student sidebar, writes refused, hand-ins off, leave", async ({ browser }) => {
    const cid = nav().course_id;
    const taskId = await createTextAssignment("Задание для обзора");
    const outlineBefore = await api(nav().teacher, "GET", `/courses/${cid}/modules`);
    const tp = await open(browser, nav().students.assistant);
    await tp.goto(base());
    await tp.getByRole("button", { name: t("studentView.button") }).click();
    // the banner (role=status) is sticky over the student frame; the sidebar is the student's
    const banner = tp.getByRole("status").filter({ hasText: t("studentView.banner") });
    await expect(banner).toBeVisible();
    await expect(banner.getByRole("button", { name: t("studentView.leave") })).toBeVisible();
    await expect(link(tp, LINKS.bank)).toHaveCount(0); // staff-only link (assistants have no Settings)
    await expect(tp.getByRole("button", { name: t("studentView.button") })).toHaveCount(0);
    expect(await tp.evaluate((id) => window.sessionStorage.getItem(`studentView:${id}`), cid)).toBe("1");
    // every course request carries the header (the app's own reads succeed as student shapes)
    const sawHeader = tp.waitForRequest((r) => r.url().includes(`/api/v1/courses/${cid}/`) && r.headers()["x-view-as"] === "student");
    await tp.goto(`${base()}/assignments`);
    await sawHeader;
    // hand-ins are off in the student view of an assignment
    await tp.goto(`${base()}/assignments/${taskId}`);
    await expect(tp.getByText(t("studentView.handInsOff"))).toBeVisible();
    // a write with the header is refused and changes nothing
    const refused = await fetch(`${seed().api}/api/v1/courses/${cid}/modules`, {
      method: "POST",
      headers: { Authorization: `Bearer ${nav().students.assistant.token}`, "Content-Type": "application/json", "X-View-As": "student" },
      body: JSON.stringify({ title: { ru: "Не должен появиться" } }),
    });
    expect(refused.status).toBe(403);
    expect((await refused.json()).error.code).toBe("student_view_read_only");
    const outlineAfter = await api(nav().teacher, "GET", `/courses/${cid}/modules`);
    expect(outlineAfter.modules.length).toBe(outlineBefore.modules.length);
    // reads with the header give student shapes; the same read without it is the staff outline
    const asStudent = await fetch(`${seed().api}/api/v1/courses/${cid}/modules`, { headers: { Authorization: `Bearer ${nav().students.assistant.token}`, "X-View-As": "student" } });
    expect(asStudent.status).toBe(200);
    expect("rules_version" in (await asStudent.json())).toBe(false);
    // leaving restores the staff frame
    await banner.getByRole("button", { name: t("studentView.leave") }).click();
    await expect(tp.getByRole("status").filter({ hasText: t("studentView.banner") })).toHaveCount(0);
    await expect(link(tp, LINKS.bank)).toBeVisible();
    expect(await tp.evaluate((id) => window.sessionStorage.getItem(`studentView:${id}`), cid)).toBeNull();
    await tp.context().close();
  });

  test("Student view: 'Start' on a quiz lobby starts a preview attempt", async ({ browser }) => {
    const cid = nav().course_id;
    const tp = await open(browser, nav().students.assistant);
    await tp.goto(base());
    await tp.getByRole("button", { name: t("studentView.button") }).click();
    await expect(tp.getByRole("status").filter({ hasText: t("studentView.banner") })).toBeVisible();
    await tp.goto(`${base()}/assessments/${nav().view_quiz}`);
    await tp.getByRole("button", { name: t("assessments.lobby.start") }).click();
    await tp.waitForURL(/\/attempts\/[0-9a-f-]{36}/);
    const attemptId = /\/attempts\/([0-9a-f-]{36})/.exec(tp.url())![1];
    const att = await api(nav().students.assistant, "GET", `/attempts/${attemptId}`);
    expect(att.is_preview).toBe(true);
    expect(cid).toBeTruthy();
    await tp.context().close();
  });

// ---------------------------------------------------------------- 6. To do deep link (S2 + S3)
  test("To do: 'to grade' links to the assignment's Submissions tab, filter to_grade", async ({ browser }) => {
    const cid = nav().course_id;
    const id = await createTextAssignment(HAND_IN);
    await api(nav().students.handin, "POST", `/courses/${cid}/assignments/${id}/submissions`, { body_text: "Мой ответ." }, [200, 201]);
    const tp = await open(browser, nav().teacher);
    await tp.goto(base());
    await expect(tp.getByRole("heading", { name: t("todo.title") })).toBeVisible();
    const toGrade = tp.locator(`a[href*="/assignments/${id}?tab=submissions"]`).first();
    await expect(toGrade).toContainText(HAND_IN);
    await toGrade.click();
    await tp.waitForURL(new RegExp(`/assignments/${id}\\?.*tab=submissions`));
    expect(new URL(tp.url()).searchParams.get("filter")).toBe("to_grade");
    await expect(tp.getByRole("tab", { name: t("assignments.page.tabs.submissions") })).toHaveAttribute("aria-selected", "true");
    await expect(tp.locator("button:visible", { hasText: "Nav handin" }).first()).toBeVisible();
    // the sidebar keeps Assignments active, not Grades
    await expect(link(tp, LINKS.assignments)).toHaveAttribute("aria-current", "page");
    await tp.context().close();
  });

  // ---------------------------------------------------------------- 7. Unsorted (S2)
  test("Unsorted group lists loose targets and moves one into a module", async ({ browser }) => {
    const cid = nav().course_id;
    const mod = await api(nav().teacher, "POST", `/courses/${cid}/modules`, { title: { ru: MOD_A }, published: true });
    await createTextAssignment(LOOSE_TASK);
    const pg = await api(nav().teacher, "POST", `/courses/${cid}/pages`, { title: PAGE_TITLE, language: "ru", body_md: "Текст.", published: true });
    const tp = await open(browser, nav().teacher);
    await tp.goto(base());
    const unsorted = tp.locator("section, details").filter({ has: tp.getByRole("heading", { name: t("coursePage.unsorted.title") }) }).first();
    await expect(unsorted).toBeVisible();
    for (const title of [LOOSE_TASK, PAGE_TITLE, FILE_TITLE]) await expect(unsorted.getByText(title, { exact: true })).toBeVisible();
    await expect(unsorted.getByRole("link", { name: t("coursePage.unsorted.allPages") })).toHaveAttribute("href", new RegExp(`/courses/${cid}/pages`));
    await expect(unsorted.getByRole("link", { name: t("coursePage.unsorted.allFiles") })).toHaveAttribute("href", new RegExp(`/courses/${cid}/files`));
    // move the page into the module
    const row = unsorted.locator("li").filter({ hasText: PAGE_TITLE });
    await row.getByRole("button", { name: t("modules.editor.actions") }).click();
    await tp.getByRole("menuitem", { name: t("coursePage.unsorted.moveTo") }).click();
    const dlg = tp.getByRole("dialog");
    await dlg.getByLabel(t("modules.move.target")).selectOption({ label: MOD_A });
    await dlg.getByRole("button", { name: t("modules.move.submit") }).click();
    await expect(dlg).toBeHidden();
    await expect(unsorted.getByText(PAGE_TITLE, { exact: true })).toHaveCount(0);
    await expect(tp.locator(`#m-${mod.id}`).getByText(PAGE_TITLE, { exact: true })).toBeVisible();
    // the page is referenced by the module now; the API agrees
    const un = await api(nav().teacher, "GET", `/courses/${cid}/modules/unsorted?kind=page`);
    expect(JSON.stringify(un)).not.toContain(pg.id);
    await tp.context().close();
  });

  // ---------------------------------------------------------------- 8. grouped "+ Add -> Quiz" (S2 + S3)
  test("'+ Add -> Quiz' opens the 7c editor and Back returns to the module", async ({ browser }) => {
    const cid = nav().course_id;
    const mod = await api(nav().teacher, "POST", `/courses/${cid}/modules`, { title: { ru: MOD_B }, published: false });
    const tp = await open(browser, nav().teacher);
    await tp.goto(base());
    const card = tp.locator(`#m-${mod.id}`);
    await expect(card).toBeVisible();
    // the menu groups: Content (page, file, link, header) and Assessment (quiz, assignment)
    await card.getByRole("button", { name: t("modules.editor.addItem") }).first().click();
    const menu = tp.getByRole("menu");
    await expect(menu.getByText(t("coursePage.addGroups.content"))).toBeVisible();
    await expect(menu.getByText(t("coursePage.addGroups.assessment"))).toBeVisible();
    for (const k of ["page", "file", "link", "header", "quiz", "assignment"]) {
      await expect(menu.getByRole("menuitem", { name: t(`coursePage.addItems.${k}`) })).toBeVisible();
    }
    await menu.getByRole("menuitem", { name: t("coursePage.addItems.quiz") }).click();
    const dlg = tp.getByRole("dialog", { name: t("modules.add.title") });
    await dlg.getByRole("textbox", { name: t("modules.add.quizTitle") }).fill(QUIZ_VIEW);
    for (const other of ["ky", "en"]) {
      const box = dlg.getByRole("checkbox", { name: t(`courses.languages.${other}`) });
      if (await box.isChecked()) await box.uncheck();
    }
    await dlg.getByRole("button", { name: t("modules.add.createQuiz") }).click();
    // the 7c editor, with the way back to the module in `from`
    await tp.waitForURL(/\/assessments\/[0-9a-f-]{36}\/edit/);
    const from = new URL(tp.url()).searchParams.get("from");
    expect(from).toBe(`${base()}#m-${mod.id}`);
    await expect(tp.getByText(t("quizEditor.section.emptyQuizTitle"))).toBeVisible();
    await expect(link(tp, LINKS.assignments)).toHaveAttribute("aria-current", "page");
    // Back / Close returns to the Course page at the module, which now lists the quiz
    await tp.locator(`a[href="${base()}#m-${mod.id}"]`).first().click();
    await tp.waitForURL(new RegExp(`${base()}#m-${mod.id}$`));
    await expect(tp.locator(`#m-${mod.id}`).getByText(QUIZ_VIEW, { exact: true })).toBeVisible();
    // a hostile `from` is ignored (same rule as the player's ?return=)
    const aid = (await api(nav().teacher, "GET", `/courses/${cid}/modules`)).modules
      .find((m: { id: string }) => m.id === mod.id).items.find((i: { target: { assessment_id?: string } | null }) => i.target?.assessment_id).target.assessment_id as string;
    await tp.goto(`${base()}/assessments/${aid}/edit?from=${encodeURIComponent("https://evil.example/x")}`);
    await expect(tp.getByText(t("quizEditor.section.emptyQuizTitle"))).toBeVisible();
    await expect(tp.locator('a[href^="https://evil.example"]')).toHaveCount(0);
    await settle(tp);
    await tp.context().close();
  });
});
