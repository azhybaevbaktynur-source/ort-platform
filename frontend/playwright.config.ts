import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * ORT browser e2e + screenshot baselines (PHASE_6_DESIGN section 6, docs/phases/ORT_BASELINE/README.md).
 *
 * Two web servers: the scratch backend (scripts/e2e_backend.sh: env -i, fresh SQLite, seeded through the API)
 * and the *built* frontend (`next start`). The frontend must be built with NEXT_PUBLIC_API_URL set to the bare
 * backend origin (http://127.0.0.1:$E2E_API_PORT); E2E_WEB_DIR points at that build (default: this folder).
 */
const API_PORT = Number(process.env.E2E_API_PORT || 8765);
const WEB_PORT = Number(process.env.E2E_WEB_PORT || 3765);
const E2E_DIR = process.env.E2E_DIR || "/tmp/ort_e2e";
const WEB_DIR = process.env.E2E_WEB_DIR || __dirname;
const WEB_ORIGIN = `http://127.0.0.1:${WEB_PORT}`;
const CI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  outputDir: path.join(E2E_DIR, "results"),
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: CI,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  // CI: the github reporter turns every failure into an `::error` annotation (message + file:line), readable on
  // the public check run without the job log; the html report goes into the failure artifact
  reporter: CI ? [["github"], ["list"], ["html", { outputFolder: path.join(E2E_DIR, "report"), open: "never" }]] : "list",
  use: {
    baseURL: WEB_ORIGIN,
    // local runs use the installed Chrome; CI installs Playwright's chromium (`npx playwright install chromium`)
    channel: CI ? undefined : "chrome",
    headless: true,
    locale: "ru-RU",
    timezoneId: "UTC",
    colorScheme: "light",
    deviceScaleFactor: 1,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // Item 4: the phone-sheet spec runs on iPhone (WebKit) and Pixel 7 (Chromium) only; every other spec keeps the
  // desktop project exactly as before.
  projects: [
    { name: "default", testIgnore: /mobile-sheets\.spec/ },
    { name: "mobile-ios", testMatch: /mobile-sheets\.spec/, use: { ...devices["iPhone 14"], channel: "" as never, // "" (not undefined) overrides the top-level Chrome channel, WebKit has none
      locale: "ru-RU" } },
    { name: "mobile-android", testMatch: /mobile-sheets\.spec/, use: { ...devices["Pixel 7"], channel: CI ? undefined : "chrome", locale: "ru-RU" } },
  ],
  webServer: [
    {
      command: "bash ../scripts/e2e_backend.sh",
      cwd: __dirname,
      url: `http://127.0.0.1:${API_PORT}/health`,
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        E2E_DIR,
        E2E_API_PORT: String(API_PORT),
        E2E_WEB_ORIGIN: WEB_ORIGIN,
        ...(process.env.E2E_PYTHON ? { E2E_PYTHON: process.env.E2E_PYTHON } : {}),
        // the Google sign-in stub (default E2E_API_PORT+2; +1 is admin-mfa-gate's second server): oauth-google.spec.ts
        ...(process.env.E2E_OAUTH_STUB_PORT ? { E2E_OAUTH_STUB_PORT: process.env.E2E_OAUTH_STUB_PORT } : {}),
      },
    },
    {
      command: `npx next start -H 127.0.0.1 -p ${WEB_PORT}`,
      cwd: WEB_DIR,
      url: `${WEB_ORIGIN}/ru`,
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
