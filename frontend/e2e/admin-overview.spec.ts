// FB8-5 S4 (STAFF_UX_AUDIT §6): the admin overview: metrics row, "Needs attention", quick actions, the health line
// collapsed (full card on /admin/health). With S4_SHOTS_DIR set it also writes ru screenshots at 375 / 1440 / 1920.
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { expectNoRawKeys, seed, settle, signIn, tr, VIEWPORTS } from "./helpers";

const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const SHOTS = process.env.S4_SHOTS_DIR || "";
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

test("admin overview: metrics, attention, health line and the health page", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  await page.goto("/ru/admin");
  await expect(page.getByRole("heading", { level: 1, name: t("platformAdmin.overview.title") })).toBeVisible();

  const metrics = page.getByTestId("overview-metrics");
  for (const key of ["users", "activeStudents", "pro", "tests"]) {
    await expect(metrics.getByText(t(`platformAdmin.overview.metrics.${key}`))).toBeVisible();
  }
  await expect(metrics.getByRole("link", { name: new RegExp(`${t("platformAdmin.overview.metrics.users")}\\s*\\d+`) })).toBeVisible();

  // the seed leaves a pending teacher request (teacher_signup.pending)
  const attention = page.getByTestId("needs-attention");
  const requests = attention.getByRole("link", { name: new RegExp(t("platformAdmin.overview.pendingRequests")) });
  await expect(requests).toBeVisible();
  await expect(requests).toHaveAttribute("href", "/ru/admin/teacher-requests");

  for (const key of ["newCourse", "grantPro", "codes"]) {
    await expect(page.getByRole("link", { name: t(`platformAdmin.overview.quick.${key}`) })).toBeVisible();
  }

  // health collapsed to a line; the full card lives on its own page
  const line = page.getByTestId("health-line");
  // the scratch server's real answer (its email/migration checks may fail there): either status, never the skeleton
  const status = t("adminHealth.line.problems", { count: 0 }).replace(/0.*$/, "");
  await expect(line).toContainText(new RegExp(`${t("adminHealth.line.ok")}|${status}\\d`));
  await expect(page.getByTestId("health-checks")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: t("access.admin.recent.title") })).toBeVisible();
  await expectNoRawKeys(page); // S4: the staff dictionary has arrived
  await shots(page, "01-overview");

  await line.getByRole("link", { name: t("adminHealth.line.details") }).click();
  await page.waitForURL(/\/ru\/admin\/health$/);
  await expect(page.getByRole("heading", { level: 1, name: t("adminHealth.page.title") })).toBeVisible();
  await expect(page.getByTestId("health-checks")).toBeVisible();
  await shots(page, "03-health-page");
});

test("admin overview: reveal alert and failing checks appear in Needs attention", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  await page.route("**/api/v1/platform/overview", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, reveals_last_hour: 25, reveal_alert: true } });
  });
  await page.route("**/api/v1/platform/health", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, ok: false, email: { ...body.email, ok: false } } });
  });
  await page.goto("/ru/admin");
  const attention = page.getByTestId("needs-attention");
  const reveals = attention.getByRole("link", { name: new RegExp(`${t("platformAdmin.overview.attention.reveals")}\\s*25`) });
  await expect(reveals).toHaveAttribute("href", "/ru/admin/access/vouchers");
  const health = attention.getByRole("link", { name: new RegExp(`${t("platformAdmin.overview.attention.health")}\\s*1`) });
  await expect(health).toHaveAttribute("href", "/ru/admin/health");
  await expect(page.getByTestId("health-line")).toContainText(t("adminHealth.line.problems", { count: 1 }));
  await shots(page, "02-overview-attention");

  // the overview's numbers fail: an inline retry instead of the row, the rest of the page stays
  await page.unroute("**/api/v1/platform/overview");
  await page.route("**/api/v1/platform/overview", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"error":{"code":"server_busy","message":"busy"}}' }));
  await page.reload();
  await expect(page.getByRole("button", { name: t("ui.retry") })).toBeVisible();
  await expect(page.getByTestId("needs-attention")).toBeVisible();
  await page.unroute("**/api/v1/platform/overview");
  await page.getByRole("button", { name: t("ui.retry") }).click();
  await expect(page.getByTestId("overview-metrics")).toBeVisible();
});
