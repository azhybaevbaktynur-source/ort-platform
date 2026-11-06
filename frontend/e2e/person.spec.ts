import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * S4 person page (docs/ROADMAP_EXAM_PREP.md S4): the platform admin finds a student by part of the address, opens the
 * person page, sees the open attempt in the lookup (status and saved-answer count only), changes the student's email;
 * the confirmation link from the new address's email changes it; the student signs in with the new address and opens
 * their own email-change form.
 *
 * Data: `seed.person` (a student with a password and an open ORT attempt with three saved answers).
 * Screens at 375 / 1440 / 1920 (ru) go to $S4_SHOTS (default /tmp/s4_shots).
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.S4_SHOTS || "/tmp/s4_shots";
const WIDTHS = [375, 1440, 1920] as const;
const NEW_EMAIL = "e2e-person-renamed@example.com";

interface PersonSeed { student: SeedUser & { password: string }; attempt_id: string; saved: number; items: number }
const person = () => (seed() as unknown as { person: PersonSeed }).person;

async function shoot(page: Page, name: string, fullPage = true) {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal scroll at ${width}px (${name})`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${width}-ru.png`), fullPage, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function shootElement(page: Page, testId: string, name: string) {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    const card = page.getByTestId(testId).locator("xpath=ancestor::section[1]");
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({ path: path.join(SHOTS, `${name}-${width}-ru.png`), animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The confirmation link the console email provider printed last for this address (backend log of the e2e backend). */
async function emailedLink(email: string): Promise<string> {
  const end = Date.now() + 30_000;
  while (Date.now() < end) {
    const blocks = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8").split("[EMAIL console] To: ").filter((b) => b.startsWith(`${email} `));
    const m = blocks[blocks.length - 1]?.match(/https?:\/\/\S+\/confirm-email\?token=[A-Za-z0-9_-]+/);
    if (m) return m[0];
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`no confirmation link for ${email}`);
}

async function newPage(browser: Browser, user?: SeedUser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  if (user) await signIn(page, user);
  return page;
}

test.describe("person page (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("search -> person page -> attempt lookup -> change email -> confirm link -> sign in with the new address", async ({ browser }) => {
    test.setTimeout(300_000);
    const s = seed();
    const p = person();
    const admin = await newPage(browser, s.admin);
    try {
      // ---- users list: a substring of the address (not its start) finds the student
      await admin.goto(`/${L}/admin/users`);
      await expect(admin.getByRole("heading", { name: t("platformAdmin.users.title"), level: 1 })).toBeVisible();
      await expect(admin.getByLabel(t("platformAdmin.users.filterAccess"))).toBeVisible();
      await admin.getByRole("searchbox").fill("person-stud");
      const link = admin.getByRole("link", { name: p.student.name }).locator("visible=true").first();
      await expect(link).toBeVisible();
      await expect(admin.getByRole("link", { name: s.admin.name })).toHaveCount(0);
      await shoot(admin, "users-list");
      // the filters narrow it: this student has no exam access
      await admin.getByLabel(t("platformAdmin.users.filterAccess")).check();
      await expect(admin.getByText(t("platformAdmin.users.empty"))).toBeVisible();
      await shoot(admin, "users-list-filtered");
      await admin.getByLabel(t("platformAdmin.users.filterAccess")).uncheck();

      // ---- person page: summary, exam access right after it, then the attempt lookup
      await link.click();
      await admin.waitForURL(new RegExp(`/admin/users/${p.student.profile.id}$`));
      await expect(admin.getByText(t("person.lastLogin"))).toBeVisible();
      await expect(admin.getByText(t("privacy.age.18_plus"))).toBeVisible();
      const lookup = admin.getByTestId("attempt-lookup");
      await expect(lookup.getByText(t("person.attempts.statusValue.in_progress"))).toBeVisible();
      await expect(lookup.getByText(t("person.attempts.savedValue", { saved: p.saved, total: p.items }))).toBeVisible();
      await expect(lookup.getByText("ОРТ S3 бесплатный")).toBeVisible();
      const headings = await admin.getByRole("heading", { level: 2 }).allInnerTexts();
      expect(headings.indexOf(t("access.admin.user.title"))).toBeLessThan(headings.indexOf(t("person.attempts.title")));
      await shoot(admin, "person-page");
      await shootElement(admin, "attempt-lookup", "attempt-lookup");

      // ---- change the email (reason required), the link goes to the new address
      await admin.getByRole("button", { name: t("coursePage.moreActions") }).click();
      await admin.getByRole("menuitem", { name: t("person.changeEmail") }).click();
      const dialog = admin.getByRole("alertdialog");
      await expect(dialog).toBeVisible();
      await dialog.getByLabel(t("person.newEmail")).fill(NEW_EMAIL);
      await dialog.getByLabel(t("ui.reason.required")).fill("Ошибка в адресе при регистрации");
      await shoot(admin, "change-email-dialog", false);
      await dialog.getByRole("button", { name: t("person.changeEmailSend") }).click();
      await expect(dialog).toHaveCount(0);
      await expect(admin.getByText(t("person.pendingEmail"))).toBeVisible();
    } finally {
      await admin.context().close();
    }

    // ---- the link, opened signed out: the button confirms it
    // the student never chose a site language, so the email and its link are in Kyrgyz (the default); open it in ru
    const url = (await emailedLink(NEW_EMAIL)).replace(/\/(ky|en)\/confirm-email/, "/ru/confirm-email");
    const anon = await newPage(browser);
    try {
      await anon.goto(url);
      await expect(anon.getByRole("heading", { name: t("auth.confirmEmail.title") })).toBeVisible();
      await anon.getByRole("button", { name: t("auth.confirmEmail.button") }).click();
      await expect(anon.getByRole("heading", { name: t("auth.confirmEmail.successTitle") })).toBeVisible();
      await expect(anon.getByText(NEW_EMAIL)).toBeVisible();
      // the seeded session of the student ended with the change
      const res = await anon.request.get(`${s.api}/api/v1/me/email-change`, { headers: { Authorization: `Bearer ${p.student.token}` } });
      expect(res.status()).toBe(401);

      // ---- sign in with the new address
      await anon.getByRole("button", { name: t("auth.signInButton") }).click();
      await anon.waitForURL(/\/ru\/login/);
      await anon.getByLabel(t("auth.email")).fill(NEW_EMAIL);
      await anon.getByLabel(t("auth.password")).fill(p.student.password);
      await anon.getByRole("button", { name: t("auth.signInButton") }).click();
      await anon.waitForURL((u) => !u.pathname.includes("/login"));

      // ---- the student's own form on the account page
      await anon.goto(`/${L}/privacy`);
      const card = anon.getByTestId("email-card");
      await expect(card.getByText(NEW_EMAIL)).toBeVisible();
      await card.getByRole("button", { name: t("privacy.email.change") }).click();
      await card.getByLabel(t("privacy.email.newEmail")).fill("e2e-person-third@example.com");
      await card.getByLabel(t("privacy.email.password")).fill(p.student.password);
      await shoot(anon, "own-email-form");
      await card.getByRole("button", { name: t("privacy.email.submit") }).click();
      await expect(card.getByText(t("privacy.email.sent", { email: "e2e-person-third@example.com" }))).toBeVisible();
      await card.getByRole("button", { name: t("privacy.email.cancelPending") }).click();
      await expect(card.getByText(t("privacy.email.sent", { email: "e2e-person-third@example.com" }))).toHaveCount(0);
    } finally {
      await anon.context().close();
    }
  });
});
