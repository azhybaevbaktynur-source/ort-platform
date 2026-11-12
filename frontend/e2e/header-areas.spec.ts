import { expect, test, type Page } from "@playwright/test";
import { seed, signIn, tr, VIEWPORTS } from "./helpers";

/**
 * UX rework 2 (item 7): the top menu comes from the account, once, so it is the same on every page and never loses an
 * area while a page loads. The API is slowed down on purpose: on production it answers from far away.
 */
const t = (key: string) => tr("ru", key);

const headerAreas = (page: Page) => page.getByRole("navigation", { name: t("shell.areas.label") });
/** Student UI U2: in the Learning area the student sidebar replaces the header; it lists the other areas. */
const otherAreas = (page: Page) => page.getByRole("navigation", { name: t("student.nav.otherAreas") });

/** Area labels as drawn on the desktop header, or (Learning, student sidebar) Learning plus the sidebar's other areas. */
async function areas(page: Page): Promise<string[]> {
  // item 4: an area with choices (the platform admin's organization switcher) is a button, not a link
  if (await headerAreas(page).count()) return headerAreas(page).locator(":scope > ul > li").locator(":scope > a, :scope > div > button").allInnerTexts();
  if (await otherAreas(page).count()) return [t("shell.areas.learning"), ...await otherAreas(page).getByRole("link").allInnerTexts()];
  return [];
}

/** The link to an area: on the header, or on the student sidebar's "other areas". */
const areaLink = (page: Page, key: string) => headerAreas(page).getByRole("link", { name: t(key) })
  .or(otherAreas(page).getByRole("link", { name: t(key) }));

/** Opens an area: its link, or (a switcher, item 4) the dropdown's first choice. */
async function goToArea(page: Page, key: string) {
  const switcher = headerAreas(page).getByRole("button", { name: t(key), exact: true });
  if (await switcher.count()) {
    await switcher.click();
    await switcher.locator("xpath=..").getByRole("link").first().click();
    return;
  }
  await areaLink(page, key).click();
}

test("the same menu on every page, also while the API is slow", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const data = seed();
  const orgId = data.org_admin.organization_id;
  await signIn(page, data.admin);
  await page.goto("/ru/courses");
  // owner feedback 2026-11-08 (item 2): the admin teaches but learns nowhere, so there is no Learning area
  const full = [t("shell.areas.teaching"), t("shell.areas.organization"), t("shell.areas.platform")];
  await expect.poll(() => areas(page)).toEqual(full);

  for (const path of ["/ru/admin", `/ru/org/${orgId}`, "/ru/grading-schemes", `/ru/courses/${data.course_id}`, "/ru/admin/users"]) {
    await page.goto(path);
    await expect.poll(() => areas(page), { message: path }).toEqual(full);
  }

  // moving between areas with every API answer 2 s late: at no moment is an area missing
  await page.route("**/api/v1/**", async (route) => {
    await new Promise((done) => setTimeout(done, 2000));
    await route.continue();
  });
  for (const area of ["shell.areas.platform", "shell.areas.organization", "shell.areas.teaching", "shell.areas.platform"]) {
    await goToArea(page, area);
    for (const wait of [50, 300, 700]) {
      await page.waitForTimeout(wait);
      expect(await areas(page), `${area} after ${wait} ms`).toEqual(full);
    }
    await expect(page.getByTestId("areas-loading")).toHaveCount(0);
  }
});

test("a first visit shows placeholders, never a partial menu", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  // the shell's account answer: `/me/bootstrap` since PERFORMANCE_AUDIT S2 (`/me/lms` kept for other readers)
  await page.route(/\/api\/v1\/me\/(lms|bootstrap)(\?|$)/, async (route) => {
    await new Promise((done) => setTimeout(done, 1500));
    await route.continue();
  });
  await page.goto("/ru/admin");
  await expect(page.getByTestId("areas-loading").first()).toBeVisible();
  expect(await page.getByRole("navigation", { name: t("shell.areas.label") }).count()).toBe(0);
  await expect.poll(() => areas(page)).toHaveLength(3);
});

test("a student's menu has no extra areas on any page", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const data = seed();
  await signIn(page, data.modules.student);
  await page.goto("/ru/home"); // step 3a S3: the hub
  await expect(page.getByRole("heading", { level: 2, name: t("home.hub.coursesTitle") })).toBeVisible();
  await expect(headerAreas(page)).toHaveCount(0);
  await expect(otherAreas(page)).toHaveCount(0);
  await page.goto("/ru/parent"); // a page of another area must not add a tab
  await expect(headerAreas(page)).toHaveCount(0);
  await expect(otherAreas(page)).toHaveCount(0);
});

test("an independent teacher has no Organization area", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().teacher_signup.independent);
  await page.goto("/ru/courses");
  await expect.poll(() => areas(page)).toEqual([t("shell.areas.teaching")]); // owner feedback 2026-11-08 (item 2)
});

test("a teacher who learns nowhere: no Learning tab, no Join with code; ?view=learning and /home open Teaching", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().teacher_signup.independent);
  await page.goto("/ru/home"); // step 3a S3: the hub is never a teacher's page
  await expect(page).toHaveURL(/\/ru\/courses$/);
  await page.goto("/ru/courses?view=learning");
  await expect(page).toHaveURL(/\/ru\/courses$/); // step 3a S3: ?view= is gone, the old link lands on the list
  await expect.poll(() => areas(page)).toEqual([t("shell.areas.teaching")]);
  await expect(page.getByRole("tablist")).toHaveCount(0);
  await expect(page.locator('a[href="/ru/courses/join"]')).toHaveCount(0);
  // the Teaching sub-menu stays although Teaching is the only area
  await expect(page.getByRole("link", { name: t("examTemplates.nav.title") }).first()).toBeVisible();
});

/**
 * Fix round 2026-11-12 1e (owner decision): student and teacher are separate accounts. A teacher who still has a student
 * enrolment gets exactly the teacher-only design and checks courses through Student view.
 */
const approvedLine = (page: Page) => page.getByRole("status").filter({ hasText: t("home.teacherApplication.approved") });
const studentViewBanner = (page: Page) => page.getByRole("status").filter({ hasText: t("studentView.banner") });

test("a teacher with a student enrolment: the teacher-only design; Student view only on the course page", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const teacher = seed().teacher_enrolled;
  await signIn(page, teacher);
  await page.goto("/ru/courses?view=learning"); // the old Learning link lands on Teaching
  await expect(page).toHaveURL(/\/ru\/courses$/); // step 3a S3: without ?view=
  await expect(page.getByRole("heading", { level: 1, name: t("courses.list.title") })).toBeVisible();
  await expect.poll(() => areas(page)).toEqual([t("shell.areas.teaching")]);
  await expect(areaLink(page, "shell.areas.learning")).toHaveCount(0); // no "Учёба"
  await expect(page.getByRole("tablist")).toHaveCount(0); // no "Преподаю / Учусь"
  await expect(page.locator('a[href="/ru/courses/join"]')).toHaveCount(0); // no "Войти по коду"
  await expect(approvedLine(page)).toHaveCount(1); // the application line is on the Teaching list

  // owner 2026-11-12: no Student view on the course cards; the whole card opens the course's management view
  const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: teacher.course_title }) });
  await expect(card.getByRole("button", { name: t("studentView.button") })).toHaveCount(0);
  await card.getByRole("link").first().click();
  await expect(page).toHaveURL(new RegExp(`/ru/courses/${teacher.course_id}$`));
  await expect(studentViewBanner(page)).toHaveCount(0);

  // Student view from the staff course page header only
  const fromPage = page.getByRole("button", { name: t("studentView.button") });
  await expect(fromPage).toBeVisible();
  await fromPage.click();
  await expect(studentViewBanner(page)).toBeVisible();
  await studentViewBanner(page).getByRole("button", { name: t("studentView.leave") }).click();
  await expect(studentViewBanner(page)).toHaveCount(0);
});

test("a newly approved teacher who learns nowhere: no Learning area, the approved line on the Teaching list", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().teacher_notice); // teacher-approved-notice.spec.ts (later) closes it
  await page.goto("/ru/courses");
  await expect(page.getByRole("heading", { level: 1, name: t("courses.list.title") })).toBeVisible();
  await expect.poll(() => areas(page)).toEqual([t("shell.areas.teaching")]);
  await expect(areaLink(page, "shell.areas.learning")).toHaveCount(0);
  await expect(approvedLine(page)).toHaveCount(1);
});

test("admin overview: numbers, then a retry when the summary fails", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  await page.goto("/ru/admin");
  const pending = page.getByRole("link", { name: new RegExp(t("platformAdmin.overview.pendingRequests")) });
  await expect(pending).toContainText(/\d+/);
  // FB8-5 S4: storage shows in "Needs attention" only when it is not ok; the metrics row has the user count
  await expect(page.getByRole("link", { name: new RegExp(`${t("platformAdmin.overview.metrics.users")}\\s*\\d+`) })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("—");

  await page.route("**/api/v1/platform/summary", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"error":{"code":"server_busy","message":"busy"}}' }));
  await page.reload();
  await expect(page.getByRole("button", { name: t("ui.retry") })).toBeVisible();
  await page.unroute("**/api/v1/platform/summary");
  await page.getByRole("button", { name: t("ui.retry") }).click();
  await expect(pending).toContainText(/\d+/);
});
