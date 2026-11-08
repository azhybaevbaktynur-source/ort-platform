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
  await page.route("**/api/v1/me/lms", async (route) => {
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
  await page.goto("/ru/courses");
  await expect(page.getByRole("heading", { name: t("home.dashboard") })).toBeVisible();
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

test("a teacher who learns nowhere: no Learning tab, no Join with code; ?view=learning opens Teaching", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().teacher_signup.independent);
  await page.goto("/ru/courses?view=learning");
  await expect(page).toHaveURL(/\/ru\/courses\?view=teaching$/);
  await expect.poll(() => areas(page)).toEqual([t("shell.areas.teaching")]);
  await expect(page.getByRole("tab", { name: t("courses.list.learning") })).toHaveCount(0);
  await expect(page.getByRole("link", { name: t("courses.list.join") })).toHaveCount(0);
  // the Teaching sub-menu stays although Teaching is the only area
  await expect(page.getByRole("link", { name: t("examTemplates.nav.title") }).first()).toBeVisible();
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
