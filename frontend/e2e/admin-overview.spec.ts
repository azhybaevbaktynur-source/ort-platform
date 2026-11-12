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
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

// FIX_ROUND_2026-11-12 1a: one failing call never replaces the overview; only its own card shows an inline error.
const SUMMARY = "**/api/v1/platform/summary";
const RENDER_502 = "<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body>Bad Gateway</body></html>";

/** The cards that do not depend on the failing call, and the page error that must never appear. */
async function expectOtherCards(page: Page, { metrics = true, attention = true, recent = true } = {}): Promise<void> {
  if (metrics) await expect(page.getByTestId("overview-metrics").getByText(t("platformAdmin.overview.metrics.users"))).toBeVisible();
  for (const key of ["newCourse", "grantPro", "codes"]) {
    await expect(page.getByRole("link", { name: t(`platformAdmin.overview.quick.${key}`) })).toBeVisible();
  }
  await expect(page.getByTestId("health-line")).toContainText(t("adminHealth.title"));
  if (attention) {
    await expect(page.getByTestId("needs-attention").getByRole("link", { name: new RegExp(t("platformAdmin.overview.pendingRequests")) })).toBeVisible();
  }
  if (recent) await expect(page.getByTestId("recent-exams").getByRole("heading", { name: t("access.admin.recent.title") })).toBeVisible();
  await expect(page.getByText(t("mascot.error.title"), { exact: true })).toHaveCount(0); // the page's error boundary
}

test("admin overview: the summary down (502 HTML while the server wakes) shows only inside Needs attention", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  let calls = 0;
  await page.route(SUMMARY, (route) => {
    calls += 1;
    return route.fulfill({ status: 502, contentType: "text/html", body: RENDER_502 });
  });
  await page.goto("/ru/admin");
  await expect(page.getByRole("heading", { level: 1, name: t("platformAdmin.overview.title") })).toBeVisible();
  await expectOtherCards(page, { attention: false });

  // the shell retries (1.5 s, 4 s, 8 s), then the card alone says the server is starting, with its own retry
  const attention = page.getByTestId("needs-attention");
  await expect(attention.getByRole("alert")).toContainText(t("lms.errors.server_starting"), { timeout: 40_000 });
  expect(calls).toBe(4);
  await expect(page.getByRole("button", { name: t("ui.retry") })).toHaveCount(1);
  await expectOtherCards(page, { attention: false });
  await shots(page, "04-summary-down");

  await page.unroute(SUMMARY);
  await attention.getByRole("button", { name: t("ui.retry") }).click();
  await expect(attention.getByRole("link", { name: new RegExp(t("platformAdmin.overview.pendingRequests")) })).toBeVisible();
  await expect(attention.getByRole("alert")).toHaveCount(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("admin overview: the recent exams call failing errors only that card", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  await page.route("**/api/v1/platform/access/overview", (route) => route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"boom"}' }));
  await page.goto("/ru/admin");
  const recent = page.getByTestId("recent-exams");
  await expect(recent.getByRole("alert")).toContainText(t("lms.errors.unknown"));
  await expectOtherCards(page, { recent: false });
  await expect(page.getByRole("button", { name: t("ui.retry") })).toHaveCount(1);

  await page.unroute("**/api/v1/platform/access/overview");
  await recent.getByRole("button", { name: t("ui.retry") }).click();
  await expect(recent.getByRole("alert")).toHaveCount(0);
  await expect(recent.locator("li").or(recent.getByText(t("access.admin.recent.empty"))).first()).toBeVisible();
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("admin overview: a card that crashes while drawing errors alone (malformed metrics answer)", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  await page.route("**/api/v1/platform/overview", (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ users_total: null, active_students_7d: null, pro_active: null, attempts_submitted_7d: null }) }));
  await page.goto("/ru/admin");
  await expect(page.getByRole("heading", { level: 1, name: t("platformAdmin.overview.title") })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: t("lms.errors.unknown") })).toHaveCount(1);
  await expect(page.getByTestId("overview-metrics")).toHaveCount(0);
  await expectOtherCards(page, { metrics: false });

  await page.unroute("**/api/v1/platform/overview");
  await page.getByRole("button", { name: t("ui.retry") }).click();
  await expect(page.getByTestId("overview-metrics").getByText(t("platformAdmin.overview.metrics.users"))).toBeVisible();
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("admin overview: the health check failing leaves the page whole", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  await page.route("**/api/v1/platform/health", (route) => route.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error" }));
  await page.goto("/ru/admin");
  await expect(page.getByTestId("health-line")).toContainText(t("adminHealth.unavailable"));
  await expectOtherCards(page);
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

// DB_STORAGE_REVIEW 7.4 (slice D1): the stored database measurement adds one line to Needs attention from 70 % or when
// no full exam fits; below that the overview stays quiet.
test("admin overview: the database line appears from warning and links to Services", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
  let database: Record<string, unknown> = { level: "warning", percent: 72, fits: 1, used_bytes: 773_094_113, limit_bytes: 1_073_741_824, measured_at: new Date().toISOString() };
  await page.route("**/api/v1/platform/overview", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, database } });
  });
  await page.goto("/ru/admin");
  const attention = page.getByTestId("needs-attention");
  const row = attention.locator('[data-attention="database"]').getByRole("link");
  await expect(row).toContainText(t("platformAdmin.overview.attention.database_one", { percent: 72, count: 1 }));
  await expect(row).toHaveAttribute("href", "/ru/admin/services");
  await expect(row.getByText("72%", { exact: true })).toBeVisible(); // the badge
  await shots(page, "04-overview-database");

  database = { ...database, level: "critical", percent: 40, fits: 0 };
  await page.reload();
  await expect(attention.locator('[data-attention="database"]')).toContainText(t("platformAdmin.overview.attention.databaseFull", { percent: 40 }));

  database = { ...database, level: "notice", percent: 55, fits: 2 };
  await page.reload();
  await expect(page.getByTestId("overview-metrics")).toBeVisible();
  await expect(attention.locator('[data-attention="database"]')).toHaveCount(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
});
