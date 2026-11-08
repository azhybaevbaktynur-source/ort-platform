import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { E2E_DIR, seed, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Accounts and teacher sign-up (docs/phases/ACCOUNTS.md D, E). Every test has its own person from `seed_teacher_signup`
 * (seed_backend.py) or creates one, so no test depends on another. Phone first: the apply page is walked at 375 px.
 */

const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const data = () => seed().teacher_signup;
const APPLY = "/ru/for-teachers/apply";
const PASSWORD = "e2e-pass-word-7";
const PHONE = "+996 555 123 456";

async function as(browser: Browser, user: SeedUser, viewport: { width: number; height: number } = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function api(user: SeedUser, p: string): Promise<any> { // eslint-disable-line @typescript-eslint/no-explicit-any
  const r = await fetch(`${seed().api}/api/v1${p}`, { headers: { Authorization: `Bearer ${user.token}` } });
  expect(r.status, p).toBe(200);
  return r.json();
}

/** The code the console email provider printed last for this address (backend log of the e2e backend). */
async function emailedCode(email: string): Promise<string> {
  const end = Date.now() + 30_000;
  while (Date.now() < end) {
    const blocks = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8").split("[EMAIL console] To: ").filter((b) => b.startsWith(`${email} `));
    const m = blocks[blocks.length - 1]?.match(/\b(\d{6})\b/);
    if (m) return m[1];
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`no code for ${email}`);
}

async function expectNoSidewaysScroll(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

/** One h1, and the values typed into the form are nowhere in the URL or browser storage. */
async function expectCleanPage(page: Page, secrets: string[]): Promise<void> {
  await expect(page.locator("h1")).toHaveCount(1);
  const stored = await page.evaluate(() => JSON.stringify([{ ...localStorage }, { ...sessionStorage }]));
  for (const secret of secrets) {
    expect(page.url()).not.toContain(encodeURIComponent(secret));
    expect(page.url()).not.toContain(secret);
    expect(stored).not.toContain(secret);
  }
}

async function fillApplication(page: Page, { name }: { name?: string } = {}): Promise<void> {
  if (name !== undefined) await page.getByLabel(t("teacherApply.field.name")).fill(name);
  await page.getByLabel(t("teacherApply.field.school"), { exact: true }).fill("Школа № 5");
  await page.getByLabel(t("teacherApply.field.subject")).fill("Физика");
  await page.getByLabel(t("teacherApply.field.phone")).fill(PHONE);
}

const send = (page: Page) => page.getByRole("button", { name: t("teacherApply.form.submit") }).click();
const areas = (page: Page) => page.getByRole("navigation", { name: t("shell.areas.label") }).getByRole("link").allInnerTexts();

test("a new person: account, emailed code, application, pending", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.phone, locale: "ru-RU", timezoneId: "UTC" });
  const page = await ctx.newPage();
  const email = "e2e-signup-new@example.com";
  const name = "Новый Преподаватель";

  await page.goto("/ru/for-teachers");
  await page.getByRole("main").getByRole("link", { name: t("landing.forTeachers.apply"), exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${APPLY}$`));
  await expect(page.getByRole("heading", { level: 1, name: t("teacherApply.title") })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.account.title") })).toBeVisible();
  await expect(page.getByRole("list", { name: t("teacherApply.steps.label") }).locator('[aria-current="step"]')).toContainText(t("teacherApply.steps.account"));

  // the mascot never pushes the form below the first screen of a phone
  const nameInput = page.getByLabel(t("auth.displayName"));
  const box = (await nameInput.boundingBox())!;
  expect(box.y + box.height).toBeLessThan(VIEWPORTS.phone.height);
  expect(box.height).toBeGreaterThanOrEqual(44);
  await expectNoSidewaysScroll(page);

  await nameInput.fill(name);
  await page.getByLabel(t("auth.email")).fill(email);
  await page.getByLabel(t("auth.password")).fill(PASSWORD);
  await page.getByLabel(t("teacherApply.age")).check();
  await page.getByRole("checkbox", { name: /политик|Политик/ }).check();
  const submit = page.getByRole("button", { name: t("teacherApply.account.submit") });
  await expect(submit).toBeEnabled();
  expect((await submit.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await submit.click();

  await expect(page.getByRole("heading", { level: 2, name: t("auth.verify.title") })).toBeVisible();
  await expectCleanPage(page, [PASSWORD, email]);
  await expectNoSidewaysScroll(page);
  await page.getByLabel(t("auth.verify.codeLabel")).fill(await emailedCode(email));
  await page.getByRole("button", { name: t("auth.verify.button") }).click();

  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.form.title") })).toBeVisible();
  await expect(page.getByLabel(t("teacherApply.field.name"))).toHaveValue(name);
  await expect(page.getByLabel(t("teacherApply.age"))).toHaveCount(0); // the sign-up already said so
  await expectNoSidewaysScroll(page);

  // mistakes are announced beside their field, and the first wrong field takes the focus
  await page.getByLabel(t("teacherApply.field.phone")).fill("12-34");
  await send(page);
  await expect(page.getByRole("alert").filter({ hasText: t("teacherApply.error.required") }).first()).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: t("teacherApply.error.phone") })).toBeVisible();
  await expect(page.getByLabel(t("teacherApply.field.school"), { exact: true })).toBeFocused();

  await fillApplication(page);
  await send(page);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.pending.title") })).toBeVisible();
  await expect(page.getByText("Школа № 5")).toBeVisible();
  await expect(page.getByText(PHONE)).toBeVisible();
  await expectCleanPage(page, [PASSWORD, PHONE, "Школа № 5"]);
  await expectNoSidewaysScroll(page);

  await page.goto("/ru/courses");
  await expect(page.getByRole("status").filter({ hasText: t("home.teacherApplication.pending") })).toBeVisible();
  await ctx.close();
});

test("an email already registered: log in and come back, with nothing in the URL", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.phone, locale: "ru-RU", timezoneId: "UTC" });
  const page = await ctx.newPage();
  const user = data().registered;
  await page.goto(APPLY);
  await page.getByLabel(t("auth.displayName")).fill("Кто-то");
  await page.getByLabel(t("auth.email")).fill(user.email);
  await page.getByLabel(t("auth.password")).fill(PASSWORD);
  await page.getByLabel(t("teacherApply.age")).check();
  await page.getByRole("checkbox", { name: /политик|Политик/ }).check();
  await page.getByRole("button", { name: t("teacherApply.account.submit") }).click();

  const alert = page.getByRole("alert").filter({ hasText: t("teacherApply.account.emailTaken") });
  await expect(alert).toBeVisible();
  await expectCleanPage(page, [PASSWORD, user.email]);
  const back = alert.getByRole("link", { name: t("teacherApply.account.emailTakenLink") });
  await expect(back).toHaveAttribute("href", `/ru/login?redirect=${encodeURIComponent(APPLY)}`);
  await back.click();

  await expect(page.getByRole("heading", { level: 1, name: t("auth.signInTitle") })).toBeVisible();
  await page.getByLabel(t("auth.email")).fill(user.email);
  await page.getByLabel(t("auth.password")).fill(user.password);
  await page.getByRole("button", { name: t("auth.signInButton") }).click();
  await expect(page).toHaveURL(new RegExp(`${APPLY}$`));
  await expect(page.getByRole("heading", { name: t("teacherApply.form.title") })).toBeVisible();
  await expect(page.getByLabel(t("teacherApply.field.name"))).toHaveValue(user.name); // leaving early left a normal account
  await ctx.close();
});

test("an existing student applies from the same page, without the account steps", async ({ browser }) => {
  const page = await as(browser, data().student, VIEWPORTS.phone);
  await page.goto(APPLY);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.form.title") })).toBeVisible();
  await expect(page.getByRole("list", { name: t("teacherApply.steps.label") })).toHaveCount(0);
  await expect(page.getByLabel(t("auth.password"))).toHaveCount(0);
  await expect(page.getByLabel(t("teacherApply.field.name"))).toHaveValue(data().student.name);
  await expect(page.getByLabel(t("teacherApply.age"))).toHaveCount(0);
  await fillApplication(page);
  await page.getByLabel(new RegExp(t("teacherApply.field.message"))).fill("Хочу вести курс.");
  await send(page);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.pending.title") })).toBeVisible();
  await expect(page.getByText("Хочу вести курс.")).toBeVisible();
  await page.context().close();
});

test("an account with no age band confirms 18+ and the policies on the form", async ({ browser }) => {
  const user = data().legacy;
  const page = await as(browser, user, VIEWPORTS.phone);
  await page.goto(APPLY);
  const age = page.getByLabel(t("teacherApply.age"));
  await expect(age).toBeVisible();
  await fillApplication(page);
  await expect(page.getByRole("button", { name: t("teacherApply.form.submit") })).toBeEnabled();
  await send(page);
  await expect(page.getByRole("alert").filter({ hasText: t("teacherApply.error.age") })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: t("teacherApply.error.policies") })).toBeVisible();
  await expect(age).toBeFocused();
  expect((await api(user, "/me/privacy")).age_band).toBeNull();

  await age.check();
  await page.getByRole("checkbox", { name: /политик|Политик/ }).check();
  await send(page);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.pending.title") })).toBeVisible();
  expect((await api(user, "/me/privacy")).age_band).toBe("18_plus");
  await page.context().close();
});

test("a known minor gets a plain refusal and no form", async ({ browser }) => {
  const page = await as(browser, data().minor, VIEWPORTS.phone);
  await page.goto(APPLY);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.minor.title") })).toBeVisible();
  await expect(page.getByLabel(t("teacherApply.field.phone"))).toHaveCount(0);
  await page.context().close();
});

test("pending: the status with the application's details, and no form", async ({ browser }) => {
  const page = await as(browser, data().pending);
  await page.goto(APPLY);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.pending.title") })).toBeVisible();
  await expect(page.getByText("Веду олимпиадную группу.")).toBeVisible();
  await expect(page.getByText("Лицей 7")).toBeVisible();
  await expect(page.getByLabel(t("teacherApply.field.phone"))).toHaveCount(0);
  await page.context().close();
});

test("rejected: the reason and the date during the wait; the dashboard says the same", async ({ browser }) => {
  const user = data().rejected;
  const page = await as(browser, user, VIEWPORTS.phone);
  await page.goto(APPLY);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.rejected.title") })).toBeVisible();
  await expect(page.getByText("Нет данных о школе")).toBeVisible();
  await expect(page.getByText(/Новую заявку можно подать с \d{2}\.\d{2}\.\d{4}/)).toBeVisible();
  await expect(page.getByLabel(t("teacherApply.field.phone"))).toHaveCount(0);
  await expectNoSidewaysScroll(page);

  await page.goto("/ru/courses");
  const line = page.getByRole("status").filter({ hasText: t("home.teacherApplication.rejected") });
  await expect(line).toContainText("Нет данных о школе");
  await expect(line).toContainText(/\d{2}\.\d{2}\.\d{4}/);
  await expect(line.getByRole("link")).toHaveCount(0);
  await page.context().close();
});

test("rejected after the wait: the form is back, with the earlier reason", async ({ browser }) => {
  const page = await as(browser, data().waited);
  await page.goto(APPLY);
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.form.title") })).toBeVisible();
  await expect(page.getByText(t("teacherApply.form.rejected"))).toBeVisible();
  await expect(page.getByText("Нет данных о школе")).toBeVisible();
  await page.context().close();
});

test("the admin reads the application and approves it; the header changes", async ({ browser }) => {
  const d = data();
  const user = d.approve;
  const student = await as(browser, user);
  await student.goto("/ru/courses");
  await expect(student.getByRole("heading", { name: t("home.dashboard") })).toBeVisible();
  await expect(student.getByRole("navigation", { name: t("shell.areas.label") })).toHaveCount(0);

  const admin = await as(browser, seed().admin);
  await admin.goto("/ru/admin/teacher-requests");
  const card = admin.getByRole("listitem").filter({ hasText: user.email });
  await expect(card.getByRole("link", { name: user.name })).toBeVisible();
  for (const text of [user.email, "Лицей 7", "Математика", "+996 700 111 222", "Преподаю пять лет."]) await expect(card.getByText(text)).toBeVisible();
  await expect(card.getByText(t("platformAdmin.requests.teachesAt"))).toHaveCount(0);

  // a school teacher who applies: the queue says where they teach, and nothing was cancelled
  const school = admin.getByRole("listitem").filter({ hasText: d.school_teacher.email });
  await expect(school.getByText(t("platformAdmin.requests.teachesAt"))).toBeVisible();
  await expect(school.getByText(d.school_name)).toBeVisible();

  await card.getByRole("button", { name: t("platformAdmin.requests.approve") }).click();
  await expect(card).toHaveCount(0);

  await student.reload();
  // owner feedback 2026-11-08 (item 2): a new teacher who learns nowhere has Teaching only; Learning's link opens it
  await expect.poll(() => areas(student)).toEqual([t("shell.areas.teaching")]);
  await student.goto("/ru/courses?view=learning");
  await expect(student).toHaveURL(/\/ru\/courses\?view=teaching$/);
  const line = student.getByRole("status").filter({ hasText: t("home.teacherApplication.approved") });
  await expect(line).toHaveCount(1); // shown once, on the Teaching view
  await expect(line.getByRole("link", { name: t("home.teacherApplication.approvedLink") })).toHaveAttribute("href", "/ru/courses?view=teaching");

  await student.goto(APPLY);
  await expect(student.getByRole("heading", { level: 2, name: t("teacherApply.approved.title") })).toBeVisible();
  await expect(student.getByRole("link", { name: t("teacherApply.approved.link") })).toHaveAttribute("href", "/ru/courses?view=teaching");
  await student.context().close();
  await admin.context().close();
});

test("no teacher link anywhere for a student; the old pages redirect", async ({ browser }) => {
  const page = await as(browser, data().no_links);
  const noTeacherLink = () => expect(page.locator('a[href*="for-teachers"], a[href*="teacher-access"], a[href*="become-teacher"]')).toHaveCount(0);
  await page.goto("/ru/courses");
  await expect(page.getByRole("heading", { name: t("home.dashboard") })).toBeVisible();
  await page.getByRole("button", { name: t("shell.account.menu", { name: data().no_links.name }) }).click();
  await expect(page.getByRole("link", { name: t("privacy.title") })).toBeVisible();
  await noTeacherLink();

  for (const [url, body] of [["/ru/grading-schemes", "teacherOnly.schemesBody"], ["/ru/courses/new", "teacherOnly.courseBody"]]) {
    await page.goto(url);
    await expect(page.getByRole("heading", { name: t("teacherOnly.title") })).toBeVisible();
    await expect(page.getByText(t(body))).toBeVisible();
    await expect(page.getByRole("link", { name: t("teacherOnly.back") })).toHaveAttribute("href", "/ru/courses");
    await noTeacherLink();
  }

  for (const old of ["/ru/teacher-access", "/ru/courses/become-teacher", "/en/teacher-access"]) {
    await page.goto(old);
    await expect(page).toHaveURL(new RegExp(`/${old.slice(1, 3)}/for-teachers/apply$`));
  }
  await page.context().close();
});

test("an invitation is accepted from /invitations; the banner links there and hides there", async ({ browser }) => {
  const d = data();
  const page = await as(browser, d.invitee, VIEWPORTS.phone);
  await page.goto("/ru/courses");
  await page.getByRole("link", { name: t("invitations.mine.view") }).click();
  await expect(page).toHaveURL(/\/ru\/invitations$/);
  await expect(page.getByRole("heading", { level: 1, name: t("invitations.mine.title") })).toBeVisible();
  await expect(page.getByRole("link", { name: t("invitations.mine.view") })).toHaveCount(0);
  await expect(page.getByText(t("invitations.mine.item.teacher", { org: d.school_name }))).toBeVisible();
  await expectNoSidewaysScroll(page);
  await page.getByRole("button", { name: t("invitations.mine.accept") }).click();
  await expect(page).not.toHaveURL(/\/ru\/invitations$/);

  await page.goto("/ru/invitations");
  await expect(page.getByText(t("invitations.mine.empty"))).toBeVisible();
  await expect(page.getByRole("link", { name: t("teacherOnly.back") })).toHaveAttribute("href", "/ru/courses");
  await page.context().close();
});

test("roster import from People, for this course and its students; only where it is allowed", async ({ browser }) => {
  const d = data();
  const page = await as(browser, d.independent);
  await page.goto(`/ru/courses/${d.independent_course_id}/people`);
  await page.getByRole("link", { name: t("rosterImport.title") }).click();
  await expect(page).toHaveURL(new RegExp(`/courses/${d.independent_course_id}/people/roster-import$`));
  await expect(page.getByRole("heading", { level: 1, name: t("rosterImport.title") })).toBeVisible();
  await expect(page.getByText(t("rosterImport.courseIntro", { course: "Мой курс E2E" }))).toBeVisible();
  await expect(page.locator("#roster-kind")).toHaveCount(0);
  await expect(page.locator("#roster-course")).toHaveCount(0);

  const csv = "email;display_name\nnew-signup-roster@example.com;Новый Ученик\n";
  await page.locator("#roster-file").setInputFiles({ name: "students.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: t("rosterImport.check") }).click();
  await expect(page.getByText(t("rosterImport.counts.valid", { n: 1 }))).toBeVisible();
  await page.getByRole("button", { name: t("rosterImport.preview.apply", { n: 1 }) }).click();
  await expect(page.getByText(t("rosterImport.counts.invited", { n: 1 }))).toBeVisible();
  const invitations = await api(d.independent, `/courses/${d.independent_course_id}/students/invitations?limit=50`);
  expect(invitations.items.filter((i: { state: string }) => i.state === "pending").length).toBe(1);
  await page.context().close();

  // a member teacher of a school is not its org admin; the ORT course never offers it, not even to the platform admin
  const school = seed().org_admin;
  const teacher = await as(browser, school.maths);
  await teacher.goto(`/ru/courses/${school.maths_course_id}/people`);
  await expect(teacher.getByRole("tab", { name: t("studentInvite.tabs.roster") })).toBeVisible();
  await expect(teacher.getByRole("link", { name: t("rosterImport.title") })).toHaveCount(0);
  await teacher.context().close();
  const admin = await as(browser, seed().admin);
  await admin.goto(`/ru/courses/${seed().course_id}/people`);
  await expect(admin.getByRole("tab", { name: t("studentInvite.tabs.roster") })).toBeVisible();
  await expect(admin.getByRole("link", { name: t("rosterImport.title") })).toHaveCount(0);
  await admin.context().close();
});

test("an independent teacher: no Organization tab, /org redirects, the personal templates are listed", async ({ browser }) => {
  const d = data();
  const page = await as(browser, d.independent);
  await page.goto("/ru/courses");
  await expect.poll(() => areas(page)).toEqual([t("shell.areas.teaching")]); // owner feedback 2026-11-08 (item 2)

  await page.goto(`/ru/org/${d.personal_org_id}`);
  await expect(page).toHaveURL(/\/ru\/courses\?view=teaching$/);
  await page.goto("/ru/org");
  await expect(page.getByText(t("organizations.org.pickEmpty"))).toBeVisible();

  await page.goto("/ru/exam-templates");
  const section = page.getByRole("region", { name: t("examTemplates.list.personalTitle") });
  const link = section.getByRole("link", { name: d.personal_template_name });
  await expect(link).toHaveAttribute("href", `/ru/exam-templates/${d.personal_template_id}`);
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/ru/exam-templates/${d.personal_template_id}$`));
  await expect(page.getByRole("heading", { level: 1 })).toContainText(d.personal_template_name);
  await page.context().close();

  // the platform admin still opens it
  const admin = await as(browser, seed().admin);
  await admin.goto(`/ru/org/${d.personal_org_id}`);
  await expect(admin).toHaveURL(new RegExp(`/ru/org/${d.personal_org_id}$`));
  await expect(admin.getByRole("navigation", { name: t("organizations.org.nav.label") }).first()).toBeVisible();
  await admin.context().close();
});

test("the course picker says My courses, not the person's name", async ({ browser }) => {
  const d = data();
  const page = await as(browser, d.both);
  await page.goto("/ru/courses/new");
  // the list loads after the page: wait for it (a slow CI machine got here first)
  await expect.poll(() => page.locator("#new-org option").allInnerTexts()).toContain(t("organizations.fields.personal"));
  const options = await page.locator("#new-org option").allInnerTexts();
  expect(options).toContain(d.school_name);
  expect(options).not.toContain(d.both.name);
  await page.context().close();
});

test("a revoked teacher reads the honest notice and may apply again", async ({ browser }) => {
  const page = await as(browser, data().revoked, VIEWPORTS.phone);
  const line = page.getByRole("status").filter({ hasText: t("home.teacherApplication.revoked") });
  await page.goto("/ru/courses?view=teaching");
  await expect(line).toBeVisible();
  await expect(line.getByRole("link", { name: t("home.teacherApplication.applyLink") })).toHaveAttribute("href", APPLY);
  await expectNoSidewaysScroll(page);
  await page.goto("/ru/courses?view=learning");
  await expect(line).toBeVisible();
  await line.getByRole("link", { name: t("home.teacherApplication.applyLink") }).click();
  await expect(page.getByRole("heading", { level: 2, name: t("teacherApply.form.title") })).toBeVisible();
  await expect(page.getByText(t("teacherApply.form.revoked"))).toBeVisible();
  await page.context().close();
});

test("the admin's revoke says how many students it freezes and asks for a reason", async ({ browser }) => {
  const d = data();
  const page = await as(browser, seed().admin);
  await page.goto(`/ru/admin/users/${d.revoke_target.profile.id}`);
  await page.getByRole("button", { name: t("platformAdmin.users.revokeTeacher") }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByText(t("platformAdmin.users.revokeImpact", { students: 1, courses: 1 }))).toBeVisible();
  await dialog.getByRole("button", { name: t("platformAdmin.requests.revoke") }).click();
  await expect(dialog.getByText(t("ui.reason.missing"))).toBeVisible();
  await dialog.getByRole("textbox").fill("Жалобы учеников");
  await dialog.getByRole("button", { name: t("platformAdmin.requests.revoke") }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: t("platformAdmin.users.grantTeacher") })).toBeVisible();
  await page.context().close();
});
