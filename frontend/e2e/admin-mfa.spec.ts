// S1 admin security (docs/ROADMAP_EXAM_PREP.md S1): a platform admin sets up two-step login on /admin/security, ends all
// their sessions, and signs in again with the password and a code from the "authenticator app" (computed here, RFC 6238).
import crypto from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { seed, tr, watchCsp } from "./helpers";

const STEP = 30;

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/[\s=]/g, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

function hotp(secret: string, counter: number): string {
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(counter));
  const mac = crypto.createHmac("sha1", base32(secret)).update(msg).digest();
  const offset = mac[mac.length - 1] & 0x0f;
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

const stepNow = () => Math.floor(Date.now() / 1000 / STEP);

/** The real login form (no injected token: a stale one would come back on every navigation). */
async function passwordStep(page: Page, email: string, password: string): Promise<void> {
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: tr("ru", "auth.signInButton") }).click();
}

test("an admin sets up two-step login, ends every session and signs in with a code", async ({ page }) => {
  const admin = seed().mfa_admin;
  watchCsp(page);
  await page.goto("/ru/login?redirect=/ru/admin/security");
  await passwordStep(page, admin.email, admin.password); // no two-step login yet: straight in
  await page.waitForURL(/\/ru\/admin\/security/);
  await expect(page.getByText(tr("ru", "adminSecurity.badgeOff"))).toBeVisible();

  await page.getByRole("button", { name: tr("ru", "adminSecurity.setup.start") }).click();
  const secret = (await page.getByTestId("mfa-secret").innerText()).replace(/\s/g, "");
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);
  await expect(page.getByRole("img", { name: tr("ru", "adminSecurity.setup.qrAlt") })).toBeVisible();

  const setupStep = stepNow();
  await page.getByLabel(tr("ru", "adminSecurity.setup.codeLabel")).fill(hotp(secret, setupStep));
  await page.getByRole("button", { name: tr("ru", "adminSecurity.setup.confirm") }).click();

  const codes = page.getByTestId("recovery-codes").locator("li");
  await expect(codes).toHaveCount(10);
  await expect(codes.first()).toHaveText(/^[a-z2-9]{5}-[a-z2-9]{5}$/);
  const done = page.getByRole("button", { name: tr("ru", "adminSecurity.codes.done") });
  await expect(done).toBeDisabled();
  await page.getByLabel(tr("ru", "adminSecurity.codes.saved")).check();
  await done.click();
  await expect(codes).toHaveCount(0);
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
