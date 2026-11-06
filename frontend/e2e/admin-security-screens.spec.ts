// S1 admin security: screenshots of the changed screens in ru at 375, 1440 and 1920 px for the UX check (AGENTS.md
// rule 10). Runs only with S1_SHOTS_DIR set; writes PNGs there, compares nothing.
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { seed, settle, tr, watchCsp } from "./helpers";
import { confirmSetup, passwordStep, startSetup } from "./mfa";

const DIR = process.env.S1_SHOTS_DIR || "";
const SIZES = [
  { name: "375", width: 375, height: 812 },
  { name: "1440", width: 1440, height: 900 },
  { name: "1920", width: 1920, height: 1080 },
];

async function shots(page: Page, name: string): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await settle(page, false);
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(DIR, `${name}-${size.name}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.skip(!DIR, "set S1_SHOTS_DIR to write the S1 screenshots");

test("S1 screens (ru, 375 / 1440 / 1920)", async ({ page }) => {
  fs.mkdirSync(DIR, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  const admin = seed().shots_admin;
  watchCsp(page);
  await page.goto("/ru/login?redirect=/ru/admin/security");
  await passwordStep(page, admin.email, admin.password);
  await page.waitForURL(/\/ru\/admin\/security/);

  const secret = await startSetup(page, admin.password);
  await shots(page, "01-security-setup-qr");
  await confirmSetup(page, secret);
  await shots(page, "02-recovery-codes");
  await page.getByLabel(tr("ru", "adminSecurity.codes.saved")).check();
  await page.getByRole("button", { name: tr("ru", "adminSecurity.codes.done") }).click();
  await expect(page.getByText(tr("ru", "adminSecurity.badgeOn")).first()).toBeVisible();
  await shots(page, "03-security-enabled");

  await page.goto("/ru/admin");
  await expect(page.getByTestId("health-checks")).toBeVisible();
  await shots(page, "04-overview-health");

  const target = seed().students[Object.keys(seed().students)[0]];
  await page.goto(`/ru/admin/users/${target.profile.id}`);
  const more = page.getByRole("button", { name: tr("ru", "coursePage.moreActions") });
  await expect(more).toBeVisible();
  await shots(page, "05-user-page");
  for (const [item, file] of [["adminSecurity.user.makeAdmin", "06-user-make-admin-dialog"],
    ["adminSecurity.user.endSessions", "07-user-end-sessions-dialog"]] as const) {
    await more.click();
    await page.getByRole("menuitem", { name: tr("ru", item) }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await shots(page, file);
    await page.getByRole("alertdialog").getByRole("button", { name: tr("ru", "ui.cancel") }).click();
    await expect(page.getByRole("alertdialog")).toHaveCount(0);
  }

  // the code step of the sign-in (sign out first; the code is not entered)
  await page.goto("/ru/admin/security");
  await page.getByRole("button", { name: tr("ru", "adminSecurity.sessions.button") }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: tr("ru", "adminSecurity.sessions.button") }).click();
  await page.waitForURL(/\/ru\/login/);
  await passwordStep(page, admin.email, admin.password);
  await expect(page.getByRole("heading", { name: tr("ru", "auth.mfa.title") })).toBeVisible();
  await shots(page, "08-login-code-step");
});
