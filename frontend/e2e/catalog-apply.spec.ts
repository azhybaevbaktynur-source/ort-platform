import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Phase 9 S4 walk (PHASE_9_DESIGN 8.1, 11, 12): enrollment form builder → Settings → Enrollment (form mode + catalog)
 * → student catalog search → course landing → apply → teacher inbox → approve with a note → the student is in.
 *
 * Data: `seed_backend.py` (`seed_catalog_apply`, written after every other row): a published private course of an
 * approved teacher without a form, and one applicant in no course. Screens of each step are written to
 * `$E2E_DIR/phase9-s4/` (375 px and 1440 px) for the UX gate; they are not compared against baselines.
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/catalog-apply.spec.ts
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const FIELD_LABEL = "Имя и фамилия";
const ANSWER = "Айдана Асанова";
const NOTE = "Добро пожаловать в группу";

const data = () => seed().catalog_apply;
const shots = path.join(E2E_DIR, "phase9-s4");

async function shot(page: Page, name: string) {
  for (const [vp, size] of [["375", VIEWPORTS.phone], ["1440", VIEWPORTS.desktop]] as const) {
    await page.setViewportSize(size);
    await settle(page, false);
    await page.screenshot({ path: path.join(shots, `${name}-${vp}.png`), fullPage: true });
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

async function as(browser: import("@playwright/test").Browser, user: SeedUser): Promise<Page> {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

test.describe.configure({ mode: "serial" });

test("teacher builds and activates the enrollment form", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  await page.goto(`/ru/courses/${data().course_id}/settings/enrollment-form`);
  await page.getByRole("button", { name: t("enrollmentForm.empty.create") }).click();
  await page.getByRole("button", { name: t("enrollmentForm.addField") }).click();
  await page.getByRole("textbox", { name: t("enrollmentForm.field.label") }).fill(FIELD_LABEL);
  await page.getByRole("button", { name: t("lms.common.save"), exact: true }).click();
  await expect(page.getByText(t("enrollmentForm.saved"))).toBeVisible();
  await shot(page, "builder-edit");

  await page.getByRole("tab", { name: t("enrollmentForm.tabs.preview") }).click();
  await expect(page.getByRole("textbox", { name: FIELD_LABEL })).toBeVisible();
  await shot(page, "builder-preview");
  await page.getByRole("tab", { name: t("enrollmentForm.tabs.edit") }).click();

  await page.getByRole("button", { name: t("enrollmentForm.activate"), exact: true }).click();
  await page.locator("dialog[open]").getByRole("button", { name: t("enrollmentForm.activate"), exact: true }).click();
  await expect(page.getByText(t("enrollmentForm.status.active")).first()).toBeVisible();
  await page.context().close();
});

test("teacher turns on the application mode and the catalog", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  await page.goto(`/ru/courses/${data().course_id}/settings`);
  await expect(page.getByText(t("enrollmentForm.settings.active", { n: 1 }))).toBeVisible();
  await page.locator("#s-mode").selectOption("form_review");
  await page.getByRole("switch", { name: t("enrollmentForm.settings.catalog") }).click();
  const form = page.locator("form", { has: page.locator("#s-mode") });
  await form.getByRole("button", { name: t("lms.common.save") }).click();
  await expect(form.getByText(t("courses.settings.saved"))).toBeVisible();
  await shot(page, "settings-enrollment");
  await page.context().close();
});

test("student finds the course, opens the landing and applies", async ({ browser }) => {
  const page = await as(browser, data().student);
  await page.goto("/ru/courses/catalog");
  await page.locator("#catalog-q").fill("анкетой");
  const card = page.locator("li", { has: page.getByRole("link", { name: "Курс с анкетой E2E" }) });
  await expect(card).toBeVisible();
  await expect(page.getByRole("link", { name: /ОРТ/ })).toHaveCount(0); // the search (debounced) hides the ORT courses
  await expect(card.getByText(t("catalog.modes.form_review"))).toBeVisible();
  await shot(page, "catalog-search");

  await card.getByRole("link", { name: "Курс с анкетой E2E" }).click();
  await expect(page.getByRole("heading", { name: t("catalog.landing.howToJoin") })).toBeVisible();
  await shot(page, "landing-form");

  await page.getByRole("link", { name: t("catalog.apply") }).click();
  await expect(page.getByText(t("applications.privacyNote"))).toBeVisible();
  await page.getByRole("button", { name: t("applications.apply.submit") }).click();
  await expect(page.getByText(t("applications.answerErrors.required"))).toBeVisible(); // required, client-side
  await shot(page, "apply-errors");
  await page.getByRole("textbox", { name: FIELD_LABEL }).fill(ANSWER);
  await page.getByRole("button", { name: t("applications.apply.submit") }).click();
  await expect(page.getByRole("heading", { name: t("applications.apply.sentTitle") })).toBeVisible();
  await shot(page, "apply-sent");

  await page.goto(`/ru/courses/catalog/${data().course_id}`);
  await expect(page.getByText(t("applications.studentStatus.pending")).first()).toBeVisible();
  await shot(page, "landing-pending");
  await page.context().close();
});

test("teacher approves the application with a note", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  await page.goto(`/ru/courses/${data().course_id}/people`);
  await page.getByRole("tab", { name: t("studentInvite.tabs.applications") }).click();
  await page.getByRole("button", { name: new RegExp(t("applications.inbox.review")) }).click();
  const dialog = page.locator("dialog[open]");
  await expect(dialog.getByText(ANSWER)).toBeVisible();
  await dialog.getByRole("textbox", { name: new RegExp(t("applications.panel.note")) }).fill(NOTE);
  await shot(page, "inbox-panel");
  await dialog.getByRole("button", { name: t("applications.panel.approve") }).click();
  await expect(dialog.getByText(t("applications.status.approved"))).toBeVisible();
  await dialog.getByRole("button", { name: tr(L, "ui.close") }).first().click();
  await shot(page, "inbox-list");
  await page.context().close();
});

test("the student is in the course and sees it from the landing", async ({ browser }) => {
  const page = await as(browser, data().student);
  await page.goto(`/ru/courses/catalog/${data().course_id}`);
  await expect(page.getByRole("link", { name: t("catalog.landing.openCourse") })).toBeVisible();
  await page.context().close();
});
