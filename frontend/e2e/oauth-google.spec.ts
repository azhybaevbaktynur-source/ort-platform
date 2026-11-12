// Item 3 slice C (docs/phases/AUTH_SOCIAL_DESIGN.md 9, 10): "Continue with Google" end to end against the real backend and
// scripts/e2e_oauth_stub.py (Google's authorize, token and JWKS endpoints). The person Google "signs in" is queued with
// the stub's GET /next before the button is pressed. Nothing here is mocked in the browser except where a test says so.
import { spawn, type ChildProcess } from "node:child_process";
import crypto from "node:crypto";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, E2E_DIR, seed, signIn, tr, watchCsp } from "./helpers";
import { hotp, passwordStep, stepNow } from "./mfa";

const API_PORT = Number(process.env.E2E_API_PORT || 8765);
const API = `http://127.0.0.1:${API_PORT}`;
// the same default as scripts/e2e_backend.sh (API port + 2; + 1 is the --mfa-required server)
const STUB = `http://127.0.0.1:${Number(process.env.E2E_OAUTH_STUB_PORT || API_PORT + 2)}`;
const WEB_ORIGIN = `http://127.0.0.1:${Number(process.env.E2E_WEB_PORT || 3765)}`;

const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const alertBox = (page: Page) => page.locator('div[role="alert"]:not([id])'); // not the route announcer
const rand = () => crypto.randomBytes(4).toString("hex");

/** The person Google answers with on the next authorize (stub GET /next). */
async function nextGoogle(person: Record<string, string>): Promise<void> {
  const r = await fetch(`${STUB}/next?${new URLSearchParams(person)}`);
  expect(r.status, "stub /next").toBe(204);
}

async function pressGoogle(page: Page, from = "/ru/login"): Promise<void> {
  watchCsp(page);
  await page.goto(from);
  await page.getByRole("link", { name: t("auth.continueWithGoogle") }).click();
}

async function me(page: Page): Promise<{ id: string; email: string; displayName?: string }> {
  const token = await page.evaluate(() => localStorage.getItem("ort_token"));
  expect(token, "a session token").toBeTruthy();
  const r = await fetch(`${API}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
  expect(r.status).toBe(200);
  return r.json();
}

const signedIn = (page: Page) => page.waitForURL((u) => !/\/(login|oauth-callback)/.test(u.pathname), { timeout: 20_000 });

test("new user: Google, then the age step and consent, lands signed in where they started", async ({ page }) => {
  const email = `e2e-google-new-${rand()}@gmail.test`;
  await nextGoogle({ email, name: "Гугл Новый", sub: `new-${rand()}` });
  await pressGoogle(page, "/ru/login?redirect=%2Fru%2Fabout");
  await expect(page.getByRole("heading", { name: t("auth.oauth.completeTitle") })).toBeVisible();
  expect(await page.evaluate(() => window.location.hash)).toBe(""); // the ticket left the address bar
  await expect(page.getByText(t("auth.oauth.signedInAs", { email }))).toBeVisible();
  await expect(page.getByLabel(t("auth.displayName"))).toHaveValue("Гугл Новый");
  expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBeNull(); // no account before the age step

  await page.getByRole("button", { name: t("privacy.age.18_plus") }).click();
  await page.getByRole("checkbox").check();
  await page.getByLabel(t("auth.displayName")).fill("Гугл Новый К.");
  await page.getByRole("button", { name: t("auth.oauth.completeButton") }).click();
  await expect(page).toHaveURL(/\/ru\/about/);
  const who = await me(page);
  expect(who.email).toBe(email);
  expect(who.displayName).toBe("Гугл Новый К.");
});

test("new user under 14: the privacy page, signed in, never sent to login", async ({ page }) => {
  const email = `e2e-google-child-${rand()}@gmail.test`;
  await nextGoogle({ email, name: "Гугл Ребёнок", sub: `child-${rand()}` });
  await pressGoogle(page);
  await expect(page.getByRole("heading", { name: t("auth.oauth.completeTitle") })).toBeVisible();
  await page.getByRole("button", { name: t("privacy.age.under_14") }).click();
  await page.getByRole("button", { name: t("auth.oauth.completeButton") }).click();
  await expect(page).toHaveURL(/\/ru\/privacy$/);
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/ru\/privacy$/);
  expect((await me(page)).email).toBe(email);
});

test("new user 18+ without a redirect: the choose step (step 3a S4); nothing joined", async ({ page }) => {
  const email = `e2e-google-choose-${rand()}@gmail.test`;
  await nextGoogle({ email, name: "Гугл Выбор", sub: `choose-${rand()}` });
  await pressGoogle(page);
  await page.getByRole("button", { name: t("privacy.age.18_plus") }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: t("auth.oauth.completeButton") }).click();
  await expect(page).toHaveURL(/\/ru\/courses\/choose\?first=1$/);
  await expect(page.getByRole("heading", { level: 1, name: t("choose.title") })).toBeVisible();
  const token = await page.evaluate(() => localStorage.getItem("ort_token"));
  const home = await (await fetch(`${API}/api/v1/me/home`, { headers: { Authorization: `Bearer ${token}` } })).json();
  expect(home.courses).toHaveLength(0);
});

test("existing password user with a verified email: linked, signed in, password still works", async ({ page }) => {
  const user = seed().oauth.linked;
  await nextGoogle({ email: user.email, name: "Someone Else", sub: `linked-${rand()}` });
  await pressGoogle(page);
  await signedIn(page); // no age step: the account exists
  expect((await me(page)).id).toBe(user.profile.id);

  // the password was not touched
  await page.evaluate(() => localStorage.clear());
  await page.goto("/ru/login");
  await passwordStep(page, user.email, user.password);
  await signedIn(page);
  expect((await me(page)).id).toBe(user.profile.id);

  // the admin person page lists both ways in
  await page.evaluate(() => localStorage.clear());
  await signIn(page, seed().admin);
  await page.goto(`/ru/admin/users/${user.profile.id}`);
  const googlePrefix = t("person.signInMethod.googleLinked", { date: "\u0000" }).split("\u0000")[0];
  await expect(page.getByText(t("person.signInMethods"))).toBeVisible();
  await expect(page.getByText(`${t("person.signInMethod.password")} · ${googlePrefix}`)).toBeVisible();
});

test("an unverified Google email is refused with a clear message and nothing is created", async ({ page }) => {
  const email = `e2e-google-unverified-${rand()}@gmail.test`;
  await nextGoogle({ email, email_verified: "false", sub: `unverified-${rand()}` });
  await pressGoogle(page);
  await expect(page).toHaveURL(/\/ru\/login$/); // the code was shown once and removed
  await expect(alertBox(page)).toHaveText(t("auth.errors.oauth_email_unverified"));
  expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBeNull();
  const found = await api(seed().admin, "GET", `/platform/users?q=${encodeURIComponent(email)}`);
  expect(JSON.stringify(found)).not.toContain(email);
});

test("a disabled account is refused and never signed in", async ({ page }) => {
  await nextGoogle({ email: seed().oauth.disabled.email, sub: `disabled-${rand()}` });
  await pressGoogle(page);
  await expect(alertBox(page)).toHaveText(t("auth.errors.account_disabled"));
  expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBeNull();
  await page.getByRole("link", { name: t("auth.oauth.backToLogin") }).click();
  await expect(page).toHaveURL(/\/ru\/login$/);
});

test("a platform admin with two-step login still gets the code step after Google", async ({ page }) => {
  const admin = seed().oauth.admin;
  const setup = await api(admin, "POST", "/platform/security/mfa/setup", { password: admin.password });
  const setupStep = stepNow();
  await api(admin, "POST", "/platform/security/mfa/confirm", { password: admin.password, code: hotp(setup.secret, setupStep) });

  await nextGoogle({ email: admin.email, sub: `admin-${rand()}` });
  await pressGoogle(page, "/ru/login?redirect=%2Fru%2Fadmin");
  await expect(page.getByRole("heading", { name: t("auth.mfa.title") })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("ort_token"))).toBeNull(); // Google alone gives no session

  const loginStep = Math.max(setupStep + 1, stepNow()); // the setup's code is never accepted again
  await page.getByLabel(t("auth.mfa.codeLabel")).fill(hotp(setup.secret, loginStep));
  await page.getByRole("button", { name: t("auth.mfa.button") }).click();
  await expect(page).toHaveURL(/\/ru\/admin$/);
  expect((await me(page)).id).toBe(admin.profile.id);
});

test("pressing Cancel at Google and a wrong state come back as translated refusals", async ({ page }) => {
  await nextGoogle({ deny: "1" });
  await pressGoogle(page);
  await expect(page).toHaveURL(/\/ru\/login$/);
  await expect(alertBox(page)).toHaveText(t("auth.errors.oauth_denied"));

  // a callback whose state is not the one this browser started with: the real start sets the flow cookie, and its
  // redirect is bent straight to our callback with a forged state (a redirect to the stub cannot be routed)
  await page.route(`${API}/api/v1/auth/google/start**`, async (r) => {
    const response = await r.fetch({ maxRedirects: 0 });
    expect(response.status()).toBe(302);
    await r.fulfill({ response, headers: { ...response.headers(), location: `${API}/api/v1/auth/google/callback?code=forged&state=forged` } });
  });
  await pressGoogle(page);
  await expect(page).toHaveURL(/\/ru\/login$/);
  await expect(alertBox(page)).toHaveText(t("auth.errors.oauth_state_mismatch"));
});

test("login CSRF: the attacker's ticket link signs nobody in from another browser", async ({ page, browser, baseURL }) => {
  // the attacker finishes their own Google flow and keeps the callback link instead of using it
  const email = `e2e-google-attacker-${rand()}@gmail.test`;
  await nextGoogle({ email, name: "Attacker", sub: `attacker-${rand()}` });
  let ticket = "";
  await page.route(`${API}/api/v1/auth/oauth/complete`, async (r) => {
    ticket = r.request().postDataJSON().ticket;
    await r.abort();
  });
  await pressGoogle(page);
  await expect.poll(() => ticket).not.toBe("");

  // the victim's browser: signed in to their own account, then opens the link
  const victim = await browser.newContext({ baseURL });
  try {
    const vpage = await victim.newPage();
    watchCsp(vpage);
    const own = seed().oauth.linked;
    await signIn(vpage, own);
    await vpage.goto("/ru/login");
    const before = await vpage.evaluate(() => localStorage.getItem("ort_token"));
    let sent = 0;
    vpage.on("request", (req) => { if (req.url().includes("/auth/oauth/complete")) sent += 1; });
    await vpage.goto(`/ru/oauth-callback#t=${ticket}`);
    await expect(alertBox(vpage)).toHaveText(t("auth.errors.oauth_ticket_invalid"));
    expect(sent).toBe(0); // no bind in this tab: nothing is even sent
    expect(await vpage.evaluate(() => localStorage.getItem("ort_token"))).toBe(before);

    // even with a bind of its own in the tab (it pressed Google once), the server refuses the ticket
    await vpage.goto("/ru/login"); // a new document before the callback page again
    await vpage.evaluate(() => sessionStorage.setItem("ort_oauth_bind", "victims-own-bind-0123456789abcdefghijklmnop"));
    await vpage.goto(`/ru/oauth-callback#t=${ticket}`);
    await vpage.getByRole("button", { name: t("auth.oauth.switchContinue", { email }) }).click();
    await expect(alertBox(vpage)).toHaveText(t("auth.errors.oauth_ticket_invalid"));
    expect(sent).toBe(1);
    expect(await vpage.evaluate(() => localStorage.getItem("ort_token"))).toBe(before);
  } finally {
    await victim.close();
  }
  const found = await api(seed().admin, "GET", `/platform/users?q=${encodeURIComponent(email)}`);
  expect(JSON.stringify(found)).not.toContain(email);
});

test("every oauth_error code is shown in Russian; an unknown one gets the general text", async ({ page }) => {
  watchCsp(page);
  for (const code of ["oauth_not_configured", "oauth_expired", "oauth_state_mismatch", "oauth_denied",
    "oauth_provider_error", "oauth_email_unverified", "oauth_ticket_invalid", "account_disabled"]) {
    await page.goto(`/ru/login?oauth_error=${code}`);
    await expect(alertBox(page)).toHaveText(t(`auth.errors.${code}`));
    await expect(page).toHaveURL(/\/ru\/login$/);
  }
  await page.goto("/ru/login?oauth_error=something_new");
  await expect(alertBox(page)).toHaveText(t("auth.loginError"));
});

test.describe("a server without Google keys", () => {
  const STRICT_PORT = API_PORT + 1; // the --mfa-required server of e2e_backend.sh: same database, no Google keys
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
    throw new Error("the second e2e server did not start");
  });

  test.afterAll(() => {
    server?.kill("SIGTERM");
  });

  test("hides the Google button and the divider", async ({ page }) => {
    expect(await (await fetch(`http://127.0.0.1:${STRICT_PORT}/api/v1/auth/providers`)).json()).toEqual({ google: false, apple: false });
    await page.route(`${API}/**`, async (route) => {
      const url = route.request().url().replace(`127.0.0.1:${API_PORT}`, `127.0.0.1:${STRICT_PORT}`);
      await route.fulfill({ response: await route.fetch({ url }) });
    });
    watchCsp(page);
    for (const p of ["/ru/login", "/ru/register"]) {
      await page.goto(p);
      await expect(page.getByLabel(t("auth.email"))).toBeVisible();
      await page.waitForLoadState("networkidle");
      await expect(page.getByText(t("auth.continueWithGoogle"))).toHaveCount(0);
      await expect(page.getByRole("separator")).toHaveCount(0);
    }
    await page.unrouteAll({ behavior: "ignoreErrors" });
  });
});
