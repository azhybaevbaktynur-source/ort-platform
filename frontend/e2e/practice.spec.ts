import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser, goToReviewPage } from "./helpers";

/**
 * Phase 10 S3 practice walk (PHASE_10_DESIGN 3): a teacher creates a practice set from a bank in the dialog, a student
 * starts it, answers wrongly, presses "Check" (the key shows, the answer is locked), finishes, and retakes the set.
 *
 * Data: the spec builds its own course through the API (so quiz-editor.spec.ts data stays untouched): the quiz-editor
 * teacher creates a course (ru), a bank with two questions and an invite code; the quiz-editor student joins.
 * Run: same harness as the ORT specs (docs/phases/ORT_BASELINE/README.md "Run").
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SET = "Набор E2E";
const RIGHT = /(^|\s)Верно$/;

async function api(user: SeedUser, method: string, path: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${path}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  expect(r.status, `${method} ${path}`).toBeLessThan(300);
  return r.json();
}

const sc = (stem: string) => ({
  type: "single_choice", language: "ru", stem, explanation: "Потому что так.",
  data: { choices: [{ id: "A", text: "Неверно" }, { id: "B", text: "Верно" }], correct: "B" },
});

async function pageFor(browser: Browser, user: SeedUser, viewport = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

test.describe("practice walk (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("create, start, check, wrong answer shows the key, finish, retake", async ({ browser }) => {
    test.setTimeout(240_000);
    const { teacher, student } = seed().quiz_editor;
    const course = await api(teacher, "POST", "/courses", {
      title: { ru: "Практика E2E" }, languages: ["ru"], default_language: "ru",
    });
    await api(teacher, "POST", `/courses/${course.id}/publish`, {});
    const bank = await api(teacher, "POST", `/courses/${course.id}/banks`, { title: "Банк практики", default_language: "ru" });
    for (const stem of ["Первый вопрос?", "Второй вопрос?"]) {
      await api(teacher, "POST", `/courses/${course.id}/banks/${bank.id}/questions`, sc(stem));
    }
    await api(student, "POST", "/courses/join", { code: course.join_code });

    // ---- teacher: new set from the bank
    const tp = await pageFor(browser, teacher);
    // Phase 10: a general course offers the new question types in the editor's type list and the bank filter; ORT never
    await tp.goto(`/${L}/courses/${course.id}/bank/${bank.id}`);
    await settle(tp);
    for (const ty of ["matching", "fill_blank", "ordering"]) await expect(tp.locator(`option[value="${ty}"]`)).toHaveCount(1); // the filter
    await tp.getByRole("button", { name: t("bank.questions.new") }).click();
    await tp.waitForURL(/\/new/);
    for (const ty of ["matching", "fill_blank", "ordering"]) await expect(tp.locator(`option[value="${ty}"]`)).toHaveCount(1); // the type list
    const ort = await pageFor(browser, seed().admin);
    await ort.goto(`/${L}/courses/${seed().course_id}/bank/${seed().bank_id}`);
    await settle(ort);
    await ort.getByRole("button", { name: t("bank.questions.new") }).click();
    await expect(ort.getByRole("menuitem", { name: new RegExp(`^${t("bank.types.single_choice.name")}`) })).toBeVisible();
    for (const ty of ["matching", "fill_blank", "ordering"]) {
      await expect(ort.getByRole("menuitem", { name: new RegExp(`^${t(`bank.types.${ty}.name`)}`) })).toHaveCount(0);
      await expect(ort.locator(`option[value="${ty}"]`)).toHaveCount(0);
    }
    await ort.context().close();
    await tp.goto(`/${L}/courses/${course.id}/practice`);
    await expect(tp.getByText(t("practice.emptyStaff"))).toBeVisible();
    await tp.getByRole("button", { name: t("practice.new") }).first().click();
    const dlg = tp.getByRole("dialog", { name: t("practice.dialog.createTitle") });
    await dlg.getByLabel(t("practice.dialog.name")).fill(SET);
    await expect(dlg.getByLabel(t("practice.dialog.bank"))).toHaveValue(bank.id);
    await dlg.getByRole("spinbutton", { name: t("practice.dialog.count") }).fill("2");
    await dlg.getByRole("button", { name: t("practice.dialog.create") }).click();
    await expect(tp.getByRole("heading", { name: SET })).toBeVisible();
    await expect(tp.getByText(t("practice.questions", { n: 2 }))).toBeVisible();

    // ---- student: start, answer wrongly, check
    const sp = await pageFor(browser, student);
    await sp.goto(`/${L}/courses/${course.id}/practice`);
    await expect(sp.getByRole("heading", { name: SET })).toBeVisible();
    await expect(sp.getByRole("button", { name: t("practice.new") })).toHaveCount(0);
    await sp.getByRole("button", { name: new RegExp(`^${t("practice.start")}`) }).click();
    await sp.waitForURL(/\/attempts\/[0-9a-f-]{36}/);
    await settle(sp);

    const check = sp.getByRole("button", { name: t("practice.check") });
    await expect(check).toBeDisabled();
    // no timer in practice: the top bar's center says so
    await expect(sp.getByTestId("player-top-bar").getByText(t("player.timer.unlimited"))).toBeVisible();
    await sp.getByRole("radio", { name: /Неверно/ }).click();
    await check.click();
    const fb = sp.getByTestId("practice-feedback");
    await expect(fb).toHaveAttribute("data-correctness", "incorrect");
    await expect(fb).toContainText(t("results.correctAnswer"));
    await expect(fb).toContainText("Верно");
    await expect(fb).toContainText("Потому что так.");
    await expect(sp.getByRole("radio", { name: RIGHT })).toBeDisabled();

    // reload keeps the check
    await sp.reload();
    await expect(sp.getByTestId("practice-feedback")).toHaveAttribute("data-correctness", "incorrect");

    // ---- second question: right answer, then finish
    await sp.getByRole("button", { name: t("player.next") }).click();
    await sp.getByRole("radio", { name: RIGHT }).click();
    await sp.getByRole("button", { name: t("practice.check") }).click();
    await expect(sp.getByTestId("practice-feedback")).toHaveAttribute("data-correctness", /correct|incorrect/);
    await goToReviewPage(sp);
    await sp.getByRole("button", { name: t("player.finishTest") }).first().click();
    await sp.getByRole("dialog").getByRole("button", { name: t("player.submit.confirm") }).click();
    await sp.waitForURL(/\/result/);

    // ---- retake
    await sp.goto(`/${L}/courses/${course.id}/practice`);
    await expect(sp.getByText(t("practice.attempts", { n: 1 }))).toBeVisible();
    await sp.getByRole("button", { name: new RegExp(`^${t("practice.start")}`) }).click();
    await sp.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);
    await expect(sp.getByRole("button", { name: t("practice.check") })).toBeVisible();
  });
});
