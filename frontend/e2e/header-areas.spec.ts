import { expect, test, type Page } from "@playwright/test";
import { seed, signIn, tr, VIEWPORTS } from "./helpers";

/**
 * UX rework 2 (item 7): the top menu comes from the account, once, so it is the same on every page and never loses an
 * area while a page loads. The API is slowed down on purpose: on production it answers from far away.
 */
const t = (key: string) => tr("ru", key);

/** Area labels as drawn on the desktop header. */
const areas = (page: Page) => page.getByRole("navigation", { name: t("shell.areas.label") }).getByRole("link").allInnerTexts();

test("the same menu on every page, also while the API is slow", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const data = seed();
  const orgId = data.org_admin.organization_id;
  await signIn(page, data.admin);
  await page.goto("/ru/courses");
  const full = [t("shell.areas.learning"), t("shell.areas.teaching"), t("shell.areas.organization"), t("shell.areas.platform")];
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
  for (const area of ["shell.areas.platform", "shell.areas.organization", "shell.areas.learning", "shell.areas.platform"]) {
    await page.getByRole("navigation", { name: t("shell.areas.label") }).getByRole("link", { name: t(area) }).click();
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
  await expect.poll(() => areas(page)).toHaveLength(4);
});

test("a student's menu has no extra areas on any page", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  const data = seed();
  await signIn(page, data.modules.student);
  await page.goto("/ru/courses");
  await expect(page.getByRole("heading", { name: t("home.dashboard") })).toBeVisible();
  await expect(page.getByRole("navigation", { name: t("shell.areas.label") })).toHaveCount(0);
  await page.goto("/ru/parent"); // a page of another area must not add a tab
  await expect(page.getByRole("navigation", { name: t("shell.areas.label") })).toHaveCount(0);
});

test("admin overview: numbers, then a retry when the summary fails", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  await page.goto("/ru/admin");
  const pending = page.getByRole("link", { name: new RegExp(t("platformAdmin.overview.pendingRequests")) });
  await expect(pending).toContainText(/\d+/);
  await expect(page.getByRole("link", { name: new RegExp(`${t("storage.nav")}.*${t("storage.level.ok")}`) })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("—");

  await page.route("**/api/v1/platform/summary", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"error":{"code":"server_busy","message":"busy"}}' }));
  await page.reload();
  await expect(page.getByRole("button", { name: t("ui.retry") })).toBeVisible();
  await page.unroute("**/api/v1/platform/summary");
  await page.getByRole("button", { name: t("ui.retry") }).click();
  await expect(pending).toContainText(/\d+/);
});
