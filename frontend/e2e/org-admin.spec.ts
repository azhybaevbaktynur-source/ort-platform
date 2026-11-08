import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { E2E_DIR, seed, signIn, tr, uxShots, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Phase 9 S5 walk (PHASE_9_DESIGN 10 "Walkthrough", 11, 12): the school "Лицей 61 E2E" in a real browser.
 *
 *  1. Org admin: departments "Математика" and "Языки", the maths course moved into "Математика", settings (bank
 *     sharing on), the overview's "By department" roll-up.
 *  2. Shared banks: the maths teacher shares "Алгебра E2E" from the bank page; the org admin sees it under Shared
 *     banks, edits a question of it and has no delete; the languages teacher copies it from "From my organization";
 *     an independent teacher (personal organization) sees nothing.
 *  3. Roster import: students of the languages course (dry run, apply, same file again: nothing new) and teachers
 *     into the "Языки" department (an account → added).
 *  4. People → Invitations: the languages teacher invites two students, sends one again, revokes the other; the
 *     invited student accepts from the emailed link and is in the course.
 *  5. Student view on People: no tabs, and the new writes are refused (403 `test_student_forbidden`).
 *
 * Data: `seed_backend.py` (`seed_org_admin`). UX-gate screens go to `$E2E_DIR/phase9-s5/` (375 px and 1440 px; staff
 * screens ru + en, student screens ru + ky + en); they are not compared against baselines.
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/org-admin.spec.ts
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const data = () => seed().org_admin;
const SHOTS = "phase9-s5";
const STAFF: ("ru" | "en")[] = ["ru", "en"];
const STUDENT: ("ru" | "ky" | "en")[] = ["ru", "ky", "en"];

async function api(user: SeedUser, method: string, p: string, body?: unknown, ok: number[] = [200, 201, 204]) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(ok, `${method} ${p} -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

async function as(browser: Browser, user: SeedUser): Promise<Page> {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

/** The latest invitation link the console email provider printed for `email` (backend log of the e2e backend). */
function inviteLinkFor(email: string): string {
  const log = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8");
  const blocks = log.split("[EMAIL console] To: ").filter((b) => b.startsWith(`${email} `));
  expect(blocks.length, `no email to ${email}`).toBeGreaterThan(0);
  const m = blocks[blocks.length - 1].match(/https?:\/\/[^\s]+\/invite\/[A-Za-z0-9_\-]+/);
  expect(m, `no invitation link in the email to ${email}`).not.toBeNull();
  return new URL(m![0]).pathname;
}

const orgBase = () => `/ru/org/${data().organization_id}`;
const studentCsv = () => `email;display_name\n${data().roster_student.email};Ученик Из Списка\nnew-roster-student@example.com;Новый Ученик\nnot-an-email;Ошибка\n`;
const teacherCsv = () => `email;display_name;role\n${data().roster_teacher.email};Преподаватель Из Списка;teacher\nnew-roster-teacher@example.com;Новый Преподаватель;teacher\n`;

test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------- 1. departments, course move, settings, usage
test("org admin: departments, course move, settings, usage by department", async ({ browser }) => {
  const page = await as(browser, data().org_admin);
  await page.goto(`${orgBase()}/departments`);
  await expect(page.getByRole("heading", { name: t("departments.title") })).toBeVisible();
  await uxShots(page, SHOTS, "org-departments-empty", STAFF);
  await page.goto(`${orgBase()}/departments`);

  for (const name of ["Математика", "Языки"]) {
    await page.getByRole("button", { name: t("departments.create") }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(t("departments.name")).fill(name);
    if (name === "Языки") {
      await uxShots(page, SHOTS, "org-department-create-dialog", STAFF, async (p, lang) => {
        await p.getByRole("button", { name: tr(lang as "ru", "departments.create") }).first().click();
        await p.getByRole("dialog").getByLabel(tr(lang as "ru", "departments.name")).fill(name);
      });
    }
    await dialog.getByRole("button", { name: t("departments.submitCreate") }).click();
    await expect(page.getByText(t("departments.created")).first()).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await expect(page.getByText("Математика", { exact: true })).toBeVisible();
  await expect(page.getByText("Языки", { exact: true })).toBeVisible();
  await uxShots(page, SHOTS, "org-departments", STAFF);

  // the department menu: move dialog
  await page.goto(`${orgBase()}/departments`);
  const openMove = async (p: Page, lang: string) => {
    await p.getByRole("button", { name: tr(lang as "ru", "departments.actions", { name: "Языки" }) }).click();
    await p.getByRole("menuitem", { name: tr(lang as "ru", "departments.move") }).click();
    await expect(p.getByRole("dialog")).toBeVisible();
  };
  await openMove(page, "ru");
  await uxShots(page, SHOTS, "org-department-move-dialog", STAFF, openMove);
  await page.keyboard.press("Escape");

  // move the maths course into "Математика"
  const depts: { id: string; name: string }[] = await api(data().org_admin, "GET", `/org/${data().organization_id}/departments`);
  const maths = depts.find((d) => d.name === "Математика")!;
  await page.goto(`${orgBase()}/courses/${data().maths_course_id}`);
  await page.locator("summary", { hasText: t("departments.courseDepartment") }).click(); // a disclosure (UX rework E)
  await page.locator("#course-department").selectOption(maths.id);
  await page.getByRole("button", { name: t("departments.moveCourse") }).click();
  await expect(page.getByText(t("departments.courseMoved", { name: "Математика" })).first()).toBeVisible();
  const moved = await api(data().maths, "GET", `/courses/${data().maths_course_id}`);
  expect(moved.organization_id).toBe(maths.id);
  await uxShots(page, SHOTS, "org-course-department", STAFF);

  // settings: turn on bank sharing
  await page.goto(`${orgBase()}/settings`);
  await page.getByRole("switch", { name: t("orgSettings.bankSharing") }).click();
  await page.getByRole("button", { name: t("orgSettings.save") }).click();
  await expect(page.getByText(t("orgSettings.saved")).first()).toBeVisible();
  const settings = await api(data().org_admin, "GET", `/org/${data().organization_id}/settings`);
  expect(settings.settings.bank_sharing_enabled).toBe(true);
  await uxShots(page, SHOTS, "org-settings", STAFF);

  // overview: usage by department
  await page.goto(orgBase());
  const byDept = page.getByRole("table", { name: t("departments.usageTitle") });
  await expect(byDept.getByText("Математика")).toBeVisible();
  await uxShots(page, SHOTS, "org-overview-usage", STAFF);
  await page.context().close();
});

// ---------------------------------------------------------------- 2. shared banks
test("shared bank: teacher shares, org admin edits but cannot delete, another teacher copies, outsiders see nothing", async ({ browser }) => {
  const d = data();
  // the maths teacher shares the bank from its page ("More actions")
  const tp = await as(browser, d.maths);
  await tp.goto(`/ru/courses/${d.maths_course_id}/bank/${d.bank_id}`);
  await tp.getByRole("button", { name: t("sharedBanks.menu") }).click();
  await uxShots(tp, SHOTS, "course-bank-share-menu", STAFF, async (p, lang) => {
    await p.getByRole("button", { name: tr(lang as "ru", "sharedBanks.menu") }).click();
  });
  await tp.getByRole("menuitem", { name: new RegExp(t("sharedBanks.share")) }).click();
  await expect(tp.getByText(t("sharedBanks.sharedToast")).first()).toBeVisible();
  const reach = async (p: Page, lang: string) => { await p.getByRole("button", { name: tr(lang as "ru", "sharedBanks.menu") }).click(); };
  await uxShots(tp, SHOTS, "course-bank-unshare-menu", STAFF, reach);
  await tp.context().close();

  // the org admin: Shared banks list, opens the bank, edits a question, has no delete
  const ap = await as(browser, d.org_admin);
  await ap.goto(`${orgBase()}/shared-banks`);
  await expect(ap.getByText("Алгебра E2E")).toBeVisible();
  await uxShots(ap, SHOTS, "org-shared-banks", STAFF);
  await ap.getByRole("link", { name: t("sharedBanks.open") }).click();
  await expect(ap).toHaveURL(new RegExp(`/bank/${d.bank_id}`));
  await expect(ap.getByRole("button", { name: t("bank.questions.new") })).toBeVisible();
  await uxShots(ap, SHOTS, "org-admin-shared-bank", STAFF);
  // edit the first question in the bank editor (a new version of the shared question)
  await ap.getByRole("link", { name: /Сколько будет 2 \+ 2\?/ }).click();
  await ap.getByLabel(t("bank.editor.stem")).fill("Сколько будет 2 + 2? (исправлено)");
  await ap.getByRole("button", { name: t("lms.common.save"), exact: true }).click();
  await expect(ap.getByText(t("bank.editor.saved")).first()).toBeVisible();
  const qs = await api(d.maths, "GET", `/courses/${d.maths_course_id}/banks/${d.bank_id}/questions?limit=5`);
  expect(qs.items.some((q: { stem_excerpt?: string }) => (q.stem_excerpt ?? "").includes("исправлено"))).toBe(true);
  // the bank list: no delete for the org admin; the server refuses it too
  await ap.goto(`/ru/courses/${d.maths_course_id}/bank`);
  const card = ap.locator("li", { has: ap.getByRole("link", { name: "Алгебра E2E" }) });
  await expect(card).toBeVisible();
  await expect(card.getByRole("button", { name: t("bank.list.delete") })).toHaveCount(0);
  await api(d.org_admin, "DELETE", `/courses/${d.maths_course_id}/banks/${d.bank_id}`, undefined, [403, 404]);
  await ap.context().close();

  // the languages teacher copies it from "From my organization"
  const lp = await as(browser, d.languages);
  await lp.goto(`/ru/courses/${d.languages_course_id}/bank`);
  await expect(lp.getByRole("heading", { name: t("sharedBanks.pickerTitle") })).toBeVisible();
  await uxShots(lp, SHOTS, "course-bank-picker", STAFF);
  await lp.getByRole("button", { name: t("sharedBanks.copyLabel", { title: "Алгебра E2E" }) }).click();
  await expect(lp.getByText(t("sharedBanks.copied", { title: t("sharedBanks.copyTitle", { title: "Алгебра E2E" }) })).first()).toBeVisible();
  await expect(lp.getByRole("link", { name: t("sharedBanks.copyTitle", { title: "Алгебра E2E" }) })).toBeVisible();
  await uxShots(lp, SHOTS, "course-bank-copied", STAFF);
  await lp.context().close();

  // an independent teacher: the school's shared banks are a 404
  await api(d.independent, "GET", `/org/${d.organization_id}/shared-banks`, undefined, [404]);
});

// ---------------------------------------------------------------- 3. roster import
test("roster import: students (dry run, apply, same file again) and teachers into a department", async ({ browser }) => {
  const d = data();
  const page = await as(browser, d.org_admin);
  await page.goto(`${orgBase()}/roster-import`);
  await uxShots(page, SHOTS, "org-roster-upload", STAFF);

  const runStudents = async (p: Page = page, lang: string = L) => {
    await p.locator("#roster-kind").selectOption("student");
    await p.locator("#roster-course").selectOption(d.languages_course_id);
    await p.locator("#roster-file").setInputFiles({ name: "students.csv", mimeType: "text/csv", buffer: Buffer.from(studentCsv()) });
    await p.getByRole("button", { name: tr(lang as "ru", "rosterImport.check") }).click();
    await expect(p.getByRole("heading", { name: tr(lang as "ru", "rosterImport.preview.title", { name: "students.csv" }) })).toBeVisible();
  };
  await runStudents();
  await expect(page.getByText(t("rosterImport.counts.valid", { n: 2 }))).toBeVisible();
  await expect(page.getByText(t("rosterImport.counts.invalid", { n: 1 }))).toBeVisible();
  await uxShots(page, SHOTS, "org-roster-dryrun", STAFF, runStudents); // a dry run sends nothing
  await page.getByRole("button", { name: t("rosterImport.preview.apply", { n: 2 }) }).click();
  await expect(page.getByRole("heading", { name: t("rosterImport.result.title") })).toBeVisible();
  await expect(page.getByText(t("rosterImport.counts.invited", { n: 2 }))).toBeVisible();
  await uxShots(page, SHOTS, "org-roster-applied", ["ru"]);
  const invs = await api(d.languages, "GET", `/courses/${d.languages_course_id}/students/invitations?limit=50`);
  expect(invs.items.filter((i: { state: string }) => i.state === "pending").length).toBe(2);

  // the same file again: nothing new to send
  await page.getByRole("button", { name: t("rosterImport.result.again") }).click();
  await runStudents();
  await expect(page.getByText(t("rosterImport.counts.skipped", { n: 2 }))).toBeVisible();
  await expect(page.getByText(t("rosterImport.preview.nothing"))).toBeVisible();
  await expect(page.getByRole("button", { name: t("rosterImport.preview.apply", { n: 0 }) })).toBeDisabled();
  await uxShots(page, SHOTS, "org-roster-again", ["ru"]);
  const invs2 = await api(d.languages, "GET", `/courses/${d.languages_course_id}/students/invitations?limit=50`);
  expect(invs2.items.length).toBe(invs.items.length);

  // teachers into "Языки" (from the English page, so the result screen exists in en too): the one with an
  // account is added, the other invited
  const en = (key: string, vars: Record<string, string | number> = {}) => tr("en", key, vars);
  const depts: { id: string; name: string }[] = await api(d.org_admin, "GET", `/org/${d.organization_id}/departments`);
  const langs = depts.find((x) => x.name === "Языки")!;
  await page.goto(`/en/org/${d.organization_id}/roster-import`);
  await page.locator("#roster-kind").selectOption("teacher");
  await page.locator("#roster-dept").selectOption(langs.id);
  await page.locator("#roster-file").setInputFiles({ name: "teachers.csv", mimeType: "text/csv", buffer: Buffer.from(teacherCsv()) });
  await page.getByRole("button", { name: en("rosterImport.check") }).click();
  await expect(page.getByText(en("rosterImport.counts.valid", { n: 2 }))).toBeVisible();
  await uxShots(page, SHOTS, "org-roster-dryrun-teachers", ["en"]);
  await page.getByRole("button", { name: en("rosterImport.preview.apply", { n: 2 }) }).click();
  await expect(page.getByText(en("rosterImport.counts.added", { n: 1 }))).toBeVisible();
  await expect(page.getByText(en("rosterImport.counts.invited", { n: 1 }))).toBeVisible();
  await uxShots(page, SHOTS, "org-roster-applied-teachers", ["en"]);
  const members = await api(d.org_admin, "GET", `/org/${langs.id}/members?limit=50`);
  expect(members.items.some((m: { user: { email: string } }) => m.user.email === d.roster_teacher.email)).toBe(true);
  await page.context().close();
});

// ---------------------------------------------------------------- 4. People → Invitations, accept
test("teacher invites students, sends one again, revokes one; the student accepts", async ({ browser }) => {
  const d = data();
  const page = await as(browser, d.languages);
  await page.goto(`/ru/courses/${d.languages_course_id}/people`);
  await expect(page.getByRole("tab", { name: t("studentInvite.tabs.roster") })).toBeVisible();
  await uxShots(page, SHOTS, "course-people-roster", STAFF);

  const openInvite = async (p: Page, lang: string) => {
    await p.getByRole("button", { name: tr(lang as "ru", "studentInvite.invite") }).first().click();
    await expect(p.getByRole("dialog")).toBeVisible();
  };
  await openInvite(page, "ru");
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(t("studentInvite.dialog.emails")).fill(`${d.invite_student.email}\nrevoke-me@example.com`);
  await uxShots(page, SHOTS, "course-invite-dialog", STAFF, async (p, lang) => {
    await openInvite(p, lang);
    await p.getByRole("dialog").getByLabel(tr(lang as "ru", "studentInvite.dialog.emails")).fill(`${d.invite_student.email}\nrevoke-me@example.com`);
  });
  await dialog.getByRole("button", { name: t("studentInvite.dialog.sendN", { n: 2 }) }).click();
  await expect(dialog.getByText(t("studentInvite.result.invited", { n: 2 }))).toBeVisible();
  await uxShots(page, SHOTS, "course-invite-result", ["ru"]);
  await dialog.getByRole("button", { name: t("studentInvite.result.done") }).click();

  const toInvitations = async (p: Page, lang: string) => {
    await p.getByRole("tab", { name: tr(lang as "ru", "studentInvite.tabs.invitations") }).click();
    await expect(p.getByRole("table", { name: tr(lang as "ru", "studentInvite.list.title") })).toBeVisible();
  };
  await toInvitations(page, "ru");
  const row = (email: string) => page.getByRole("row", { name: new RegExp(email.replace(/[.+]/g, "\\$&")) });
  await row(d.invite_student.email).getByRole("button", { name: t("invitations.resend") }).click();
  await expect(page.getByText(t("invitations.resent", { email: d.invite_student.email })).first()).toBeVisible();
  await row("revoke-me@example.com").getByRole("button", { name: t("invitations.revoke") }).click();
  await page.locator("dialog[open]").getByRole("button", { name: t("invitations.revoke") }).click();
  await expect(page.getByText(t("invitations.revoked", { email: "revoke-me@example.com" })).first()).toBeVisible();
  await uxShots(page, SHOTS, "course-people-invitations", STAFF, toInvitations);
  await page.context().close();

  // the student accepts the (re-sent) link
  const link = inviteLinkFor(d.invite_student.email);
  // signed out: the invitation card with log in / sign up (UX-gate screens)
  const anon = await (await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC" })).newPage();
  await anon.goto(link.replace(/^\/(ru|ky|en)\//, "/ru/"));
  await expect(anon.getByRole("link", { name: tr("ru", "invitations.accept.login") })).toBeVisible();
  await uxShots(anon, SHOTS, "student-invite-accept", STUDENT);
  await anon.context().close();
  // signed in with the invited address: accepted at once, then the course
  const sp = await as(browser, d.invite_student);
  await sp.goto(link);
  await expect(sp).toHaveURL(new RegExp(`/courses/${d.languages_course_id}`));
  await uxShots(sp, SHOTS, "student-invite-joined", ["ru"]);
  const roster = await api(d.languages, "GET", `/courses/${d.languages_course_id}/people?role=student&limit=50`);
  expect(roster.items.some((r: { user: { email: string } }) => r.user.email === d.invite_student.email)).toBe(true);
  await sp.context().close();
});

// ---------------------------------------------------------------- platform admin: Departments tab, settings in Summary
test("platform admin: the organization's Departments tab and settings", async ({ browser }) => {
  const page = await as(browser, seed().admin);
  await page.goto(`/ru/admin/organizations/${data().organization_id}`);
  await uxShots(page, SHOTS, "admin-org-summary", STAFF);
  const toDepartments = async (p: Page, lang: string) => {
    await p.getByRole("tab", { name: tr(lang as "ru", "organizations.admin.tabs.departments") }).click();
    await expect(p.getByRole("tab", { name: tr(lang as "ru", "organizations.admin.tabs.departments") })).toHaveAttribute("aria-selected", "true");
  };
  await toDepartments(page, "ru");
  await expect(page.getByText("Математика", { exact: true })).toBeVisible();
  await uxShots(page, SHOTS, "admin-org-departments", STAFF, toDepartments);
  await page.context().close();
});

// ---------------------------------------------------------------- item 4 (ADMIN_ORGS_DESIGN §2.4-2.6, slices C + D)
/** UX check screens (ru, 375 / 1440 / 1920) only with UX_SCREENS_DIR set. */
const ITEM4_OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
async function item4Shots(page: Page, name: string) {
  if (!ITEM4_OUT) return;
  fs.mkdirSync(ITEM4_OUT, { recursive: true });
  const size = page.viewportSize() ?? VIEWPORTS.desktop;
  for (const width of [375, 1440, 1920]) {
    await page.setViewportSize({ width, height: width === 375 ? 812 : 1000 });
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(ITEM4_OUT, `${name}-ru-${width}.png`), fullPage: true });
  }
  await page.setViewportSize(size);
}

test("platform admin: opens a school as org admin, sees the strip, one audited action has the badge in Log", async ({ browser }) => {
  const d = data();
  const page = await as(browser, seed().admin);
  // Admin → Organizations: type badge and the subtree counts, the Type filter
  await page.goto("/ru/admin/organizations");
  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: "Лицей 61 E2E" }) });
  await expect(row).toBeVisible();
  await expect(row.getByText(t("organizations.kind.school"), { exact: true })).toBeVisible();
  await page.getByLabel(t("organizations.admin.kind")).selectOption("platform");
  await expect(page.getByRole("link", { name: "Лицей 61 E2E" })).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: t("organizations.kind.platform") }).first()).toBeVisible();
  await page.getByLabel(t("organizations.admin.kind")).selectOption("");
  await expect(page.getByRole("link", { name: "Лицей 61 E2E" })).toBeVisible();
  await item4Shots(page, "admin-orgs-list");

  // the platform organization is protected: a note, no Suspend in "⋯"
  const platformOrgs = await api(seed().admin, "GET", "/platform/organizations?kind=platform");
  await page.goto(`/ru/admin/organizations/${platformOrgs.items[0].id}`);
  await expect(page.getByText(t("organizations.admin.protectedNote"))).toBeVisible();
  await page.getByRole("button", { name: t("coursePage.moreActions") }).click();
  await expect(page.getByRole("menuitem", { name: t("organizations.admin.edit") })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: t("organizations.admin.suspend") })).toHaveCount(0);
  await page.keyboard.press("Escape");

  // the school: Students tab, the suspend dialog names the affected counts (cancelled), then "Open as org admin"
  await page.goto(`/ru/admin/organizations/${d.organization_id}`);
  await expect(page.getByRole("heading", { level: 1, name: "Лицей 61 E2E" })).toBeVisible();
  await item4Shots(page, "admin-org-detail");
  await page.getByRole("tab", { name: t("organizations.admin.tabs.students") }).click();
  await expect(page.getByText(t("organizations.admin.students.note"))).toBeVisible();
  await page.getByRole("button", { name: t("coursePage.moreActions") }).click();
  await page.getByRole("menuitem", { name: t("organizations.admin.suspend") }).click();
  const school = await api(seed().admin, "GET", `/platform/organizations/${d.organization_id}`);
  await expect(page.getByRole("alertdialog")).toContainText(t("organizations.admin.affected",
    { courses: school.courses, students: school.students, departments: school.departments }));
  await page.getByRole("alertdialog").getByRole("button", { name: t("ui.cancel") }).click();
  await page.getByRole("link", { name: t("organizations.admin.openAsOrgAdmin") }).click();
  await expect(page).toHaveURL(new RegExp(`/ru/org/${d.organization_id}$`));

  // the org area as platform admin: the strip, the label, no Shared banks, the header's active foreign choice
  const strip = page.getByTestId("acting-as-platform-admin");
  await expect(strip).toContainText(t("organizations.org.actingAsPlatformAdmin", { org: "Лицей 61 E2E" }));
  await expect(page.getByText(t("organizations.org.areaPlatformAdmin")).first()).toBeVisible();
  await expect(page.getByRole("link", { name: t("sharedBanks.nav") })).toHaveCount(0);
  await expect(page).toHaveTitle(new RegExp(t("organizations.org.titleSuffix")));
  await item4Shots(page, "org-as-platform-admin");
  const header = page.getByRole("navigation", { name: t("shell.areas.label") });
  await header.getByRole("button", { name: t("shell.areas.organization") }).click();
  const foreign = page.getByRole("link", { name: t("shell.areas.asPlatformAdmin", { name: "Лицей 61 E2E" }) });
  await expect(foreign).toBeVisible();
  await expect(foreign).toHaveAttribute("aria-current", /page|true/);
  await expect(page.getByRole("link", { name: t("shell.areas.allOrganizations") })).toHaveAttribute("href", "/ru/admin/organizations");
  await page.keyboard.press("Escape");

  // one audited action: a setting saved from the org area is recorded as the platform admin
  const before = await api(d.org_admin, "GET", `/org/${d.organization_id}/settings`);
  await page.goto(`${orgBase()}/settings`);
  await page.getByRole("switch", { name: t("orgSettings.teachersCanCreate") }).click();
  await page.getByRole("button", { name: t("orgSettings.save") }).click();
  await expect(page.getByText(t("orgSettings.saved")).first()).toBeVisible();
  const logged = await api(seed().admin, "GET",
    `/platform/audit-log?acting_as=platform_admin&target_type=organization&target_id=${d.organization_id}&action=organization.settings_update`);
  expect(logged.items.length).toBeGreaterThan(0);
  expect(logged.items[0].details.acting_as).toBe("platform_admin");

  // the badge in the organization's Log tab
  await page.getByRole("link", { name: t("organizations.org.actingAsPlatformAdminBack") }).click();
  await expect(page).toHaveURL(new RegExp(`/ru/admin/organizations/${d.organization_id}$`));
  await page.getByRole("tab", { name: t("organizations.admin.tabs.log") }).click();
  await expect(page.getByRole("table").getByText(t("platformAdmin.audit.actingAs")).first()).toBeVisible();
  // the header no longer shows the foreign organization once the org area is left
  await page.getByRole("navigation", { name: t("shell.areas.label") }).getByRole("button", { name: t("shell.areas.organization") }).click();
  await expect(page.getByRole("link", { name: t("shell.areas.asPlatformAdmin", { name: "Лицей 61 E2E" }) })).toHaveCount(0);
  await page.context().close();
  await api(d.org_admin, "PATCH", `/org/${d.organization_id}/settings`, { teachers_can_create_courses: before.settings.teachers_can_create_courses });
});

// ---------------------------------------------------------------- ORT course (design 9): read-only checks
test("ORT course: People tabs, no form modes, no share entry on the bank", async ({ browser }) => {
  const cid = seed().course_id;
  const page = await as(browser, seed().admin);
  await page.goto(`/ru/courses/${cid}/people`);
  await expect(page.getByRole("tab", { name: t("studentInvite.tabs.roster") })).toBeVisible();
  await expect(page.getByRole("tab", { name: t("studentInvite.tabs.invitations") })).toBeVisible();
  await expect(page.getByRole("tab", { name: t("studentInvite.tabs.applications") })).toHaveCount(0);
  await uxShots(page, SHOTS, "ort-people-tabs", ["ru"]);
  await page.goto(`/ru/courses/${cid}/settings?section=enrollment`); // FB8-5 S3: the Enrollment section
  // form modes are listed but cannot be chosen (with the template lock note); the server refuses them too
  await expect(page.getByText(t("enrollmentForm.settings.ortNote"))).toBeVisible(); // the settings form is loaded
  const formModes = await page.locator("#s-mode option").evaluateAll((os) => (os as HTMLOptionElement[])
    .filter((o) => o.value.startsWith("form_")).map((o) => o.disabled));
  expect(formModes).toEqual([true, true]);
  await expect(page.getByText(t("enrollmentForm.settings.ortNote"))).toBeVisible();
  await api(seed().admin, "PATCH", `/courses/${cid}`, { enrollment_mode: "form_review" }, [409, 422]);
  await page.goto(`/ru/courses/${cid}/bank/${seed().bank_id}`);
  await expect(page.getByRole("button", { name: t("bank.questions.new") })).toBeVisible();
  await expect(page.locator("button[aria-haspopup]", { hasText: t("sharedBanks.menu") })).toHaveCount(0); // (the pager is also «Ещё»)
  await page.goto(`/ru/courses/${cid}/bank`);
  await expect(page.getByRole("heading", { name: t("sharedBanks.pickerTitle") })).toHaveCount(0);
  await page.context().close();
});

// ---------------------------------------------------------------- 5. Student view
test("Student view on People: no tabs, the new writes are refused", async ({ browser }) => {
  const d = data();
  const cid = d.languages_course_id;
  const page = await as(browser, d.languages);
  await page.goto(`/ru/courses/${cid}/people`);
  await page.getByRole("button", { name: t("studentView.button") }).click();
  await expect(page.getByRole("status").filter({ hasText: t("studentView.banner") })).toBeVisible();
  await expect(page.getByRole("tab", { name: t("studentInvite.tabs.invitations") })).toHaveCount(0);
  await expect(page.getByRole("button", { name: t("studentInvite.invite") })).toHaveCount(0);
  const session = await page.evaluate(() => JSON.parse(window.sessionStorage.getItem("studentView") || "{}"));
  await page.context().close();

  const headers = { Authorization: `Bearer ${session.token}`, "Content-Type": "application/json" };
  const writes: [string, string, unknown][] = [
    ["POST", `/courses/${cid}/students/invitations`, { emails: ["sv@example.com"] }],
    ["POST", `/courses/${cid}/banks/copy-from`, { bank_id: d.bank_id }],
    ["POST", `/courses/${cid}/enrollment-forms`, { fields: [] }],
  ];
  for (const [method, p, body] of writes) {
    const r = await fetch(`${seed().api}/api/v1${p}`, { method, headers, body: JSON.stringify(body) });
    expect(r.status, `${method} ${p}`).toBe(403);
    expect((await r.json()).error.code, `${method} ${p}`).toBe("test_student_forbidden");
  }
});

// Phase 11 S3: `/auth/register` requires the age band; the invitation's sign-up keeps the address and its way back
test("invited with no account: sign-up asks the age first, keeps the address, then accepts", async ({ browser }) => {
  const d = data();
  const email = "invited-new@example.com";
  await api(d.languages, "POST", `/courses/${d.languages_course_id}/students/invitations`, { emails: [email], language: "ru" });
  const page = await (await browser.newContext({ viewport: VIEWPORTS.phone, locale: "ru-RU", timezoneId: "UTC" })).newPage();
  // the emailed link carries `?email=`; `inviteLinkFor` keeps only its path
  await page.goto(`${inviteLinkFor(email).replace(/^\/(ru|ky|en)\//, "/ru/")}?email=${encodeURIComponent(email)}`);
  await page.getByRole("link", { name: tr("ru", "invitations.accept.register") }).click();
  await page.getByRole("button", { name: tr("ru", "privacy.age.14_17") }).click();
  await expect(page.getByLabel(tr("ru", "auth.email"))).toHaveValue(email);
  await page.getByLabel(tr("ru", "auth.displayName")).fill("Новый Приглашённый");
  await page.getByLabel(tr("ru", "auth.phone")).fill("+996700000001");
  const password = `e2e-${Math.random().toString(36).slice(2)}-pass`;
  await page.getByLabel(tr("ru", "auth.password")).fill(password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: tr("ru", "auth.signUpButton") }).click();
  await expect(page.getByRole("heading", { name: tr("ru", "auth.verify.title") })).toBeVisible();
  const blocks = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8").split("[EMAIL console] To: ").filter((b) => b.startsWith(`${email} `));
  const code = blocks[blocks.length - 1].match(/\b(\d{6})\b/);
  expect(code, `no code in the last email to ${email}`).not.toBeNull();
  await page.getByLabel(tr("ru", "auth.verify.codeLabel")).fill(code![1]);
  await page.getByRole("button", { name: tr("ru", "auth.verify.button") }).click();
  await expect(page).toHaveURL(new RegExp(`/courses/${d.languages_course_id}`));
  await page.context().close();
});
