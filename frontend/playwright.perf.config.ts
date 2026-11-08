import path from "node:path";
import { defineConfig } from "@playwright/test";

/**
 * PERFORMANCE_AUDIT: configuration for e2e/perf-waterfall.spec.ts only. Unlike playwright.config.ts it starts no
 * servers: the scratch backend (scripts/e2e_backend.sh, port $E2E_API_PORT) and a built frontend (`next start`,
 * PERF_WEB) are already running, so the same backend serves several frontend builds (before/after) one after another.
 *   PERF_RUN=1 PERF_LABEL=after PERF_WEB=http://127.0.0.1:3031 E2E_DIR=/tmp/ort_e2e \
 *     npx playwright test -c playwright.perf.config.ts e2e/perf-waterfall.spec.ts
 */
const E2E_DIR = process.env.E2E_DIR || "/tmp/ort_e2e";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /perf-waterfall\.spec\.ts/,
  outputDir: path.join(E2E_DIR, "perf-results"),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 3_000_000,
  reporter: "list",
  use: {
    baseURL: process.env.PERF_WEB || "http://127.0.0.1:3031",
    channel: process.env.CI ? undefined : "chrome",
    headless: true,
    locale: "ru-RU",
    timezoneId: "UTC",
    colorScheme: "light",
  },
});
