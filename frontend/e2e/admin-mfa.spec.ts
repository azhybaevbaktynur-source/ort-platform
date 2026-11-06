// S1 admin security (docs/ROADMAP_EXAM_PREP.md S1): a platform admin sets up two-step login on /admin/security, ends all
// their sessions, and signs in again with the password and a code from the "authenticator app" (computed here, RFC 6238).
import { expect, test } from "@playwright/test";
import { seed, tr, watchCsp } from "./helpers";
import { closeRecoveryCodes, confirmSetup, hotp, passwordStep, startSetup, stepNow } from "./mfa";

test("an admin sets up two-step login, ends every session and signs in with a code", async ({ page }) => {
  const admin = seed().mfa_admin;
  watchCsp(page);
  await page.goto("/ru/login?redirect=/ru/admin/security");
  await passwordStep(page, admin.email, admin.password); // no two-step login yet: straight in
  await page.waitForURL(/\/ru\/admin\/security/);
  await expect(page.getByText(tr("ru", "adminSecurity.badgeOff"))).toBeVisible();

  const secret = await startSetup(page);
  const setupStep = await confirmSetup(page, secret);
  const codes = page.getByTestId("recovery-codes").locator("li");
  await expect(codes.first()).toHaveText(/^[a-z2-9]{5}-[a-z2-9]{5}$/);
  await expect(page.getByRole("button", { name: tr("ru", "adminSecurity.codes.done") })).toBeDisabled();
  await closeRecoveryCodes(page);
  await expect(page.getByText(tr("ru", "adminSecurity.badgeOn")).first()).toBeVisible();

  // end every session (this one too): back to the sign-in page
  await page.getByRole("button", { name: tr("ru", "adminSecurity.sessions.button") }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: tr("ru", "adminSecurity.sessions.button") }).click();
  await page.waitForURL(/\/ru\/login/);

  // the password alone no longer signs in: the code step follows
  await passwordStep(page, admin.email, admin.password);
  await expect(page.getByRole("heading", { name: tr("ru", "auth.mfa.title") })).toBeVisible();

  const loginStep = Math.max(setupStep + 1, stepNow()); // the setup's code is never accepted again
  const valid = new Set([loginStep - 1, loginStep, loginStep + 1].map((s) => hotp(secret, s)));
  const wrong = ["000000", "111111", "222222", "333333"].find((c) => !valid.has(c))!;
  const field = page.getByLabel(tr("ru", "auth.mfa.codeLabel"));
  await field.fill(wrong);
  await page.getByRole("button", { name: tr("ru", "auth.mfa.button") }).click();
  await expect(page.getByRole("alert").filter({ hasText: tr("ru", "auth.errors.mfa_invalid_code") })).toBeVisible();

  await field.fill(hotp(secret, loginStep));
  await page.getByRole("button", { name: tr("ru", "auth.mfa.button") }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login")); // back where the sign-out happened

  await page.goto("/ru/admin/security");
  await expect(page.getByText(tr("ru", "adminSecurity.badgeOn")).first()).toBeVisible();
  await expect(page.getByText(tr("ru", "adminSecurity.enabled.codesLeft", { n: 10 }))).toBeVisible();
});
