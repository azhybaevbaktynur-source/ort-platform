import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import { goToReviewPage, questionMapToggle, sectionCounts, seed, settle, signIn, tr, VIEWPORTS, type Lang, type SeedUser } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * The exam player in Bluebook style (docs/phases/BLUEBOOK_PLAYER.md): the review page lists states and jumps; a closed
 * forward-only section cannot be reached again; a hidden timer keeps counting, comes back in the last five minutes and
 * time-up still submits; Esc closes the popups and returns focus; hotkeys work and are ignored with a popup open or on
 * the review page; the reading split screen (divider, independent panes, stacked at 375 px).
 *
 * PLAYER_SCREENS_DIR=<dir> also writes screenshots for a look at 375, 1440 and 1920 px (not compared).
 */

const L: Lang = "ru";
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SCREENS = process.env.PLAYER_SCREENS_DIR ? path.resolve(process.env.PLAYER_SCREENS_DIR) : null;

interface ItemState { position: number; section_pos: number; response: Record<string, unknown> | null; flagged: boolean }
const sc = () => seed().scrolling;

async function api(user: SeedUser, p: string) {
  const r = await fetch(`${seed().api}/api/v1${p}`, { headers: { Authorization: `Bearer ${user.token}` } });
  expect(r.status, p).toBe(200);
  return r.json();
}

async function studentPage(browser: Browser, user: SeedUser, extra: BrowserContextOptions = {}): Promise<Page> {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light", ...extra });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function startQuiz(page: Page, user: SeedUser, quizId: string) {
  await page.goto(`/${L}/courses/${sc().course_id}/assessments/${quizId}`);
  await page.getByRole("button", { name: t("assessments.lobby.start") }).click();
  await page.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);
  const attemptId = /\/attempts\/([0-9a-f-]{36})/.exec(page.url())![1];
  const state = await api(user, `/attempts/${attemptId}`);
  return { attemptId, items: [...(state.items as ItemState[])].sort((a, b) => a.position - b.position) };
}

const bar = (page: Page) => page.getByTestId("player-bottom-bar");
const top = (page: Page) => page.getByTestId("player-top-bar");
const review = (page: Page) => page.getByRole("region", { name: t("player.review.title") });
const map = (page: Page) => page.getByRole("dialog", { name: t("player.palette.title") });
const heading = (page: Page, n: number, total: number) => page.getByRole("heading", { level: 2, name: t("player.questionOf", { n, total }) });
const radios = (page: Page) => page.getByRole("radiogroup", { name: t("player.answers") }).getByRole("radio");
const entryName = (n: number, s: { answered?: boolean; flagged?: boolean } = {}) =>
  `${t("player.question")} ${n}${s.answered ? `, ${t("player.palette.answered")}` : ""}${s.flagged ? `, ${t("player.palette.flagged")}` : ""}`;

test.describe("Bluebook exam player", () => {
  test("review page lists states and jumps; a closed forward-only section cannot be reached again", async ({ browser }) => {
    const page = await studentPage(browser, seed().students["bb-review-ru"]);
    const exam = new OrtExam(page, L);
    const counts = sectionCounts();
    await exam.openLobby();
    await exam.start();
    await exam.assertSection(1);

    // the finish action is not on the question screen; "Back" only where it can go
    await expect(page.getByRole("button", { name: t("player.finishSection") })).toHaveCount(0);
    await expect(bar(page).getByRole("button", { name: t("player.prev") })).toHaveCount(0);

    await exam.choose(0);
    await exam.toggleFlag(true);
    await exam.next();
    await expect(bar(page).getByRole("button", { name: t("player.prev") })).toBeVisible();
    await exam.next();
    await exam.assertQuestionNumber(3, counts[0]);

    // "Next" on the section's last question opens the review page
    await exam.next();
    await expect(exam.reviewPage()).toBeVisible();
    await expect(exam.question()).toHaveCount(0);
    await expect(exam.reviewPage().getByRole("heading", { level: 2 })).toBeFocused();
    await expect(bar(page).getByRole("button", { name: t("player.next") })).toHaveCount(0);
    const list = exam.reviewPage().getByRole("button", { name: new RegExp(`^${t("player.question")} \\d+`) });
    await expect(list).toHaveCount(counts[0]);
    await expect(list.nth(0)).toHaveAccessibleName(entryName(1, { answered: true, flagged: true }));
    await expect(list.nth(0)).toContainText(t("player.palette.answered"));
    await expect(list.nth(1)).toHaveAccessibleName(entryName(2));
    await expect(list.nth(1)).toContainText(t("player.palette.unanswered"));
    await expect(list.nth(2)).toHaveAccessibleName(entryName(3));
    await expect(list.nth(2)).toHaveAttribute("aria-current", "true");

    // tap to jump; "Back" returns to the question left
    await list.nth(1).click();
    await exam.assertQuestionNumber(2, counts[0]);
    await expect(exam.reviewPage()).toHaveCount(0);
    await exam.openFinish();
    await bar(page).getByRole("button", { name: t("player.prev") }).click();
    await exam.assertQuestionNumber(2, counts[0]);

    // the unchanged section-end dialog, no-return warning included; "stay" stays on the review page
    await exam.openSectionEnd(1, { unanswered: counts[0] - 1, flagged: 1 });
    await exam.dialog().getByRole("button", { name: t("player.sectionEnd.stay") }).click();
    await expect(exam.dialog()).toBeHidden();
    await expect(exam.finishButton(false)).toBeFocused();
    await exam.openSectionEnd(1, { unanswered: counts[0] - 1, flagged: 1 });
    await exam.confirmSectionEnd(2);

    // forward-only: the next section starts on its first question, and nothing leads back
    await expect(exam.reviewPage()).toHaveCount(0);
    await exam.assertQuestionNumber(1, counts[1]);
    await expect(bar(page).getByRole("button", { name: t("player.prev") })).toHaveCount(0);
    await exam.openFinish();
    await expect(exam.reviewPage().getByRole("button", { name: new RegExp(`^${t("player.question")} \\d+`) })).toHaveCount(counts[1]);
    await bar(page).getByRole("button", { name: t("player.prev") }).click();
    await exam.assertQuestionNumber(1, counts[1]);
    await page.keyboard.press("ArrowLeft");
    await exam.assertQuestionNumber(1, counts[1]);

    // resume: still the second section
    await page.reload();
    await exam.assertSection(2);
    await exam.assertQuestionNumber(1, counts[1]);
    await page.context().close();
  });

  test("scrolling mode: bar moves by scrolling, last question opens the review page, jumps scroll back", async ({ browser }) => {
    const user = sc().students["bb-scroll"];
    const page = await studentPage(browser, user);
    const { items } = await startQuiz(page, user, sc().long_quiz);
    const item = (pos: number) => page.locator(`#item-${pos}`);
    await expect(item(items[0].position)).toHaveAttribute("aria-current", "true");

    await bar(page).getByRole("button", { name: t("player.next") }).click();
    await expect(item(items[1].position)).toBeFocused();
    await expect(item(items[1].position)).toBeInViewport();
    await bar(page).getByRole("button", { name: t("player.prev") }).click();
    await expect(item(items[0].position)).toBeFocused();

    // free navigation: every section on the review page, with its title
    await goToReviewPage(page);
    await expect(page.locator(`#item-${items[0].position}`)).toBeHidden();
    const entries = review(page).getByRole("button", { name: new RegExp(`^${t("player.question")} \\d+`) });
    await expect(entries).toHaveCount(48);
    await entries.nth(46).click();
    await expect(item(items[46].position)).toBeFocused();
    await expect(item(items[46].position)).toBeInViewport();

    // the last question: "Next" opens the review page; "Back" scrolls back to the question
    await bar(page).getByRole("button", { name: t("player.next") }).click();
    await expect(item(items[47].position)).toBeFocused();
    await bar(page).getByRole("button", { name: t("player.next") }).click();
    await expect(review(page)).toBeVisible();
    await bar(page).getByRole("button", { name: t("player.prev") }).click();
    await expect(item(items[47].position)).toBeFocused();
    await expect(item(items[47].position)).toBeInViewport();
    await page.context().close();
  });

  test("a hidden timer still counts, comes back in the last five minutes, and time-up works", async ({ browser }) => {
    const user = sc().students["bb-timer"];
    const page = await studentPage(browser, user);
    await page.clock.install();
    const { attemptId } = await startQuiz(page, user, sc().long_quiz);
    const timer = page.getByRole("timer", { name: t("player.timer.label") });
    const hide = page.getByRole("button", { name: t("player.timer.hideLabel") });
    const show = page.getByRole("button", { name: t("player.timer.showLabel") });
    const seconds = async () => {
      const parts = (await timer.innerText()).trim().split(":").map(Number);
      return parts.reduce((acc, p) => acc * 60 + p, 0);
    };

    await expect(timer).toBeVisible();
    const before = await seconds();
    await hide.click();
    await expect(timer).toHaveCount(0);

    // remembered in this tab
    await page.reload();
    await expect(show).toBeVisible();
    await expect(timer).toHaveCount(0);

    // still counting while hidden
    await page.clock.fastForward("30:00");
    await show.click();
    await expect(timer).toBeVisible();
    expect(await seconds()).toBeLessThanOrEqual(before - 30 * 60);
    await hide.click();
    await expect(timer).toHaveCount(0);

    // the last five minutes: the digits come back on their own and there is no button to hide them
    const left = before - 30 * 60;
    await page.clock.fastForward((left - 4 * 60) * 1000);
    await expect(timer).toBeVisible();
    expect(await seconds()).toBeLessThanOrEqual(5 * 60);
    await expect(hide).toHaveCount(0);
    await expect(show).toHaveCount(0);

    // time-up as today: the dialog, then the automatic submit
    await page.clock.fastForward("04:30");
    await expect(page.getByRole("dialog", { name: t("player.timeUp.title") })).toBeVisible();
    await page.clock.fastForward("00:20");
    await page.waitForURL(/\/result/, { timeout: 30_000 });
    await expect.poll(async () => (await api(user, `/attempts/${attemptId}`)).status, { timeout: 20_000 }).not.toBe("in_progress");
    await page.context().close();
  });

  test("Esc closes the popups and returns focus; hotkeys work and are ignored with a popup open", async ({ browser }) => {
    const user = sc().students["bb-keys"];
    const page = await studentPage(browser, user);
    const { attemptId, items } = await startQuiz(page, user, sc().page_quiz);
    const flag = page.locator("article").getByRole("button", { name: new RegExp(`^(${t("player.flag")}|${t("player.unflag")})$`) });
    await expect(heading(page, 1, 3)).toBeVisible();

    // question map: open, focus on the current question, hotkeys do nothing
    await questionMapToggle(page).click();
    await expect(map(page)).toBeVisible();
    await expect(map(page).getByRole("button", { name: entryName(1), exact: true })).toBeFocused();
    await expect(map(page)).toContainText(t("player.palette.current"));
    await expect(map(page)).toContainText(t("player.palette.unanswered"));
    await expect(map(page)).toContainText(t("player.palette.flagged"));
    for (const key of ["Digit2", "KeyF", "ArrowRight"]) await page.keyboard.press(key);
    await page.keyboard.press("Escape");
    await expect(map(page)).toBeHidden();
    await expect(questionMapToggle(page)).toBeFocused();
    await expect(heading(page, 1, 3)).toBeVisible();
    await expect(radios(page).nth(1)).toHaveAttribute("aria-checked", "false");
    await expect(flag).toHaveAttribute("aria-pressed", "false");

    // "More": the shortcuts live here; hotkeys ignored while it is open; Esc returns focus
    const more = top(page).getByRole("button", { name: t("player.more"), exact: true });
    await more.click();
    await expect(top(page).getByText(t("player.shortcuts"))).toBeVisible();
    for (const key of ["Digit2", "KeyF", "ArrowRight"]) await page.keyboard.press(key);
    await page.keyboard.press("Escape");
    await expect(top(page).getByText(t("player.shortcuts"))).toHaveCount(0);
    await expect(more).toBeFocused();
    await expect(heading(page, 1, 3)).toBeVisible();
    await expect(radios(page).nth(1)).toHaveAttribute("aria-checked", "false");
    await expect(flag).toHaveAttribute("aria-pressed", "false");

    // hotkeys work once it is closed (physical keys, so any keyboard layout)
    await page.keyboard.press("Digit2");
    await expect(radios(page).nth(1)).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("KeyF");
    await expect(flag).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("ArrowRight");
    await expect(heading(page, 2, 3)).toBeVisible();
    await page.keyboard.press("ArrowLeft");
    await expect(heading(page, 1, 3)).toBeVisible();

    // the review page shows no question: flag and answer keys are ignored, the left arrow goes back
    await goToReviewPage(page);
    for (const key of ["Digit1", "KeyF", "ArrowRight"]) await page.keyboard.press(key);
    await expect(review(page)).toBeVisible();
    await page.keyboard.press("ArrowLeft");
    await expect(heading(page, 1, 3)).toBeVisible();
    await expect(radios(page).nth(1)).toHaveAttribute("aria-checked", "true");
    await expect(flag).toHaveAttribute("aria-pressed", "true");

    await expect(page.getByRole("status").filter({ hasText: t("player.save.saved") })).toBeVisible({ timeout: 20_000 });
    await expect.poll(async () => {
      const st = await api(user, `/attempts/${attemptId}`);
      const first = (st.items as ItemState[]).find((i) => i.position === items[0].position)!;
      return !!first.response && first.flagged;
    }, { timeout: 20_000 }).toBe(true);

    // "Directions" only when the section has instructions (this one has none); shown from the top bar when it has
    await expect(top(page).getByRole("button", { name: t("player.directions") })).toHaveCount(0);
    await page.route(/\/attempts\/[0-9a-f-]{36}\/content/, async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      body.sections[0].instructions = "Читайте внимательно.";
      await route.fulfill({ response: res, json: body });
    });
    await page.reload();
    const directions = top(page).getByRole("button", { name: t("player.directions") });
    await directions.click();
    await expect(top(page).getByText("Читайте внимательно.")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(top(page).getByText("Читайте внимательно.")).toHaveCount(0);
    await expect(directions).toBeFocused();
    await page.context().close();
  });

  test("reading: split screen with a divider from lg, stacked at 375 px", async ({ browser }) => {
    const page = await studentPage(browser, seed().students["bb-split-ru"]);
    const exam = new OrtExam(page, L);
    const counts = sectionCounts();
    await exam.openLobby();
    await exam.start();

    // Math I: Column A and Column B side by side above the answers
    const a = await exam.question().getByText(exam.t("player.comparison.columnA"), { exact: true }).boundingBox();
    const b = await exam.question().getByText(exam.t("player.comparison.columnB"), { exact: true }).boundingBox();
    expect(Math.abs(a!.y - b!.y)).toBeLessThan(2);
    expect(b!.x).toBeGreaterThan(a!.x);

    for (const pos of [1, 2, 3]) await exam.skipSection(pos);
    await exam.assertSection(4);
    await exam.assertPassage();

    const divider = page.getByRole("separator", { name: t("player.passage.resize") });
    const pane = page.locator('section[id^="passage-"]');
    await expect(divider).toHaveAttribute("aria-valuenow", "50");

    // arrow keys move the divider, not the question; clamped to 30-70 %
    await divider.focus();
    await page.keyboard.press("ArrowRight");
    await expect(divider).toHaveAttribute("aria-valuenow", "52");
    await exam.assertQuestionNumber(1, counts[3]);
    await page.keyboard.press("End");
    await expect(divider).toHaveAttribute("aria-valuenow", "70");
    await page.keyboard.press("ArrowRight");
    await expect(divider).toHaveAttribute("aria-valuenow", "70");
    await page.keyboard.press("Home");
    await expect(divider).toHaveAttribute("aria-valuenow", "30");
    await page.keyboard.press("ArrowLeft");
    await expect(divider).toHaveAttribute("aria-valuenow", "30");
    await exam.assertQuestionNumber(1, counts[3]);

    // dragging, and the pane follows
    const box = await divider.boundingBox();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + 100);
    await page.mouse.down();
    await page.mouse.move(VIEWPORTS.desktop.width * 0.6, box!.y + 100, { steps: 4 });
    await page.mouse.up();
    await expect(divider).toHaveAttribute("aria-valuenow", "60");
    const widthAt60 = (await pane.boundingBox())!.width;
    expect(Math.abs(widthAt60 - VIEWPORTS.desktop.width * 0.6)).toBeLessThan(8);

    // each side scrolls by itself: the player does not, the text keeps its place when the question changes
    const scroller = page.locator("div.fixed.inset-0.overflow-y-auto").first();
    expect(await scroller.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeLessThanOrEqual(0);
    await pane.evaluate((el) => { el.scrollTop = 200; });
    expect(await pane.evaluate((el) => el.scrollTop)).toBe(200);
    await exam.next();
    await exam.assertQuestionNumber(2, counts[3]);
    expect(await pane.evaluate((el) => el.scrollTop)).toBe(200);

    // the divider is remembered in this tab
    await page.reload();
    await expect(divider).toHaveAttribute("aria-valuenow", "60");

    // phone width: text above the question, no divider, the bar stays in view, no sideways scroll
    await page.setViewportSize(VIEWPORTS.phone);
    await expect(divider).toBeHidden();
    await expect(bar(page)).toBeInViewport();
    const stacked = await pane.boundingBox();
    const question = await exam.question().boundingBox();
    expect(question!.y).toBeGreaterThan(stacked!.y + stacked!.height - 1);
    await scroller.evaluate((el) => el.scrollTo(0, 800));
    await expect(bar(page)).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(VIEWPORTS.phone.width);
    expect(await scroller.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await page.context().close();
  });

  test("screenshots at 375, 1440 and 1920 px (PLAYER_SCREENS_DIR)", async ({ browser }) => {
    test.skip(!SCREENS, "set PLAYER_SCREENS_DIR to write the screenshots");
    test.setTimeout(600_000);
    fs.mkdirSync(SCREENS!, { recursive: true });
    const sizes = [["375", VIEWPORTS.phone], ["1440", VIEWPORTS.desktop], ["1920", { width: 1920, height: 1080 }]] as const;
    const page = await studentPage(browser, seed().students["bb-screens-ru"]);
    const shootAll = async (name: string) => {
      for (const [label, size] of sizes) {
        await page.setViewportSize(size);
        await settle(page);
        await page.screenshot({ path: path.join(SCREENS!, `${name}-${label}.png`), animations: "disabled", caret: "hide" });
      }
      await page.setViewportSize(VIEWPORTS.desktop);
    };
    const exam = new OrtExam(page, L);
    await exam.openLobby();
    await exam.start();
    await exam.choose(0);
    await exam.toggleFlag(true);
    await shootAll("comparison");
    await exam.showPalette();
    await shootAll("popup");
    await exam.openFinish();
    await shootAll("review");
    await exam.openSectionEnd(1, { unanswered: 2, flagged: 1 });
    await shootAll("section-end");
    await exam.confirmSectionEnd(2);
    await exam.skipSection(2);
    await exam.skipSection(3);
    await exam.assertSection(4);
    await shootAll("passage");
    await top(page).getByRole("button", { name: t("player.more"), exact: true }).click();
    await shootAll("more");
    await page.keyboard.press("Escape");
    await page.context().close();

    const user = sc().students["bb-screens"];
    const sp = await studentPage(browser, user);
    await startQuiz(sp, user, sc().long_quiz);
    for (const [label, size] of sizes) {
      await sp.setViewportSize(size);
      await settle(sp);
      await sp.screenshot({ path: path.join(SCREENS!, `scrolling-${label}.png`), animations: "disabled", caret: "hide" });
    }
    await sp.context().close();
  });
});
