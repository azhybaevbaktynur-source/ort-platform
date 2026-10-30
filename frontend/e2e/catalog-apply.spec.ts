import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, uxShots, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Phase 9 S4 walk (PHASE_9_DESIGN 8.1, 11, 12): enrollment form builder → Settings → Enrollment (form mode + catalog)
 * → student catalog search → course landing → apply → teacher inbox → approve with a note → the student is in.
 * Phase 9 S5 adds: a withdrawn and a rejected application (the note on the landing), a new form version, `form_auto`
 * (enrolled at once), Student view refusing the application writes, and the UX-gate screens.
 *
 * Data: `seed_backend.py` (`seed_catalog_apply`, written after every other row): a published private course of an
 * approved teacher without a form, one applicant in no course and three more applicants (S5). Screens of each step
 * are written to `$E2E_DIR/phase9-s4/` (ru, 375 px and 1440 px) and the UX-gate set to `$E2E_DIR/phase9-s5/` (staff
 * ru + en, student ru + ky + en); they are not compared against baselines.
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/catalog-apply.spec.ts
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const FIELD_LABEL = "Имя и фамилия";
const ANSWER = "Айдана Асанова";
const NOTE = "Добро пожаловать в группу";
const REJECT_NOTE = "Группа уже набрана, подайте заявку в следующем месяце";

const data = () => seed().catalog_apply;
const shots = path.join(E2E_DIR, "phase9-s4");
const UX = "phase9-s5";
const STAFF: ("ru" | "en")[] = ["ru", "en"];
const STUDENT: ("ru" | "ky" | "en")[] = ["ru", "ky", "en"];

async function shot(page: Page, name: string) {
  for (const [vp, size] of [["375", VIEWPORTS.phone], ["1440", VIEWPORTS.desktop]] as const) {
    await page.setViewportSize(size);
    await settle(page, false);
    await page.screenshot({ path: path.join(shots, `${name}-${vp}.png`), fullPage: true });
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

async function as(browser: import("@playwright/test").Browser, user: SeedUser): Promise<Page> {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function api(user: SeedUser, method: string, p: string, body?: unknown, ok: number[] = [200, 201, 204], extra: Record<string, string> = {}) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...extra },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(ok, `${method} ${p} -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

/** Apply through the API with the active form's first field (the browser apply is walked once, above). */
async function applyByApi(user: SeedUser, answer: string) {
  const landing = await api(user, "GET", `/catalog/courses/${data().course_id}`);
  const key = landing.form.fields[0].key;
  return api(user, "POST", `/courses/${data().course_id}/applications`, { form_id: landing.form.id, answers: { [key]: answer } });
}

/** People → Applications (the inbox opens on "Pending"); `all`: every status (the reach of the inbox screens). */
async function openApplications(p: Page, lang: string, all = false) {
  await p.getByRole("tab", { name: tr(lang as "ru", "studentInvite.tabs.applications") }).click();
  await expect(p.locator("#applications-status")).toBeVisible();
  if (all) await p.locator("#applications-status").selectOption("");
  await settle(p);
}

test.describe.configure({ mode: "serial" });

test("teacher builds and activates the enrollment form", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  await page.goto(`/ru/courses/${data().course_id}/settings/enrollment-form`);
  await uxShots(page, UX, "course-form-builder-empty", STAFF);
  await page.getByRole("button", { name: t("enrollmentForm.empty.create") }).click();
  await page.getByRole("button", { name: t("enrollmentForm.addField") }).click();
  await page.getByRole("textbox", { name: t("enrollmentForm.field.label") }).fill(FIELD_LABEL);
  await page.getByRole("button", { name: t("lms.common.save"), exact: true }).click();
  await expect(page.getByText(t("enrollmentForm.saved"))).toBeVisible();
  await shot(page, "builder-edit");
  await uxShots(page, UX, "course-form-builder-edit", STAFF);

  await page.getByRole("tab", { name: t("enrollmentForm.tabs.preview") }).click();
  await expect(page.getByRole("textbox", { name: FIELD_LABEL })).toBeVisible();
  await shot(page, "builder-preview");
  await uxShots(page, UX, "course-form-builder-preview", STAFF, async (p, lang) => {
    await p.getByRole("tab", { name: tr(lang as "ru", "enrollmentForm.tabs.preview") }).click();
  });
  await page.getByRole("tab", { name: t("enrollmentForm.tabs.edit") }).click();

  await page.getByRole("button", { name: t("enrollmentForm.activate"), exact: true }).click();
  await page.locator("dialog[open]").getByRole("button", { name: t("enrollmentForm.activate"), exact: true }).click();
  await expect(page.getByText(t("enrollmentForm.status.active")).first()).toBeVisible();
  await page.context().close();
});

test("teacher turns on the application mode and the catalog", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  await page.goto(`/ru/courses/${data().course_id}/settings`);
  await expect(page.getByText(t("enrollmentForm.settings.active", { n: 1 }))).toBeVisible();
  await page.locator("#s-mode").selectOption("form_review");
  await page.getByRole("switch", { name: t("enrollmentForm.settings.catalog") }).click();
  const form = page.locator("form", { has: page.locator("#s-mode") });
  await form.getByRole("button", { name: t("lms.common.save") }).click();
  await expect(form.getByText(t("courses.settings.saved"))).toBeVisible();
  await shot(page, "settings-enrollment");
  await page.goto(`/ru/courses/${data().course_id}/settings`);
  await expect(page.locator("#s-mode")).toHaveValue("form_review");
  await page.locator("#s-mode").scrollIntoViewIfNeeded();
  await uxShots(page, UX, "course-settings-enrollment", STAFF);
  await page.context().close();
});

test("student finds the course, opens the landing and applies", async ({ browser }) => {
  const page = await as(browser, data().student);
  await page.goto("/ru/courses/catalog");
  await uxShots(page, UX, "student-catalog", STUDENT);
  const search = async (p: Page) => {
    await p.locator("#catalog-q").fill("анкетой");
    await expect(p.getByRole("link", { name: /ОРТ|ЖРТ|ORT/ })).toHaveCount(0);
  };
  await search(page);
  const card = page.locator("li", { has: page.getByRole("link", { name: "Курс с анкетой E2E" }) });
  await expect(card).toBeVisible();
  await expect(page.getByRole("link", { name: /ОРТ/ })).toHaveCount(0); // the search (debounced) hides the ORT courses
  await expect(card.getByText(t("catalog.modes.form_review"))).toBeVisible();
  await shot(page, "catalog-search");
  await uxShots(page, UX, "student-catalog-search", STUDENT, search);

  await card.getByRole("link", { name: "Курс с анкетой E2E" }).click();
  await expect(page.getByRole("heading", { name: t("catalog.landing.howToJoin") })).toBeVisible();
  await shot(page, "landing-form");
  await uxShots(page, UX, "student-landing-form", STUDENT);

  await page.getByRole("link", { name: t("catalog.apply") }).click();
  await expect(page.getByText(t("applications.privacyNote"))).toBeVisible();
  await uxShots(page, UX, "student-apply", STUDENT);
  await page.getByRole("button", { name: t("applications.apply.submit") }).click();
  await expect(page.getByText(t("applications.answerErrors.required"))).toBeVisible(); // required, client-side
  await shot(page, "apply-errors");
  await uxShots(page, UX, "student-apply-errors", ["ru"]);
  await page.getByRole("textbox", { name: FIELD_LABEL }).fill(ANSWER);
  await page.getByRole("button", { name: t("applications.apply.submit") }).click();
  await expect(page.getByRole("heading", { name: t("applications.apply.sentTitle") })).toBeVisible();
  await shot(page, "apply-sent");
  await uxShots(page, UX, "student-apply-sent", ["ru"]);

  await page.goto(`/ru/courses/catalog/${data().course_id}`);
  await expect(page.getByText(t("applications.studentStatus.pending")).first()).toBeVisible();
  await shot(page, "landing-pending");
  await uxShots(page, UX, "student-landing-pending", STUDENT);

  // home: the "Pending applications" line
  await page.goto("/ru/courses");
  await expect(page.getByRole("heading", { name: t("applications.home.title") })).toBeVisible();
  await uxShots(page, UX, "student-home-pending", STUDENT);
  await page.context().close();
});

test("teacher approves the application with a note", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  await page.goto(`/ru/courses/${data().course_id}/people`);
  await openApplications(page, "ru");
  await uxShots(page, UX, "course-applications-inbox", STAFF, openApplications);
  const review = async (p: Page, lang: string) => {
    await openApplications(p, lang);
    await p.getByRole("button", { name: new RegExp(tr(lang as "ru", "applications.inbox.review")) }).click();
    await expect(p.locator("dialog[open]").getByText(ANSWER)).toBeVisible();
  };
  await page.getByRole("button", { name: new RegExp(t("applications.inbox.review")) }).click();
  const dialog = page.locator("dialog[open]");
  await expect(dialog.getByText(ANSWER)).toBeVisible();
  await uxShots(page, UX, "course-application-panel", STAFF, review);
  await dialog.getByRole("textbox", { name: new RegExp(t("applications.panel.note")) }).fill(NOTE);
  await shot(page, "inbox-panel");
  await dialog.getByRole("button", { name: t("applications.panel.approve") }).click();
  await expect(dialog.getByText(t("applications.status.approved"))).toBeVisible();
  await expect(dialog.getByText(NOTE)).toBeVisible(); // "Note shown to the student"
  await uxShots(page, UX, "course-application-approved", ["ru"]);
  await dialog.getByRole("button", { name: tr(L, "ui.close") }).first().click();
  await shot(page, "inbox-list");
  await page.context().close();
});

test("the student is in the course and sees the teacher's note on the landing", async ({ browser }) => {
  const page = await as(browser, data().student);
  await page.goto(`/ru/courses/catalog/${data().course_id}`);
  await expect(page.getByRole("link", { name: t("catalog.landing.openCourse") })).toBeVisible();
  await expect(page.getByText(NOTE)).toBeVisible();
  await uxShots(page, UX, "student-landing-approved", STUDENT);
  const roster = await api(data().teacher, "GET", `/courses/${data().course_id}/people?role=student&limit=50`);
  expect(roster.items.some((r: { user: { email: string } }) => r.user.email === data().student.email)).toBe(true);
  await page.context().close();
});

// ---------------------------------------------------------------- Phase 9 S5
test("an applicant withdraws; another is rejected with a note and sees it", async ({ browser }) => {
  const { withdraw, reject } = data().applicants;
  await applyByApi(withdraw, "Бакыт Отзыв");
  const wp = await as(browser, withdraw);
  await wp.goto(`/ru/courses/catalog/${data().course_id}`);
  await wp.getByRole("button", { name: t("applications.student.withdraw") }).click();
  await wp.locator("dialog[open]").getByRole("button", { name: t("applications.student.withdraw") }).click();
  await expect(wp.getByText(t("applications.studentStatus.withdrawn")).first()).toBeVisible();
  await expect(wp.getByRole("link", { name: t("catalog.landing.applyAgain") })).toBeVisible();
  await uxShots(wp, UX, "student-landing-withdrawn", STUDENT);
  await wp.context().close();

  await applyByApi(reject, "Нурлан Отказ");
  const tp = await as(browser, data().teacher);
  await tp.goto(`/ru/courses/${data().course_id}/people`);
  await openApplications(tp, "ru");
  await tp.locator("#applications-status").selectOption("pending");
  await tp.getByRole("button", { name: new RegExp(t("applications.inbox.review")) }).click();
  const dialog = tp.locator("dialog[open]");
  await dialog.getByRole("textbox", { name: new RegExp(t("applications.panel.note")) }).fill(REJECT_NOTE);
  await dialog.getByRole("button", { name: t("applications.panel.reject") }).click();
  await expect(dialog.getByText(t("applications.status.rejected"))).toBeVisible();
  await dialog.getByRole("button", { name: tr(L, "ui.close") }).first().click();
  await openApplications(tp, "ru", true);
  for (const s of ["approved", "rejected", "withdrawn"]) await expect(tp.getByRole("table").getByText(t(`applications.status.${s}`)).first()).toBeVisible();
  await uxShots(tp, UX, "course-applications-decided", STAFF, (p, lang) => openApplications(p, lang, true));
  await tp.context().close();

  const rp = await as(browser, reject);
  await rp.goto(`/ru/courses/catalog/${data().course_id}`);
  await expect(rp.getByText(t("applications.studentStatus.rejected")).first()).toBeVisible();
  await expect(rp.getByText(REJECT_NOTE)).toBeVisible();
  await uxShots(rp, UX, "student-landing-rejected", STUDENT);
  await rp.context().close();
});

test("Student view: the application writes are refused", async () => {
  const cid = data().course_id;
  const sv = { "X-View-As": "student" };
  const apps = await api(data().teacher, "GET", `/courses/${cid}/applications?status=rejected&limit=5`);
  const id = apps.items[0].id;
  for (const [p, body] of [[`/courses/${cid}/applications/${id}/approve`, {}], [`/courses/${cid}/enrollment-forms`, { fields: [] }]] as const) {
    const out = await api(data().teacher, "POST", p, body, [403], sv);
    expect(out.error.code, p).toBe("student_view_read_only");
  }
  await api(data().teacher, "GET", `/courses/${cid}/applications?limit=5`, undefined, [403, 404], sv);
});

test("teacher makes a new form version and switches to automatic approval; the next applicant is in at once", async ({ browser }) => {
  const tp = await as(browser, data().teacher);
  await tp.goto(`/ru/courses/${data().course_id}/settings/enrollment-form`);
  await expect(tp.getByText(t("enrollmentForm.immutable"))).toBeVisible();
  await tp.getByRole("button", { name: t("enrollmentForm.newVersion") }).first().click();
  await expect(tp.getByText(t("enrollmentForm.versionCreated")).first()).toBeVisible();
  await tp.getByRole("button", { name: t("enrollmentForm.activate"), exact: true }).click();
  await tp.locator("dialog[open]").getByRole("button", { name: t("enrollmentForm.activate"), exact: true }).click();
  await expect(tp.getByRole("heading", { name: t("enrollmentForm.versions.title") })).toBeVisible();
  await uxShots(tp, UX, "course-form-builder-versions", STAFF);

  await tp.goto(`/ru/courses/${data().course_id}/settings`);
  await tp.locator("#s-mode").selectOption("form_auto");
  const form = tp.locator("form", { has: tp.locator("#s-mode") });
  await form.getByRole("button", { name: t("lms.common.save") }).click();
  await expect(form.getByText(t("courses.settings.saved"))).toBeVisible();
  await tp.context().close();

  const ap = await as(browser, data().applicants.auto);
  await ap.goto(`/ru/courses/catalog/${data().course_id}`);
  await expect(ap.getByText(t("catalog.modes.form_auto")).first()).toBeVisible();
  await uxShots(ap, UX, "student-landing-auto", STUDENT);
  await ap.getByRole("link", { name: t("catalog.apply") }).click();
  await ap.getByRole("textbox", { name: FIELD_LABEL }).fill("Айгуль Авто");
  await ap.getByRole("button", { name: t("applications.apply.submit") }).click();
  await expect(ap.getByRole("heading", { name: t("applications.apply.approvedTitle") })).toBeVisible();
  await uxShots(ap, UX, "student-apply-approved", ["ru"]);
  await ap.getByRole("link", { name: t("catalog.landing.openCourse") }).first().click();
  await expect(ap).toHaveURL(new RegExp(`/courses/${data().course_id}`));
  const roster = await api(data().teacher, "GET", `/courses/${data().course_id}/people?role=student&limit=50`);
  expect(roster.items.some((r: { user: { email: string } }) => r.user.email === data().applicants.auto.email)).toBe(true);
  await ap.context().close();
});
