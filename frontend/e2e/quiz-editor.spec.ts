import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Phase 7c quiz editor walk (PHASE_7C_DESIGN 11, 10 "Frontend"): a teacher of a general (non-ORT) course writes a quiz
 * in the card editor without opening the Bank tab, reuses shared-bank questions, answers the scope dialog both ways,
 * adds a second section ("Section 1" appears), leaves a draft behind by closing the browser mid-card, publishes with
 * that unfinished draft, a student takes the quiz, the second quiz stays unchanged, and the Bank tab shows the quiz
 * bank, from which one question is moved to the shared bank.
 *
 * Data: `seed_backend.py` (`seed_quiz_editor`, after every ORT row): course "Общий курс E2E" (ru, ky, en) of an
 * approved teacher, shared bank "Общий банк" with two questions, quiz "Квиз Б" using both (published, version 1), and
 * one enrolled student.
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"; build the frontend against the
 * scratch backend first):
 *   rsync -a --exclude node_modules --exclude .next frontend/ /tmp/ort_e2e_fe/ && ln -s "$PWD/frontend/node_modules" /tmp/ort_e2e_fe/node_modules
 *   (cd /tmp/ort_e2e_fe && NEXT_PUBLIC_API_URL=http://127.0.0.1:8765 npx next build)
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/quiz-editor.spec.ts
 * (in a git worktree add E2E_PYTHON=<main repo>/backend/venv/bin/python). The walk is one serial test because every
 * step builds on the previous one.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);

const QUIZ = "Квиз E2E";
const STEM_1 = "Сколько будет 2 + 2?";
const DRAFT_STEM = "Сколько будет 2 + 2? (черновик)";

async function apiGet(user: SeedUser, path: string) {
  const r = await fetch(`${seed().api}/api/v1${path}`, { headers: { Authorization: `Bearer ${user.token}` } });
  expect(r.status, path).toBe(200);
  return r.json();
}

async function teacherPage(browser: Browser): Promise<Page> {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, seed().quiz_editor.teacher);
  return page;
}

/** The collapsed card "Question n" (its open button carries the number, type, points, chips and stem). */
const card = (page: Page, n: number) => page.getByRole("button", { name: t("quizEditor.card.openLabel", { label: t("quizEditor.card.number", { n }) }) });
const stemField = (page: Page) => page.getByLabel(t("bank.editor.stem"));
const answerField = (page: Page, letter: string) => page.getByLabel(t("quizEditor.card.answerLabel", { letter }));

async function openCard(page: Page, n: number) {
  await card(page, n).click();
  await expect(stemField(page)).toBeVisible();
  await settle(page);
}

async function done(page: Page) {
  await page.getByRole("button", { name: t("quizEditor.card.done") }).click();
  await expect(stemField(page)).toHaveCount(0);
  await settle(page);
}

async function newCard(page: Page, type: string, stem: string) {
  await page.getByRole("button", { name: t("quizEditor.card.addQuestion") }).last().click();
  await expect(stemField(page)).toBeVisible();
  if (type !== "single_choice") await page.getByRole("combobox", { name: t("bank.editor.type") }).selectOption(type);
  await stemField(page).fill(stem);
}

test.describe("quiz editor walk (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("write, reuse, scope, sections, draft, publish, student, bank", async ({ browser }) => {
    test.setTimeout(300_000);
    const qe = seed().quiz_editor;
    let page = await teacherPage(browser);

    // ---- a new quiz from the assignments list opens the card editor with an empty quiz
    await page.goto(`/${L}/courses/${qe.course_id}/assessments`);
    await page.getByRole("button", { name: t("assessments.list.create") }).click();
    const create = page.getByRole("dialog", { name: t("assessments.create.title") });
    await create.getByRole("textbox").first().fill(QUIZ);
    for (const other of ["ky", "en"]) {
      const box = create.getByRole("checkbox", { name: t(`courses.languages.${other}`) });
      if (await box.isChecked()) await box.uncheck();
    }
    await create.getByRole("button", { name: t("assessments.create.submit") }).click();
    await page.waitForURL(/\/assessments\/[0-9a-f-]{36}/);
    const aid = /\/assessments\/([0-9a-f-]{36})/.exec(page.url())![1];
    const editUrl = `/${L}/courses/${qe.course_id}/assessments/${aid}/edit`;
    if (!page.url().endsWith("/edit")) await page.goto(editUrl);
    await expect(page.getByText(t("quizEditor.section.emptyQuizTitle"))).toBeVisible();

    // ---- multiple choice: all seven types offered, Enter adds answers, Backspace removes an empty one, mark correct
    await page.getByRole("button", { name: t("quizEditor.card.addQuestion") }).click();
    await expect(stemField(page)).toBeVisible();
    await expect(page.getByRole("combobox", { name: t("bank.editor.type") }).locator("option")).toHaveCount(7);
    await stemField(page).fill(STEM_1);
    await answerField(page, "A").fill("3");
    await answerField(page, "A").press("Enter");
    await expect(answerField(page, "B")).toBeFocused();
    await page.keyboard.type("4");
    await page.keyboard.press("Enter");
    await expect(answerField(page, "C")).toBeFocused();
    await page.keyboard.type("5");
    await page.keyboard.press("Enter");
    await expect(answerField(page, "D")).toBeFocused();
    await page.keyboard.press("Backspace");
    await expect(answerField(page, "D")).toHaveCount(0);
    await expect(answerField(page, "C")).toBeFocused();
    await page.getByRole("radio", { name: t("quizEditor.card.markCorrect", { letter: "B" }) }).check();
    await done(page);
    await expect(card(page, 1)).toContainText(STEM_1);
    await expect(card(page, 1)).toContainText(`${t("quizEditor.card.correctAnswer")} 4`);

    // ---- true/false, numeric, short text, essay
    await newCard(page, "true_false", "Земля круглая.");
    await done(page);
    await newCard(page, "numeric", "Сколько дней в неделе?");
    await page.getByLabel(t("bank.editor.value")).fill("7");
    await done(page);
    await newCard(page, "short_text", "Столица Франции?");
    await page.getByLabel(t("bank.editor.acceptedAnswers")).fill("Париж\nParis");
    await done(page);
    await newCard(page, "essay", "Опишите своё лето.");
    await done(page);
    await expect(card(page, 2)).toContainText(`${t("quizEditor.card.correctAnswer")} ${t("bank.editor.true")}`);
    await expect(card(page, 3)).toContainText(`${t("quizEditor.card.correctAnswer")} 7`);
    await expect(card(page, 4)).toContainText("Париж; Paris");
    await expect(card(page, 5)).not.toContainText(t("quizEditor.card.correctAnswer"));

    // ---- inline validation (UX gate): the error sits under the question text, which gets the focus
    await openCard(page, 4);
    await stemField(page).fill("");
    await page.getByRole("button", { name: t("quizEditor.card.done") }).click();
    await expect(page.getByText(t("bank.editor.errStem"))).toBeVisible();
    await expect(page.getByText(t("quizEditor.card.fixFields"))).toBeVisible();
    await expect(stemField(page)).toBeFocused();
    await expect(stemField(page)).toHaveAttribute("aria-invalid", "true");
    await stemField(page).fill("Столица Франции?");
    await done(page);

    // ---- Find questions: shared banks only (the only one is chosen), two shared questions used by Квиз Б
    await page.getByRole("button", { name: t("quizEditor.add.more") }).click();
    await page.getByRole("menuitem", { name: new RegExp(t("quizEditor.add.find")) }).click();
    const find = page.getByRole("dialog", { name: t("quizEditor.add.find") });
    const bankSelect = find.getByRole("combobox", { name: t("assessments.add.bank") });
    await expect(bankSelect).toHaveValue(qe.bank_id);
    await expect(bankSelect.locator("option")).toHaveCount(2); // placeholder + "Общий банк" (no quiz banks)
    await expect(find.getByRole("checkbox")).toHaveCount(2);
    await find.getByRole("checkbox").nth(0).check();
    await find.getByRole("checkbox").nth(1).check();
    await find.getByRole("button", { name: t("assessments.add.addSelected", { n: 2 }) }).click();
    await expect(find.getByRole("status")).toBeVisible();
    await find.getByRole("button", { name: t("ui.close") }).click();
    await settle(page);
    for (const n of [6, 7]) {
      await expect(card(page, n)).toContainText(t("quizEditor.card.sharedBank"));
      await expect(card(page, n)).toContainText(t("quizEditor.card.usedIn", { n: 2 }));
    }

    // ---- scope dialog: "Change only in this quiz" (card 6), then "Update in all" (card 7)
    const scope = page.getByRole("dialog", { name: t("quizEditor.scope.title") });
    await openCard(page, 6);
    await stemField(page).fill("Столица Кыргызстана (только этот квиз)?");
    await page.getByRole("button", { name: t("quizEditor.card.done") }).click();
    await expect(scope).toBeVisible();
    await expect(scope).toContainText("Квиз Б");
    await scope.getByRole("button", { name: t("quizEditor.scope.this") }).click();
    await expect(stemField(page)).toHaveCount(0);
    await settle(page);
    await expect(card(page, 6)).not.toContainText(t("quizEditor.card.sharedBank"));
    await expect(card(page, 6)).not.toContainText(t("quizEditor.card.usedIn", { n: 2 }));
    await expect(card(page, 6)).toContainText(t("quizEditor.card.quizBank")); // the quiz also has shared-bank cards

    await openCard(page, 7);
    await stemField(page).fill("Сколько будет 3 + 4 (во всех тестах)?");
    await page.getByRole("button", { name: t("quizEditor.card.done") }).click();
    await expect(scope).toBeVisible();
    await scope.getByRole("button", { name: t("quizEditor.scope.all", { n: 2 }) }).click();
    await expect(stemField(page)).toHaveCount(0);
    await settle(page);
    await expect(card(page, 7)).toContainText("во всех тестах");
    await expect(card(page, 7)).toContainText(t("quizEditor.card.sharedBank"));

    // ---- a second section (title only, no instructions): the first block is now "Section 1"; card 7 moves there
    await expect(page.getByText(t("quizEditor.section.firstBecomesSection1"))).toBeVisible();
    await page.getByRole("button", { name: t("assessments.section.add") }).click();
    const secDlg = page.getByRole("dialog", { name: t("assessments.section.addTitle") });
    await secDlg.getByRole("textbox").nth(1).fill("Часть 2");
    await secDlg.getByRole("button", { name: t("lms.common.save") }).click();
    await expect(secDlg).toBeHidden();
    await expect(page.getByRole("heading", { name: t("assessments.section.n", { n: 1 }) })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Часть 2" })).toBeVisible();
    await openCard(page, 7);
    await page.getByRole("button", { name: t("assessments.item.moveTo") }).click();
    await page.getByRole("menuitem", { name: "Часть 2" }).click();
    await expect(stemField(page)).toHaveCount(0); // the card closes first (nothing changed), then moves
    await settle(page);
    await expect(page.locator("section").filter({ has: page.getByRole("heading", { name: "Часть 2" }) }).locator("[data-quiz-item]")).toHaveCount(1);
    await expect(card(page, 7)).toBeInViewport();

    // ---- close the tab right after typing (inside the 800 ms debounce): the pending change is sent with keepalive on
    // the way out (UX gate "no lost keystrokes"), and the draft is back on reopen
    await openCard(page, 1);
    await stemField(page).fill(DRAFT_STEM);
    page.on("dialog", (d) => void d.accept()); // the "leave the page?" prompt while the save is pending
    await page.close({ runBeforeUnload: true });
    await expect.poll(async () => {
      const a = await apiGet(qe.teacher, `/courses/${qe.course_id}/assessments/${aid}`);
      return (a.drafts ?? []).map((d: { payload: { stem: string } }) => d.payload.stem);
    }, { timeout: 10_000 }).toContain(DRAFT_STEM);
    await page.context().close();
    page = await teacherPage(browser);
    await page.goto(editUrl);
    await expect(card(page, 1)).toContainText(t("quizEditor.card.draft"));
    await expect(card(page, 1)).toContainText(STEM_1);
    await openCard(page, 1);
    await expect(stemField(page)).toHaveValue(DRAFT_STEM);
    await page.reload(); // leave it unfinished
    await expect(page.getByText(t("quizEditor.publishBar.unfinishedDrafts_one", { n: 1 }))).toBeVisible();

    // ---- publish with the unfinished draft: warned, confirmed, published
    await page.getByRole("button", { name: t("quizEditor.publishBar.publish") }).click();
    const confirm = page.getByRole("alertdialog", { name: t("quizEditor.publishBar.draftsConfirmTitle") });
    await expect(confirm).toContainText(DRAFT_STEM);
    await confirm.getByRole("button", { name: t("quizEditor.publishBar.publishAnyway") }).click();
    await expect(page.getByText(t("assessments.status.published")).first()).toBeVisible();
    const pub = await apiGet(qe.teacher, `/courses/${qe.course_id}/assessments/${aid}`);
    expect(pub.status).toBe("published");
    expect(pub.drafts).toHaveLength(1);

    // ---- the student takes the quiz: the published version, not the draft
    const sctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const sp = await sctx.newPage();
    await signIn(sp, qe.student);
    await sp.goto(`/${L}/courses/${qe.course_id}/assessments/${aid}`);
    await sp.getByRole("button", { name: t("assessments.lobby.start") }).click();
    await sp.waitForURL(/\/attempts\/[0-9a-f-]{36}/);
    const attemptId = /\/attempts\/([0-9a-f-]{36})/.exec(sp.url())![1];
    await expect(sp.getByText(STEM_1)).toBeVisible();
    await expect(sp.getByText(DRAFT_STEM)).toHaveCount(0);
    const answerB = sp.getByRole("radiogroup", { name: t("player.answers") }).getByRole("radio").nth(1);
    await answerB.click();
    await expect(answerB).toHaveAttribute("aria-checked", "true");
    await sp.getByRole("button", { name: t("player.finishTest") }).click();
    await sp.getByRole("dialog").getByRole("button", { name: t("player.submit.confirm") }).click();
    await expect.poll(async () => (await apiGet(qe.student, `/attempts/${attemptId}`)).status, { timeout: 20_000 }).toMatch(/^(submitted|needs_review|graded)$/); // the essay waits for review
    await sctx.close();

    // ---- the second quiz is unchanged: still version 1, its first question untouched by "only this quiz"
    const b = await apiGet(qe.teacher, `/courses/${qe.course_id}/assessments/${qe.quiz_b}`);
    expect(b.current_version_no).toBe(qe.quiz_b_version);
    const bItems = b.sections.flatMap((s: { items: { question: { id: string; stem_excerpt: string; newer_version_available: boolean } }[] }) => s.items);
    expect(bItems.map((i: { question: { id: string } }) => i.question.id)).toEqual(qe.shared_question_ids);
    expect(bItems[0].question.stem_excerpt).toBe("Столица Кыргызстана?");
    expect(bItems[0].question.newer_version_available).toBe(false);
    expect(bItems[1].question.newer_version_available).toBe(true); // "update in all": reaches students on republish

    // ---- Bank tab: the quiz bank under "Quiz banks"; move one question to the shared bank, it stays in the quiz
    await page.goto(`/${L}/courses/${qe.course_id}/bank`);
    await expect(page.getByText(t("bank.quizBanks.group"))).toBeVisible();
    await page.getByRole("link", { name: QUIZ }).first().click();
    const row = page.locator("li").filter({ hasText: "Земля круглая." }).first();
    await row.getByRole("button", { name: t("bank.moveToBank.title") }).click();
    const mv = page.getByRole("dialog", { name: t("bank.moveToBank.title") });
    await mv.getByRole("combobox").first().selectOption(qe.bank_id);
    await mv.getByRole("radio", { name: new RegExp(t("bank.moveToBank.move")) }).check();
    await mv.getByRole("button", { name: t("bank.moveToBank.submit") }).click();
    await expect(mv).toBeHidden();
    await page.goto(editUrl);
    await expect(card(page, 2)).toContainText("Земля круглая.");
    await expect(card(page, 2)).toContainText(t("quizEditor.card.sharedBank"));
    await page.context().close();
  });
});
