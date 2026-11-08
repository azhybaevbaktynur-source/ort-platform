// Owner round 2026-11-09 item 5 (I5b, INFRA_PANEL_DESIGN): admin -> System -> Services. Playwright route mocks for
// GET /platform/infra and POST /platform/infra/refresh cover every card state; one unmocked run uses the scratch
// backend (all cards "not connected", R2 shows only our own counter). With S5_SHOTS_DIR set it writes ru screenshots at
// 375 / 1440 / 1920.
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS } from "./helpers";

const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const SHOTS = process.env.S5_SHOTS_DIR || "";
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

const GB = 1_000_000_000;
const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;
const metric = (key: string, value: number, limit: number | null, unit: string, source: string | null = null) => {
  const percent = limit ? Math.round((1000 * value) / limit) / 10 : null;
  const level = percent === null ? "ok" : percent >= 95 ? "critical" : percent >= 80 ? "warning" : "ok";
  return { key, value, limit, unit, percent, level, source };
};
const card = (provider: string, over: Record<string, unknown> = {}): Any => ({
  provider, status: "ok", plan: null, fetched_at: ago(4), duration_ms: 320, error_code: null, error_status: null,
  dashboard_url: `https://example.test/${provider}`, metrics: [], flags: [], details: {}, ...over,
});

function infra(cards: Any[]): Any {
  return {
    generated_at: ago(4), ttl_seconds: 1200, cards,
    capacity: {
      fits: 4, students: 6000, exam_bytes: 226_000_000, used_bytes: 41_451_520, limit_bytes: 1_073_741_824, used_source: "neon",
      estimated: true, history_seconds: 21600, per_row_bytes: { attempt_items: 241 },
    },
    costs: {
      total_usd: 0, complete: true, source: "docs/COSTS.md", as_of: "2026-11-09",
      rows: [
        { key: "render", service: "Render", plan: "Free", usd_per_month: 0, next_plan: "Starter", next_usd_per_month: 7, next_unit: "month", verified: false },
        { key: "neon", service: "Neon", plan: "Free", usd_per_month: 0, next_plan: "Launch", next_usd_per_month: null, next_unit: null, verified: false },
      ],
    },
  };
}

const OK_NEON = card("neon", { plan: "free", metrics: [
  metric("storage", 41_451_520, 1_073_741_824, "bytes"), metric("compute", 6.6, 100, "cu_hours"), metric("branches", 4, 10, "count"),
  metric("data_transfer", 123_000_000, null, "bytes"),
] });
const WARN_R2 = card("r2", { plan: "free", metrics: [
  metric("storage", 8_500_000_000, 10 * GB, "bytes", "cloudflare"), metric("class_a", 120_000, 1_000_000, "requests", "cloudflare"),
  metric("storage", 6_000_000_000, 10 * GB, "bytes", "counter"),
], flags: [{ key: "counter_drift", level: "warning" }], details: { storage_page: "/admin/storage" } });
const CRIT_EMAIL = card("email", { plan: "free", metrics: [metric("sent_today", 290, 300, "emails")], details: { provider: "brevo" } });
const NOT_CONN_VERCEL = card("vercel", { status: "not_connected", fetched_at: null, duration_ms: null });
const ERROR_RENDER = card("render", { status: "error", plan: "free", error_code: "timeout", fetched_at: ago(95), metrics: [], flags: [{ key: "sleeps", level: "warning" }] });

async function mock(page: Page, body: Any, refresh?: (route: import("@playwright/test").Route) => Promise<void>): Promise<void> {
  await page.route("**/api/v1/platform/infra", (route) => route.fulfill({ json: body }));
  await page.route("**/api/v1/platform/infra/refresh", refresh ?? ((route) => route.fulfill({ json: body })));
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await signIn(page, seed().admin);
});

test("all card states render with levels, flags, hints and no secrets", async ({ page }) => {
  const body = infra([OK_NEON, ERROR_RENDER, NOT_CONN_VERCEL, WARN_R2, CRIT_EMAIL]);
  await mock(page, body);
  await page.goto("/ru/admin/services");
  await expect(page.getByRole("heading", { level: 1, name: t("infra.title") })).toBeVisible();
  await expect(page.getByTestId("infra-updated")).toContainText("4");

  // menu entry in the System group
  await expect(page.getByRole("link", { name: t("infra.nav") }).first()).toBeVisible();

  // ok: bars with value of limit and percent, no warning styling
  const neon = page.getByTestId("service-neon");
  await expect(neon).toHaveAttribute("data-tone", "ok");
  await expect(neon.getByTestId("metric-storage")).toContainText("3,9%"); // 41.45 MB of 1.07 GB
  await expect(neon.getByTestId("metric-branches")).toContainText(t("infra.of", { value: 4, limit: 10 }));
  await expect(neon.getByRole("progressbar", { name: t("infra.metric.compute") })).toHaveAttribute("aria-valuenow", "7");
  await expect(neon.getByTestId("metric-data_transfer")).toContainText(t("infra.noLimit"));
  await expect(neon.getByRole("link", { name: t("infra.openDashboard") })).toHaveAttribute("href", "https://example.test/neon");

  // R2 warning: both sources, amber, drift flag, link to our storage page
  const r2 = page.getByTestId("service-r2");
  await expect(r2).toHaveAttribute("data-tone", "warning");
  await expect(r2.getByTestId("metric-storage-cloudflare")).toHaveAttribute("data-level", "warning");
  await expect(r2.getByTestId("metric-storage-cloudflare")).toContainText(t("infra.source.cloudflare"));
  await expect(r2.getByTestId("metric-storage-counter")).toContainText(t("infra.source.counter"));
  await expect(r2.getByTestId("metric-storage-counter")).toHaveAttribute("data-level", "ok");
  await expect(r2.getByText(t("infra.flag.counter_drift"))).toBeVisible();
  await expect(r2.getByRole("link", { name: t("infra.openStorage") })).toHaveAttribute("href", "/ru/admin/storage");

  // critical (97 %)
  const email = page.getByTestId("service-email");
  await expect(email).toHaveAttribute("data-tone", "critical");
  await expect(email.getByTestId("metric-sent_today")).toHaveAttribute("data-level", "critical");

  // error keeps the flags/time and says why
  const render = page.getByTestId("service-render");
  await expect(render).toHaveAttribute("data-tone", "error");
  await expect(render.getByRole("alert")).toContainText(t("infra.errorLine", { reason: t("infra.error.timeout") }));
  await expect(render.getByRole("alert")).toContainText(t("infra.previous", { when: "" }).split(" ")[0]);
  await expect(render.getByText(t("infra.flag.sleeps"))).toBeVisible();

  // not connected: what to set on the server + dashboard link, never a key
  const vercel = page.getByTestId("service-vercel");
  await expect(vercel).toHaveAttribute("data-tone", "muted");
  await expect(vercel).toContainText(t("infra.status.not_connected"));
  await expect(vercel).toContainText("VERCEL_TOKEN");
  await expect(vercel.getByRole("link", { name: t("infra.openDashboard") })).toBeVisible();

  // capacity and cost tiles
  await expect(page.getByTestId("infra-capacity")).toContainText(t("infra.capacity.fits", { students: "6 000" }));
  await expect(page.getByTestId("infra-capacity")).toContainText(t("infra.capacity.estimated"));
  await expect(page.getByTestId("infra-costs")).toContainText(t("infra.costs.title"));
  await expect(page.getByTestId("infra-costs")).toContainText("Render · Free");
  await shots(page, "01-services-mixed");
});

test("refresh button posts, disables while in flight and shows new data", async ({ page }) => {
  const before = infra([card("neon", { plan: "free", metrics: [metric("branches", 4, 10, "count")] })]);
  const after = infra([card("neon", { plan: "free", metrics: [metric("branches", 6, 10, "count")] })]);
  let posts = 0;
  await mock(page, before, async (route) => {
    posts += 1;
    await new Promise((r) => setTimeout(r, 600));
    await route.fulfill({ json: after });
  });
  await page.goto("/ru/admin/services");
  const btn = page.getByRole("button", { name: t("infra.refresh") });
  await expect(page.getByTestId("metric-branches")).toContainText(t("infra.of", { value: 4, limit: 10 }));
  await btn.click();
  await expect(page.getByRole("button", { name: t("infra.refreshing") })).toBeDisabled();
  await expect(page.getByTestId("metric-branches")).toContainText(t("infra.of", { value: 6, limit: 10 }));
  await expect(page.getByRole("button", { name: t("infra.refresh") })).toBeEnabled();
  expect(posts).toBe(1);
});

test("a 429 on refresh shows the rate-limit message and keeps the figures", async ({ page }) => {
  await mock(page, infra([OK_NEON]), (route) => route.fulfill({ status: 429, json: { code: "rate_limited", message: "x", details: {} } }));
  await page.goto("/ru/admin/services");
  await page.getByRole("button", { name: t("infra.refresh") }).click();
  await expect(page.getByTestId("infra-rate-limited")).toContainText(t("infra.rateLimited"));
  await expect(page.getByTestId("metric-branches")).toBeVisible();
  await expect(page.getByRole("button", { name: t("infra.refresh") })).toBeEnabled();
});

test("a refreshing card shows progress, the button waits, and the page polls until it settles", async ({ page }) => {
  let gets = 0;
  const busy = infra([card("neon", { status: "refreshing", plan: "free", metrics: [metric("branches", 4, 10, "count")] })]);
  const done = infra([card("neon", { plan: "free", metrics: [metric("branches", 5, 10, "count")] })]);
  await page.route("**/api/v1/platform/infra", (route) => { gets += 1; return route.fulfill({ json: gets === 1 ? busy : done }); });
  await page.goto("/ru/admin/services");
  const neon = page.getByTestId("service-neon");
  await expect(neon.getByRole("status")).toContainText(t("infra.status.refreshing"));
  await expect(neon.getByTestId("metric-branches")).toBeVisible(); // previous figures stay
  await expect(page.getByRole("button", { name: t("infra.refreshing") })).toBeDisabled();
  await expect(neon.getByTestId("metric-branches")).toContainText(t("infra.of", { value: 5, limit: 10 }), { timeout: 10_000 });
  await expect(page.getByRole("button", { name: t("infra.refresh") })).toBeEnabled();
});

test("unmocked: the scratch backend has nothing connected except our R2 counter", async ({ page }) => {
  await page.goto("/ru/admin/services");
  await expect(page.getByRole("heading", { level: 1, name: t("infra.title") })).toBeVisible();
  for (const p of ["neon", "render", "vercel"]) {
    await expect(page.getByTestId(`service-${p}`)).toHaveAttribute("data-status", "not_connected");
  }
  const r2 = page.getByTestId("service-r2");
  await expect(r2.getByTestId("metric-storage-counter")).toBeVisible();
  await expect(r2.getByTestId("metric-storage-cloudflare")).toHaveCount(0);
  await expect(r2).toContainText("CLOUDFLARE_API_TOKEN");
  await expect(page.getByTestId("infra-capacity")).toBeVisible();
  await expect(page.getByTestId("infra-costs")).toBeVisible();
  await shots(page, "02-services-unmocked");
});
