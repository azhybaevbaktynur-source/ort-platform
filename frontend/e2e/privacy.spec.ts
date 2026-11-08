import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, uxShots, VIEWPORTS, type SeedUser } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * Phase 11 S3 (PHASE_11_DESIGN 3.2, 3.3, 11): sign-up by age band, the consent gate, the policies, My data and the
 * admin's request table, in a real browser against the scratch backend.
 *
 * Data: `seed_backend.py` (`seed_privacy`). The pairing code and the parents list belong to S2 (`parent.spec.ts` walks
 * them for real); here `/me/guardians*` is answered by the test, so these screens are checked on their own.
 * Screens go to `$E2E_DIR/phase11-s3/` (375 px and 1440 px); they are not compared against baselines.
 *
 * Run: cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/privacy.spec.ts
 */

type Lang = "ru" | "ky" | "en";
interface PrivacySeed {
  legacy: SeedUser;
  requester: SeedUser;
  gated: SeedUser & { attempt_id: string };
}
const data = () => (seed() as unknown as { privacy: PrivacySeed }).privacy;
const SHOTS = "phase11-s3";
const PASSWORD = `e2e-${Math.random().toString(36).slice(2)}-pass`;

async function fresh(browser: Browser, viewport: { width: number; height: number } = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light", acceptDownloads: true });
  return ctx.newPage();
}

async function as(browser: Browser, user: SeedUser): Promise<Page> {
  const page = await fresh(browser);
  await signIn(page, user);
  return page;
}

async function code(email: string): Promise<string> {
  const end = Date.now() + 30_000;
  while (Date.now() < end) {
    const log = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8");
    const blocks = log.split("[EMAIL console] To: ").filter((b) => b.startsWith(`${email} `));
    const m = blocks[blocks.length - 1]?.match(/\b(\d{6})\b/);
    if (m) return m[1];
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`no code for ${email}`);
}

async function fillForm(page: Page, lang: Lang, email: string): Promise<void> {
  await page.getByLabel(tr(lang, "auth.displayName")).fill("Сынак Тест");
  await page.getByLabel(tr(lang, "auth.email")).fill(email);
  await page.getByLabel(tr(lang, "auth.password")).fill(PASSWORD);
}

async function verify(page: Page, lang: Lang, email: string): Promise<void> {
  await expect(page.getByRole("heading", { name: tr(lang, "auth.verify.title") })).toBeVisible();
  await page.getByLabel(tr(lang, "auth.verify.codeLabel")).fill(await code(email));
  await page.getByRole("button", { name: tr(lang, "auth.verify.button") }).click();
}

async function apiAs(page: Page, method: string, p: string) {
  return page.evaluate(async ([api, m, url]) => {
    const r = await fetch(`${api}/api/v1${url}`, { method: m, headers: { Authorization: `Bearer ${localStorage.getItem("ort_token")}` } });
    return { status: r.status, body: await r.json().catch(() => null) };
  }, [seed().api, method, p] as const);
}

async function noSideScroll(page: Page): Promise<void> {
  for (const size of [VIEWPORTS.phone, VIEWPORTS.desktop]) {
    await page.setViewportSize(size);
    await settle(page);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(over, `side scroll at ${size.width}`).toBeLessThanOrEqual(0);
  }
}

test.describe.configure({ mode: "serial" });

test("sign-up 18+: age first, policies required, then the home page without a banner", async ({ browser }) => {
  const page = await fresh(browser, VIEWPORTS.phone);
  const email = "e2e-signup-adult@example.com";
  await page.goto("/ru/register");
  await expect(page.getByLabel(tr("ru", "auth.email"))).toBeVisible(); // the form is first (AUTH_SOCIAL_DESIGN 8.3)
  await expect(page.getByText(tr("ru", "auth.ageRowLabel"))).toBeVisible();
  await uxShots(page, SHOTS, "register-age", ["ru", "ky", "en"]);
  await page.setViewportSize(VIEWPORTS.phone);

  await page.getByRole("button", { name: tr("ru", "privacy.age.18_plus") }).click();
  await fillForm(page, "ru", email);
  const box = page.getByRole("checkbox");
  await expect(box).not.toBeChecked();
  await page.getByRole("button", { name: tr("ru", "auth.signUpButton") }).click();
  await expect(page.getByRole("heading", { name: tr("ru", "auth.verify.title") })).toHaveCount(0); // the box is required
  await box.check();
  await uxShots(page, SHOTS, "register-form", ["ru"], async (p) => {
    await p.getByRole("button", { name: tr("ru", "privacy.age.18_plus") }).click();
    await fillForm(p, "ru", email);
    await p.getByRole("checkbox").check();
  });
  await page.getByRole("button", { name: tr("ru", "auth.signUpButton") }).click();
  await verify(page, "ru", email);
  await expect(page).toHaveURL(/\/ru\/courses/);
  await settle(page);
  await expect(page.getByRole("link", { name: tr("ru", "privacy.banner.age") })).toHaveCount(0);
  const state = await apiAs(page, "GET", "/me/privacy");
  expect(state.body).toMatchObject({ age_band: "18_plus", consent_state: "ok", needs: [] });
  await page.context().close();
});

test("sign-up 14-17 in Kyrgyz", async ({ browser }) => {
  const page = await fresh(browser, VIEWPORTS.phone);
  const email = "e2e-signup-teen@example.com";
  await page.goto("/ky/register");
  await page.getByRole("button", { name: tr("ky", "privacy.age.14_17") }).click();
  await fillForm(page, "ky", email);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: tr("ky", "auth.signUpButton") }).click();
  await verify(page, "ky", email);
  await expect(page).toHaveURL(/\/ky\/courses/);
  expect((await apiAs(page, "GET", "/me/privacy")).body).toMatchObject({ age_band: "14_17", consent_state: "ok" });
  await page.context().close();
});

test("sign-up under 14: no policy box; only the code screen works until a parent consents", async ({ browser }) => {
  const page = await fresh(browser, VIEWPORTS.phone);
  const email = "e2e-signup-child@example.com";
  await page.route("**/me/guardians/pairing-code", (r) => r.fulfill({ status: 201, json: { code: "7K2M9QXA", expires_at: "2099-01-01T12:00:00Z" } }));
  await page.route("**/me/guardians", (r) => r.fulfill({ json: [] }));
  await page.goto("/en/register");
  await page.getByRole("button", { name: tr("en", "privacy.age.under_14") }).click();
  await fillForm(page, "en", email);
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await page.getByRole("button", { name: tr("en", "auth.signUpButton") }).click();
  await verify(page, "en", email);

  await expect(page).toHaveURL(/\/en\/privacy/);
  await expect(page.getByRole("heading", { name: tr("en", "privacy.code.title") })).toBeVisible();
  await page.getByRole("button", { name: tr("en", "privacy.code.get") }).click();
  await expect(page.getByTestId("pairing-code")).toHaveText("7K2M9QXA");
  await expect(page.getByRole("button", { name: tr("en", "privacy.data.download") })).toHaveCount(0);
  await uxShots(page, SHOTS, "privacy-under14", ["en"], async (p) => {
    await p.getByRole("button", { name: tr("en", "privacy.code.get") }).click();
  });
  await noSideScroll(page);

  // anywhere else leads back here
  await page.goto("/en/courses");
  await expect(page).toHaveURL(/\/en\/privacy/);
  await expect(page.getByRole("heading", { name: tr("en", "privacy.code.title") })).toBeVisible();
  expect((await apiAs(page, "POST", "/courses/join")).status).toBe(403);
  await page.context().close();
});

test("I'm a parent: an adult's form, then the parent page", async ({ browser }) => {
  const page = await fresh(browser, VIEWPORTS.phone);
  const email = "e2e-signup-parent@example.com";
  await page.goto("/ru/register");
  await page.getByRole("button", { name: tr("ru", "auth.parentCta") }).click();
  await fillForm(page, "ru", email);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: tr("ru", "auth.signUpButton") }).click();
  await verify(page, "ru", email);
  await expect(page).toHaveURL(/\/ru\/parent/);
  expect((await apiAs(page, "GET", "/me/privacy")).body).toMatchObject({ age_band: "18_plus", consent_state: "ok" });
  await page.context().close();
});

test("policies are public, in three languages, with the draft badge", async ({ browser }) => {
  const page = await fresh(browser);
  for (const lang of ["ru", "ky", "en"] as const) {
    for (const kind of ["privacy", "terms", "guardian_consent"]) {
      await page.goto(`/${lang}/policies/${kind}`);
      await expect(page.getByText(tr(lang, "privacy.draftBadge"))).toBeVisible();
      await expect(page.getByRole("heading", { level: 1, name: tr(lang, `privacy.policies.${kind}`) })).toBeVisible();
    }
  }
  await page.goto("/ru/policies/privacy");
  await expect(page.getByText(tr("ru", "privacy.draftBadge"))).toBeVisible();
  await uxShots(page, SHOTS, "policy", ["ru", "ky", "en"]);
  await noSideScroll(page);
  await page.goto("/ru/policies/nope");
  await expect(page.getByText(tr("ru", "privacy.policies.notFound"))).toBeVisible();
  await page.context().close();
});

test("existing account: one banner on the home page, nothing restricted, age confirmed once", async ({ browser }) => {
  const page = await as(browser, data().legacy);
  await page.goto("/ru/courses");
  const banner = page.getByRole("link", { name: tr("ru", "privacy.banner.age") });
  await expect(banner).toBeVisible();
  await uxShots(page, SHOTS, "home-banner", ["ru"]);
  expect((await apiAs(page, "GET", "/courses")).status).toBe(200);
  await banner.click();
  await expect(page).toHaveURL(/\/ru\/privacy/);
  await page.getByRole("button", { name: tr("ru", "privacy.age.18_plus") }).click();
  const confirm = page.getByRole("button", { name: tr("ru", "privacy.confirm") });
  await expect(confirm).toBeDisabled();
  await uxShots(page, SHOTS, "privacy-legacy", ["ru"], async (p) => {
    await p.getByRole("button", { name: tr("ru", "privacy.age.18_plus") }).click();
  });
  await page.getByRole("checkbox").check();
  await confirm.click();
  await expect(page.getByText(tr("ru", "privacy.age.18_plus"))).toBeVisible();
  await expect(page.getByRole("button", { name: tr("ru", "privacy.confirm") })).toHaveCount(0);
  await page.goto("/ru/courses");
  await settle(page);
  await expect(page.getByRole("link", { name: tr("ru", "privacy.banner.age") })).toHaveCount(0);
  await page.context().close();
});

test("gate: an open ORT attempt goes on, everything else leads to the code screen", async ({ browser }) => {
  const d = data();
  const page = await as(browser, d.gated);
  await page.goto(`/ru/courses/${seed().course_id}/attempts/${d.gated.attempt_id}`);
  const exam = new OrtExam(page, "ru");
  await expect(exam.timer()).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/attempts/${d.gated.attempt_id}$`));
  const saved = page.waitForResponse((r) => r.url().endsWith(`/attempts/${d.gated.attempt_id}/answers`) && r.request().method() === "PUT");
  await exam.question().getByRole("radio").first().click();
  expect((await saved).status()).toBe(200);
  await expect(page).toHaveURL(new RegExp(`/attempts/${d.gated.attempt_id}$`));

  await page.goto("/ru/courses");
  await expect(page).toHaveURL(/\/ru\/privacy/);
  await page.context().close();
});

test("my data: download, delete request with password, admin runs and rejects", async ({ browser }) => {
  const email = "e2e-signup-delete@example.com";
  const page = await fresh(browser);
  await page.route("**/me/guardians", (r) => r.fulfill({ json: [{ id: "g1", guardian_name: "Айгүл Родитель", created_at: "2026-11-01T10:00:00Z", holds_consent: false }] }));
  await page.route("**/me/guardians/pairing-code", (r) => r.fulfill({ status: 201, json: { code: "7K2M9QXA", expires_at: "2099-01-01T12:00:00Z" } }));
  await page.goto("/ru/register");
  await page.getByRole("button", { name: tr("ru", "privacy.age.14_17") }).click();
  await fillForm(page, "ru", email);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: tr("ru", "auth.signUpButton") }).click();
  await verify(page, "ru", email);
  await expect(page).toHaveURL(/\/ru\/courses/);

  await page.goto("/ru/privacy");
  await expect(page.getByText("Айгүл Родитель")).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: tr("ru", "privacy.data.download") }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("my-data.json");
  const exported = JSON.parse(fs.readFileSync(await download.path(), "utf-8"));
  expect(JSON.stringify(exported)).toContain(email);
  await expect(page.getByText(tr("ru", "privacy.requests.status.completed"))).toBeVisible();

  const openDelete = async (p: Page) => {
    await p.getByRole("button", { name: tr("ru", "privacy.data.delete") }).click();
    await expect(p.locator("dialog[open]")).toBeVisible();
  };
  await openDelete(page);
  const dialog = page.locator("dialog[open]");
  await dialog.getByLabel(tr("ru", "auth.password")).fill("wrong-password");
  await dialog.getByRole("button", { name: tr("ru", "privacy.data.delete") }).click();
  await expect(dialog.getByText(tr("ru", "privacy.errors.password_incorrect"))).toBeVisible();
  await dialog.getByLabel(tr("ru", "auth.password")).fill(PASSWORD);
  await dialog.getByRole("button", { name: tr("ru", "privacy.data.delete") }).click();
  await expect(page.locator("dialog[open]")).toHaveCount(0);
  await expect(page.getByText(tr("ru", "privacy.requests.status.pending"))).toBeVisible();

  await page.getByRole("button", { name: tr("ru", "privacy.requests.cancel") }).click();
  await expect(page.getByText(tr("ru", "privacy.requests.status.cancelled"))).toBeVisible();
  await openDelete(page);
  await page.locator("dialog[open]").getByLabel(tr("ru", "auth.password")).fill(PASSWORD);
  await page.locator("dialog[open]").getByRole("button", { name: tr("ru", "privacy.data.delete") }).click();
  await expect(page.getByText(tr("ru", "privacy.requests.status.pending"))).toBeVisible();
  await uxShots(page, SHOTS, "privacy-page", ["ru", "ky", "en"]);
  await noSideScroll(page);

  // admin: oldest due date first; a delete request has Run, an export only Reject
  const admin = await as(browser, seed().admin);
  await admin.goto("/ru/admin/privacy");
  const row = (e: string) => admin.getByRole("row", { name: new RegExp(e.replace(/[.+]/g, "\\$&")) });
  await expect(row(email)).toBeVisible();
  await expect(row(data().requester.email).getByRole("button", { name: tr("ru", "privacy.admin.run") })).toHaveCount(0);
  await uxShots(admin, SHOTS, "admin-requests", ["ru"]);
  await noSideScroll(admin);

  await row(data().requester.email).getByRole("button", { name: tr("ru", "privacy.admin.reject") }).click();
  const rejecting = admin.locator("dialog[open]");
  await rejecting.getByLabel(tr("ru", "privacy.admin.rejectReason")).selectOption("duplicate");
  await rejecting.getByRole("button", { name: tr("ru", "privacy.admin.reject") }).click();
  await expect(row(data().requester.email)).toHaveCount(0);

  await row(email).getByRole("button", { name: tr("ru", "privacy.admin.run") }).click();
  const running = admin.locator("dialog[open]");
  await expect(running.getByText(email)).toBeVisible();
  await running.getByRole("button", { name: tr("ru", "privacy.admin.run") }).click();
  await expect(row(email)).toHaveCount(0);
  await admin.getByRole("tab", { name: tr("ru", "privacy.admin.filters.all") }).click();
  await expect(admin.getByRole("cell", { name: tr("ru", "privacy.requests.status.rejected") }).first()).toBeVisible();
  await admin.context().close();

  // the account is gone
  const login = await page.evaluate(async ([api, e, pw]) => {
    const r = await fetch(`${api}/api/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: e, password: pw }) });
    return r.status;
  }, [seed().api, email, PASSWORD] as const);
  expect(login).toBeGreaterThanOrEqual(400);
  await page.context().close();
});
