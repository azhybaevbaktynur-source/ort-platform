// Step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2, owner D4 and D9): Admin → Преподаватели. One list of the people who
// teach (independent, school, both) with search and filters; the teacher requests as the second tab; the organizations
// list without independent teachers' own spaces; such a space's old detail address opens the person page, whose
// «Преподавание» card says «Независимый преподаватель с …». With S3_SHOTS_DIR set it writes ru screenshots at 375 /
// 1440 / 1920 (docs/phases/CATALOG_screens/s3/).
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, expectNoRawKeys, seed, settle, signIn, tr, VIEWPORTS } from "./helpers";

const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const SHOTS = process.env.S3_SHOTS_DIR || "";
const SIZES = [
  { name: "375", width: 375, height: 812 },
  { name: "1440", width: 1440, height: 900 },
  { name: "1920", width: 1920, height: 1080 },
];

async function shots(page: Page, name: string): Promise<void> {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await settle(page, false);
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${size.name}.png`), fullPage: true });
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

const rowOf = (page: Page, email: string) => page.getByRole("row").filter({ hasText: email });

test("Admin → Преподаватели: independent, school and both; search, filters, the person page link", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  await signIn(page, s.admin);
  await page.goto("/ru/admin");
  // the admin nav: «Преподаватели» replaces «Заявки преподавателей» (with the pending count)
  const nav = page.getByRole("link", { name: new RegExp(`^${t("platformAdmin.nav.teachers")}`) }).first();
  await expect(nav).toHaveAttribute("href", "/ru/admin/teachers");
  await nav.click();
  await expect(page.getByRole("heading", { level: 1, name: t("platformAdmin.teachers.title") })).toBeVisible();
  await expect(page.getByRole("tab", { name: t("platformAdmin.teachers.tabs.teachers") })).toHaveAttribute("aria-selected", "true");
  await expectNoRawKeys(page);
  await shots(page, "01-teachers");

  const search = page.locator("main").getByRole("searchbox");
  const independent = s.course_nav.teacher; // approved, own course, no school
  const both = s.org_admin.maths; // approved and a teacher of «Лицей 61 E2E»
  const school = s.org_admin.org_admin; // org admin of the school only

  await search.fill(independent.email);
  const r1 = rowOf(page, independent.email);
  await expect(r1).toHaveCount(1);
  await expect(r1.getByText(t("platformAdmin.teachers.independent"), { exact: true })).toBeVisible();
  await expect(r1.getByText(t("platformAdmin.teacherStatus.approved"))).toBeVisible();
  await expect(r1.getByRole("link", { name: independent.name })).toHaveAttribute("href", `/ru/admin/users/${independent.profile.id}`);

  await search.fill(both.email);
  await expect(rowOf(page, both.email).getByText(`${t("platformAdmin.teachers.independentShort")} · Лицей 61 E2E`)).toBeVisible();
  await search.fill(school.email);
  await expect(rowOf(page, school.email).getByText("Лицей 61 E2E", { exact: true })).toBeVisible();

  // filters: independent hides the school people; revoked shows the revoked teacher only
  await search.fill("");
  await page.getByLabel(t("platformAdmin.teachers.filters.kind")).selectOption("independent");
  await expect(rowOf(page, independent.email)).toHaveCount(1);
  await expect(rowOf(page, school.email)).toHaveCount(0);
  await expect(rowOf(page, both.email)).toHaveCount(0);
  await page.getByLabel(t("platformAdmin.teachers.filters.kind")).selectOption("");
  await page.getByLabel(t("platformAdmin.teachers.filters.status")).selectOption("revoked");
  await expect(rowOf(page, s.teacher_signup.revoked.email)).toHaveCount(1);
  await expect(rowOf(page, independent.email)).toHaveCount(0);
  await page.getByRole("button", { name: t("ui.resetFilters") }).click();

  // the word «организация» never names an independent teacher here
  await search.fill(independent.email);
  await expect(rowOf(page, independent.email)).toHaveCount(1);
  expect(await page.getByRole("tabpanel").innerText()).not.toMatch(/организац/i); // the admin nav names Организации
});

test("the requests tab: the queue moved here, the URL keeps the tab", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  await signIn(page, s.admin);
  await page.goto("/ru/admin/teachers");
  await page.getByRole("tab", { name: new RegExp(t("platformAdmin.teachers.tabs.requests")) }).click();
  await expect(page).toHaveURL(/\/ru\/admin\/teachers\?tab=requests$/);
  const pending = s.teacher_signup.pending;
  await expect(rowOf(page, pending.email).getByRole("button", { name: pending.name })).toBeVisible();
  await expect(rowOf(page, pending.email).getByRole("button", { name: t("platformAdmin.requests.approve") })).toBeVisible();
  await expectNoRawKeys(page);
  await shots(page, "02-requests");
  await page.getByLabel(t("platformAdmin.requests.filter")).selectOption("rejected");
  await expect(page).toHaveURL(/\/ru\/admin\/teachers\?tab=requests&status=rejected$/);
  await expect(rowOf(page, s.teacher_signup.rejected.email)).toHaveCount(1);
  await expect(rowOf(page, pending.email)).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel(t("platformAdmin.requests.filter"))).toHaveValue("rejected");
});

test("organizations without personal rows; a personal space opens the person page with «Преподавание»", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const s = seed();
  const d = s.teacher_signup;
  await signIn(page, s.admin);
  await page.goto("/ru/admin/organizations");
  await expect(page.getByRole("link", { name: "Лицей 61 E2E" })).toBeVisible();
  const kinds = await page.getByLabel(t("organizations.admin.kind")).locator("option").allTextContents();
  expect(kinds).not.toContain(t("organizations.kind.personal"));
  // no personal row on any page of the list (the API refuses `kind=personal`)
  let cursor: string | null = null;
  do {
    const body: { items: { kind: string }[]; next_cursor: string | null } = await api(s.admin, "GET", `/platform/organizations?limit=100${cursor ? `&cursor=${cursor}` : ""}`);
    expect(body.items.map((o) => o.kind)).not.toContain("personal");
    cursor = body.next_cursor;
  } while (cursor);
  await api(s.admin, "GET", "/platform/organizations?kind=personal", undefined, [422]);
  await expect(page.locator(`main a[href="/ru/admin/organizations/${d.personal_org_id}"]`)).toHaveCount(0);
  await shots(page, "03-organizations");

  // the personal space's detail address (old links, the audit log) → the teacher's person page
  await page.goto(`/ru/admin/organizations/${d.personal_org_id}`);
  await expect(page).toHaveURL(new RegExp(`/ru/admin/users/${d.independent.profile.id}$`));
  const card = page.getByTestId("teaching-card");
  await expect(card.getByText(new RegExp(`^${t("person.teaching.independentSince", { date: "" }).trim()}`))).toBeVisible();
  await expect(card.getByRole("link", { name: t("person.teaching.openCourses") })).toHaveAttribute("href", `/ru/admin/courses?owner_id=${d.independent.profile.id}`);
  // the organizations section has no personal row
  await expect(page.getByRole("link", { name: d.independent.name, exact: true })).toHaveCount(0);
  await expectNoRawKeys(page);
  await shots(page, "04-person-teaching");

  // Admin → Курсы with ?owner_id= lists that teacher's course only
  await card.getByRole("link", { name: t("person.teaching.openCourses") }).click();
  await expect(page.getByRole("link", { name: "Мой курс E2E" })).toBeVisible();
  await expect(page.getByText(t("platformAdmin.courses.ownerFilter"))).toBeVisible();

  // a school teacher's card names the school
  await page.goto(`/ru/admin/users/${s.org_admin.org_admin.profile.id}`);
  const schoolCard = page.getByTestId("teaching-card");
  await expect(schoolCard.getByText("Лицей 61 E2E", { exact: true })).toBeVisible();
  // a student has no card
  await page.goto(`/ru/admin/users/${s.access!.student.profile.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: t("person.teaching.title"), exact: true })).toHaveCount(0);
});
