// S1 admin security: with ADMIN_MFA_REQUIRED=true, an admin without two-step login who opens /ru/admin lands on
// /ru/admin/security, sets it up, and then reaches the overview.
//
// The main e2e server runs with the requirement off (every other admin spec uses unenrolled admins). This spec starts a
// second server on the same scratch database and throwaway key with the requirement on (`e2e_backend.sh
// --mfa-required`) and sends only this page's API calls there.
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { E2E_DIR, seed, tr, watchCsp } from "./helpers";
import { closeRecoveryCodes, confirmSetup, passwordStep, startSetup } from "./mfa";

const API_PORT = Number(process.env.E2E_API_PORT || 8765);
const STRICT_PORT = API_PORT + 1;
const WEB_ORIGIN = `http://127.0.0.1:${Number(process.env.E2E_WEB_PORT || 3765)}`;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn("bash", [path.join(__dirname, "..", "..", "scripts", "e2e_backend.sh"), "--mfa-required", String(STRICT_PORT)], {
    env: { ...process.env, E2E_DIR, E2E_WEB_ORIGIN: WEB_ORIGIN }, stdio: "ignore",
  });
  for (let i = 0; i < 120; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${STRICT_PORT}/health`)).ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("the ADMIN_MFA_REQUIRED=true server did not start");
});

test.afterAll(() => {
  server?.kill("SIGTERM");
});

test("an admin without two-step login is sent to set it up, then reaches the overview", async ({ page }) => {
  await page.route(`http://127.0.0.1:${API_PORT}/**`, async (route) => {
    const url = route.request().url().replace(`127.0.0.1:${API_PORT}`, `127.0.0.1:${STRICT_PORT}`);
    await route.fulfill({ response: await route.fetch({ url }) });
  });
  const admin = seed().gate_admin;
  watchCsp(page);
  await page.goto("/ru/login");
  await passwordStep(page, admin.email, admin.password); // no two-step login yet: the password signs in
  // every page refuses the account (403 mfa_enrollment_required), so the first page after the login sends it on
  await expect(page).toHaveURL(/\/ru\/admin\/security$/, { timeout: 15_000 });
  await page.waitForLoadState("networkidle");

  // the client redirect can abort the first navigation (ERR_ABORTED), so wait on the URL, not the load
  await page.goto("/ru/admin", { waitUntil: "commit" }).catch((e) => { if (!String(e).includes("ERR_ABORTED")) throw e; });
  await expect(page).toHaveURL(/\/ru\/admin\/security$/, { timeout: 15_000 });
  await expect(page.getByText(tr("ru", "adminSecurity.setup.required"))).toBeVisible();
  const nav = page.getByRole("navigation", { name: tr("ru", "platformAdmin.nav.label") });
  await expect(nav.getByRole("link", { name: tr("ru", "platformAdmin.nav.overview") })).toHaveCount(0);

  const secret = await startSetup(page, admin.password);
  await confirmSetup(page, secret);
  await closeRecoveryCodes(page);
  await expect(page.getByText(tr("ru", "adminSecurity.badgeOn")).first()).toBeVisible();

  await nav.getByRole("link", { name: tr("ru", "platformAdmin.nav.overview") }).click();
  await page.waitForURL(/\/ru\/admin$/);
  await expect(page.getByRole("heading", { name: tr("ru", "platformAdmin.overview.title") })).toBeVisible();
  await expect(page.getByText(tr("ru", "adminHealth.title"))).toBeVisible();
});
