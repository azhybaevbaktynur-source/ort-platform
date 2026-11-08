import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { settle, tr } from "./helpers";

/**
 * AUTH_SOCIAL_DESIGN slice B: the auth screens in the split layout, the provider buttons and the Google callback page.
 * The backend slice is not needed: `/auth/providers` and `/auth/oauth/complete` are Playwright routes.
 * Screenshots (ru, 375 / 1440 / 1920) with ITEM3B_SHOTS=<dir>.
 */

const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const SHOTS = process.env.ITEM3B_SHOTS ? path.resolve(process.env.ITEM3B_SHOTS) : null;

const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
const TICKET = `${b64({ alg: "HS256" })}.${b64({ typ: "oauth_ticket", email: "new.person@example.com", name: "Айгерим Новая", provider: "google" })}.sig`;
const SESSION = { access_token: "e30.e30.sig", token_type: "bearer", user: { id: "usr_e2e_oauth", email: "new.person@example.com", displayName: "Айгерим Новая" } };

async function providers(page: Page, on: { google: boolean; apple: boolean }) {
  await page.route("**/auth/providers", (r) => r.fulfill({ json: on }));
}

const alertBox = (page: Page) => page.locator('div[role="alert"]:not([id])'); // not the route announcer

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

test.describe("provider buttons", () => {
  test("hidden when no provider is on: no buttons, no divider", async ({ page }) => {
    await providers(page, { google: false, apple: false });
    for (const p of ["/ru/register", "/ru/login"]) {
      await page.goto(p);
      await expect(page.getByLabel(t("auth.email"))).toBeVisible();
      await settle(page);
      await expect(page.getByText(t("auth.continueWithGoogle"))).toHaveCount(0);
      await expect(page.getByText(t("auth.continueWithApple"))).toHaveCount(0);
      await expect(page.getByRole("separator")).toHaveCount(0);
    }
  });

  test("Google shown, Apple hidden; links go to the backend start route", async ({ page }) => {
    await providers(page, { google: true, apple: false });
    await page.goto("/ru/login?redirect=%2Fru%2Fcourses%2Fx");
    const google = page.getByRole("link", { name: t("auth.continueWithGoogle") });
    await expect(google).toBeVisible();
    await expect(google).toHaveAttribute("href", /\/auth\/google\/start\?lang=ru&redirect=%2Fru%2Fcourses%2Fx$/);
    await expect(page.getByText(t("auth.continueWithApple"))).toHaveCount(0);
    await expect(page.getByRole("separator")).toBeVisible();
  });

  test("Apple shown when on; forgot password has no buttons but a hint for Google users", async ({ page }) => {
    await providers(page, { google: true, apple: true });
    await page.goto("/ru/register");
    await expect(page.getByRole("link", { name: t("auth.continueWithApple") })).toBeVisible();
    await page.goto("/ru/forgot-password");
    await expect(page.getByText(t("auth.forgotGoogleHint"))).toBeVisible();
    await expect(page.getByRole("link", { name: t("auth.continueWithGoogle") })).toHaveCount(0);
  });

  test("login shows the refusal from ?oauth_error= once and removes the parameter", async ({ page }) => {
    await providers(page, { google: true, apple: false });
    await page.goto("/ru/login?oauth_error=oauth_email_unverified&redirect=%2Fru%2Fcourses");
    await expect(alertBox(page)).toHaveText(t("auth.errors.oauth_email_unverified"));
    await expect(page).toHaveURL(/\/ru\/login\?redirect=%2Fru%2Fcourses$/);
  });
});

test.describe("Google callback page", () => {
  test("no ticket: straight to the login page", async ({ page }) => {
    await page.goto("/ru/oauth-callback");
    await expect(page).toHaveURL(/\/ru\/login$/);
  });

  test("new user: the ticket leaves the URL, the Almost done step sends age, policies and name", async ({ page }) => {
    await providers(page, { google: true, apple: false });
    const bodies: Record<string, unknown>[] = [];
    await page.route("**/auth/oauth/complete", async (r) => {
      const body = r.request().postDataJSON();
      bodies.push(body);
      if (!body.ageBand) await r.fulfill({ status: 422, json: { detail: { code: "oauth_profile_required", message: "profile" } } });
      else await r.fulfill({ json: SESSION });
    });
    await page.route("**/auth/me", (r) => r.fulfill({ json: { id: SESSION.user.id, email: SESSION.user.email, displayName: SESSION.user.displayName } }));
    await page.goto(`/ru/oauth-callback#t=${TICKET}&r=%2Fru%2Fabout`);
    await expect(page.getByRole("heading", { name: t("auth.oauth.completeTitle") })).toBeVisible();
    expect(page.url()).not.toContain("#");
    expect(await page.evaluate(() => window.location.hash)).toBe("");
    await expect(page.getByText(t("auth.oauth.signedInAs", { email: "new.person@example.com" }))).toBeVisible();
    await expect(page.getByLabel(t("auth.displayName"))).toHaveValue("Айгерим Новая");
    await expect(page.getByRole("button", { name: t("auth.oauth.completeButton") })).toBeDisabled();

    await page.getByRole("button", { name: t("privacy.age.14_17") }).click();
    await page.getByRole("checkbox").check();
    await page.getByLabel(t("auth.displayName")).fill("Айгерим К.");
    await page.getByRole("button", { name: t("auth.oauth.completeButton") }).click();
    await expect(page).toHaveURL(/\/ru\/about/);
    expect(bodies).toHaveLength(2);
    expect(bodies[0]).toEqual({ ticket: TICKET });
    expect(bodies[1]).toMatchObject({ ticket: TICKET, ageBand: "14_17", displayName: "Айгерим К." });
    expect((bodies[1].policyVersionIds as string[]).length).toBeGreaterThan(0);
    expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBe(SESSION.access_token);
  });

  test("under 14: no policy box, goes to the privacy page", async ({ page }) => {
    await page.route("**/auth/oauth/complete", async (r) => {
      const body = r.request().postDataJSON();
      if (!body.ageBand) await r.fulfill({ status: 422, json: { detail: { code: "oauth_profile_required" } } });
      else await r.fulfill({ json: SESSION });
    });
    await page.goto(`/ru/oauth-callback#t=${TICKET}`);
    await page.getByRole("button", { name: t("privacy.age.under_14") }).click();
    await expect(page.getByRole("checkbox")).toHaveCount(0);
    await page.getByRole("button", { name: t("auth.oauth.completeButton") }).click();
    await expect(page).toHaveURL(/\/ru\/privacy/);
  });

  test("two-step login: the existing MFA step appears and finishes with /auth/mfa", async ({ page }) => {
    await page.route("**/auth/oauth/complete", (r) => r.fulfill({ status: 403, json: { detail: { code: "mfa_required", message: "mfa", challenge: "chal-123" } } }));
    let mfaBody: unknown = null;
    await page.route("**/auth/mfa", async (r) => {
      mfaBody = r.request().postDataJSON();
      await r.fulfill({ json: SESSION });
    });
    await page.route("**/auth/me", (r) => r.fulfill({ json: { id: SESSION.user.id, email: SESSION.user.email } }));
    await page.goto(`/ru/oauth-callback#t=${TICKET}&r=%2Fru%2Fabout`);
    await expect(page.getByRole("heading", { name: t("auth.mfa.title") })).toBeVisible();
    await page.getByLabel(t("auth.mfa.codeLabel")).fill("123456");
    await page.getByRole("button", { name: t("auth.mfa.button") }).click();
    await expect(page).toHaveURL(/\/ru\/about/);
    expect(mfaBody).toEqual({ challenge: "chal-123", code: "123456" });
  });

  for (const code of ["oauth_ticket_invalid", "account_disabled", "rate_limited"]) {
    test(`error ${code}: translated text and a way back`, async ({ page }) => {
      await page.route("**/auth/oauth/complete", (r) => r.fulfill({ status: code === "rate_limited" ? 429 : 401, json: { detail: { code, message: "raw server text" } } }));
      await page.goto(`/ru/oauth-callback#t=${TICKET}`);
      await expect(alertBox(page)).toHaveText(t(`auth.errors.${code}`));
      await page.getByRole("link", { name: t("auth.oauth.backToLogin") }).click();
      await expect(page).toHaveURL(/\/ru\/login$/);
    });
  }
});

test.describe("layout", () => {
  test("no horizontal scroll at 375 px on every auth screen", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await providers(page, { google: true, apple: true });
    await page.route("**/auth/oauth/complete", (r) => r.fulfill({ status: 422, json: { detail: { code: "oauth_profile_required" } } }));
    for (const p of ["/ru/register", "/ru/login", "/ru/forgot-password", "/ru/reset-password?token=abc", `/ru/oauth-callback#t=${TICKET}`]) {
      await page.goto(p);
      await page.getByRole("heading").first().waitFor();
      await settle(page);
      await noHorizontalScroll(page);
    }
  });

  test("screens in ru at 375 / 1440 / 1920", async ({ page }) => {
    test.skip(!SHOTS, "ITEM3B_SHOTS only");
    fs.mkdirSync(SHOTS!, { recursive: true });
    await providers(page, { google: true, apple: false });
    await page.route("**/auth/oauth/complete", (r) => r.fulfill({ status: 422, json: { detail: { code: "oauth_profile_required" } } }));
    const screens: [string, string, string][] = [
      ["register", "/ru/register", "form"],
      ["login", "/ru/login", "form"],
      ["forgot-password", "/ru/forgot-password", "form"],
      ["oauth-callback", `/ru/oauth-callback#t=${TICKET}`, "form"],
    ];
    for (const [name, url] of screens.map((s) => [s[0], s[1]])) {
      for (const width of [375, 1440, 1920]) {
        await page.setViewportSize({ width, height: width === 375 ? 812 : 900 });
        await page.goto(url);
        await page.locator("form").first().waitFor();
        await settle(page);
        await noHorizontalScroll(page);
        await page.screenshot({ path: path.join(SHOTS!, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
      }
    }
  });
});
