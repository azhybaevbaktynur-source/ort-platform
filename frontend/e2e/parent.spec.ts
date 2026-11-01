import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, uxShots, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Phase 11 S2 walk (PHASE_11_DESIGN 4, 10, 11): a parent in a real browser.
 *
 *  1. A student of 14 to 17 gets a code; a parent enters it; the parent sees grades, due dates and announcements of the
 *     student, and never the feedback or the student's answer.
 *  2. A student under 14 is closed until the parent consents; the parent sees only the consent screen, consents, and
 *     both go on. Removing the link closes the child again.
 *  3. The older student removes the parent: the link page says it is gone.
 *
 * The student's side (`/privacy`) is Phase 11 S3, so the student acts through the API here.
 * Data: the spec registers its own people through the API and builds on the modules course (`seed_modules`).
 * UX-gate screens go to `$E2E_DIR/phase11-s2/` (375 px and 1440 px, ru + ky + en).
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/parent.spec.ts
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = "phase11-s2";
const FEEDBACK = "ОТЗЫВ-УЧИТЕЛЯ";
const ANSWER = "ОТВЕТ-УЧЕНИКА";

async function call(user: SeedUser | null, method: string, apiPath: string, body?: unknown): Promise<Response> {
  return fetch(`${seed().api}/api/v1${apiPath}`, {
    method,
    headers: { ...(user ? { Authorization: `Bearer ${user.token}` } : {}), "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function api(user: SeedUser | null, method: string, apiPath: string, body?: unknown) {
  const r = await call(user, method, apiPath, body);
  expect(r.status, `${method} ${apiPath}`).toBeLessThan(300);
  return r.status === 204 ? null : r.json();
}

/** The code the console email provider printed last for this address (backend log of the e2e backend). */
async function emailedCode(email: string): Promise<string> {
  for (let i = 0; i < 100; i += 1) {
    const log = fs.readFileSync(path.join(E2E_DIR, "backend.log"), "utf-8");
    const at = log.lastIndexOf(`[EMAIL console] To: ${email} `);
    const body = at >= 0 ? log.slice(log.indexOf("\n", at)) : ""; // not the "To:" line: the address holds digits too
    const code = body.match(/\b(\d{6})\b/);
    if (code) return code[1];
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`no code for ${email}`);
}

async function person(name: string, ageBand: string): Promise<SeedUser> {
  const email = `e2e-parent-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  const password = `pw-${Math.random().toString(36).slice(2)}-${Date.now()}`;
  const policies = (await api(null, "GET", "/privacy/policies/current")) as { id: string; kind: string }[];
  await api(null, "POST", "/auth/register", {
    email, password, displayName: name, lang: "ru", ageBand,
    policyVersionIds: ageBand === "under_14" ? [] : policies.filter((p) => p.kind !== "guardian_consent").map((p) => p.id),
  });
  const out = await api(null, "POST", "/auth/verify-email", { email, password, code: await emailedCode(email) });
  const user = { email, name, token: out.access_token, profile: { id: "" } } as SeedUser;
  user.profile = await api(user, "GET", "/auth/me");
  return user;
}

async function pageFor(browser: Browser, user: SeedUser, viewport: { width: number; height: number } = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function enterCode(page: Page, code: string) {
  await page.goto(`/${L}/parent`);
  await settle(page);
  await page.getByLabel(t("guardian.code.label")).fill(code);
  await page.getByRole("button", { name: t("guardian.code.submit") }).click();
  await page.waitForURL(/\/parent\/[0-9a-f-]{36}$/);
  await settle(page);
}

test.describe("parent walk (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("a parent sees grades, due dates and announcements, and no answers", async ({ browser }) => {
    test.setTimeout(240_000);
    const { course_id: cid, join_code: joinCode, teacher } = seed().modules;
    const student = await person("Айдана Ученица", "14_17");
    const parent = await person("Мама Айданы", "18_plus");
    await api(student, "POST", "/courses/join", { code: joinCode });

    const graded = await api(teacher, "POST", `/courses/${cid}/assignments`, {
      title: { ru: "Сочинение E2E" }, kind: "text", points_possible: "10",
    });
    await api(teacher, "PATCH", `/courses/${cid}/assignments/${graded.id}`, { published: true });
    const open = await api(teacher, "POST", `/courses/${cid}/assignments`, {
      title: { ru: "Эссе на завтра E2E" }, kind: "text", points_possible: "10", due_at: new Date(Date.now() + 86_400_000).toISOString(),
    });
    await api(teacher, "PATCH", `/courses/${cid}/assignments/${open.id}`, { published: true });
    await api(student, "POST", `/courses/${cid}/assignments/${graded.id}/submissions`, { body_text: ANSWER });
    const roster = await api(teacher, "GET", `/courses/${cid}/assignments/${graded.id}/submissions`);
    const row = roster.rows.find((r: { user_id: string }) => r.user_id === student.profile.id);
    await api(teacher, "PUT", `/courses/${cid}/assignments/${graded.id}/grades/${row.enrollment_id}`, { points: "8", feedback_text: FEEDBACK });
    await api(teacher, "POST", `/courses/${cid}/assignments/${graded.id}/grades/release`, {});
    await api(teacher, "POST", `/courses/${cid}/announcements`, { title: "Поездка E2E", body_md: "Едем в музей.", publish: true });

    const code = (await api(student, "POST", "/me/guardians/pairing-code")).code;
    const page = await pageFor(browser, parent);
    await enterCode(page, code);
    await expect(page.getByRole("heading", { level: 1, name: student.name })).toBeVisible();

    // grades: the number, never the feedback or the answer
    await expect(page.getByText("Сочинение E2E")).toBeVisible();
    await expect(page.getByText(t("guardian.grades.points", { points: 8, possible: 10 }))).toBeVisible();
    await expect(page.getByText(t("guardian.state.graded"))).toBeVisible();
    await expect(page.locator("body")).not.toContainText(FEEDBACK);
    await expect(page.locator("body")).not.toContainText(ANSWER);
    await uxShots(page, SHOTS, "grades", ["ru", "ky", "en"]);

    await page.getByRole("tab", { name: t("guardian.tabs.due") }).click();
    await expect(page.getByText("Эссе на завтра E2E")).toBeVisible();
    await uxShots(page, SHOTS, "due", ["ru"]);

    await page.getByRole("tab", { name: t("guardian.tabs.announcements") }).click();
    await expect(page.getByText("Поездка E2E")).toBeVisible();
    await expect(page.getByText("Едем в музей.")).toBeVisible();
    await uxShots(page, SHOTS, "announcements", ["ru"]);

    // the course itself is closed
    expect([403, 404]).toContain((await call(parent, "GET", `/courses/${cid}/grades/mine`)).status);
    expect([403, 404]).toContain((await call(parent, "GET", `/courses/${cid}/assignments/${graded.id}`)).status);

    // the list
    await page.goto(`/${L}/parent`);
    await settle(page);
    await expect(page.getByRole("link", { name: student.name })).toBeVisible();
    await uxShots(page, SHOTS, "home", ["ru", "ky", "en"]);

    // the student removes the parent
    const links = await api(student, "GET", "/me/guardians");
    expect(links).toHaveLength(1);
    await api(student, "DELETE", `/me/guardians/${links[0].id}`);
    await page.reload();
    await settle(page);
    await expect(page.getByText(t("guardian.noStudents"))).toBeVisible();
    await page.context().close();
  });

  test("a child under 14 waits for the parent's consent", async ({ browser }) => {
    test.setTimeout(180_000);
    const kid = await person("Бек Младший", "under_14");
    const parent = await person("Папа Бека", "18_plus");
    expect((await call(kid, "GET", "/me/home")).status).toBe(403);
    const code = (await api(kid, "POST", "/me/guardians/pairing-code")).code;

    const page = await pageFor(browser, parent, VIEWPORTS.phone);
    await enterCode(page, code);
    await expect(page.getByRole("button", { name: t("guardian.consent.confirm") })).toBeVisible();
    await expect(page.getByText(t("guardian.consent.draft"))).toBeVisible();
    await expect(page.getByRole("tab", { name: t("guardian.tabs.grades") })).toHaveCount(0);
    await uxShots(page, SHOTS, "consent", ["ru", "ky", "en"]);

    await page.getByRole("button", { name: t("guardian.consent.confirm") }).click();
    await expect(page.getByRole("tab", { name: t("guardian.tabs.grades") })).toBeVisible();
    expect((await call(kid, "GET", "/me/home")).status).toBe(200);
    await uxShots(page, SHOTS, "consent-held", ["ru"]);

    // an only consent holder stays until the parent ends it
    const links = await api(kid, "GET", "/me/guardians");
    expect(links[0].holds_consent).toBe(true);
    expect((await call(kid, "DELETE", `/me/guardians/${links[0].id}`)).status).toBe(409);

    await page.getByRole("button", { name: t("guardian.remove.action") }).first().click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await uxShots(page, SHOTS, "remove-dialog", ["ru"]);
    await page.getByRole("alertdialog").getByRole("button", { name: t("guardian.remove.action") }).click();
    await page.waitForURL(/\/parent$/);
    await settle(page);
    await expect(page.getByText(t("guardian.noStudents"))).toBeVisible();
    expect((await call(kid, "GET", "/me/home")).status).toBe(403);
    await page.context().close();
  });

  test("a teen cannot be a parent", async ({ browser }) => {
    test.setTimeout(120_000);
    const teen = await person("Подросток", "14_17");
    const page = await pageFor(browser, teen, VIEWPORTS.phone);
    await page.goto(`/${L}/parent`);
    await settle(page);
    await expect(page.getByText(t("guardian.adultOnly.title"))).toBeVisible();
    await uxShots(page, SHOTS, "adult-only", ["ru"]);
    await page.context().close();
  });
});
