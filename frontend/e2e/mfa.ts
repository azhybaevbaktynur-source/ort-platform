// S1 admin security: the "authenticator app" of the two-step login specs (RFC 6238, SHA1, 6 digits, 30 s) and shared steps.
import crypto from "node:crypto";
import { expect, type Page } from "@playwright/test";
import { tr } from "./helpers";

const STEP = 30;

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/[\s=]/g, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

export function hotp(secret: string, counter: number): string {
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(counter));
  const mac = crypto.createHmac("sha1", base32(secret)).update(msg).digest();
  const offset = mac[mac.length - 1] & 0x0f;
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

export const stepNow = () => Math.floor(Date.now() / 1000 / STEP);

/** The real login form (no injected token: a stale one would come back on every navigation). */
export async function passwordStep(page: Page, email: string, password: string): Promise<void> {
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: tr("ru", "auth.signInButton") }).click();
}

/** On /admin/security: start the setup, read the key. */
export async function startSetup(page: Page): Promise<string> {
  await page.getByRole("button", { name: tr("ru", "adminSecurity.setup.start") }).click();
  const secret = (await page.getByTestId("mfa-secret").innerText()).replace(/\s/g, "");
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);
  await expect(page.getByRole("img", { name: tr("ru", "adminSecurity.setup.qrAlt") })).toBeVisible();
  return secret;
}

/** Confirms the setup with the current code; returns the step it used (never accepted again). */
export async function confirmSetup(page: Page, secret: string): Promise<number> {
  const step = stepNow();
  await page.getByLabel(tr("ru", "adminSecurity.setup.codeLabel")).fill(hotp(secret, step));
  await page.getByRole("button", { name: tr("ru", "adminSecurity.setup.confirm") }).click();
  await expect(page.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  return step;
}

/** Ticks "I have saved these codes" and closes the list. */
export async function closeRecoveryCodes(page: Page): Promise<void> {
  await page.getByLabel(tr("ru", "adminSecurity.codes.saved")).check();
  await page.getByRole("button", { name: tr("ru", "adminSecurity.codes.done") }).click();
  await expect(page.getByTestId("recovery-codes")).toHaveCount(0);
}
