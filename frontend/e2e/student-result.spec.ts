import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { sectionCounts, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * SF-1 (docs/phases/STUDENT_UI_FIX_PLAN.md §2.1, §2.2 with the §10 overrides): an exam-prep student's lobby and result
 * live in the student shell (`.student-theme`, the student navigation), the player route has no chrome at all (no
 * sidebar, no tab bar) at 375 and 1440, and the result page shows the hero, the section breakdown and the actions.
 * An empty attempt (raw 0) reads "0" with the plain sentence and never "Незачёт", "Идёт в зачёт" or "Процентиль 0.0".
 * A link to `#item-n` lands on that review card (problem 3).
 *
 * Data: `result-zero-ru` (skips every section) and `result-data-ru` (two correct answers) in ORT (Russian).
 * With F2_SHOTS=<dir>, the UX screens (lobby, player, result, zero result, review with hash) at 375 / 1440 / 1920 ru.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.F2_SHOTS || "";
const WIDTHS = [375, 1440, 1920] as const;

async function api(user: SeedUser, p: string) {
  const r = await fetch(`${seed().api}/api/v1${p}`, { headers: { Authorization: `Bearer ${user.token}` } });
  expect(r.status, p).toBeLessThan(300);
  return r.json();
}

async function shoot(page: Page, name: string, widths: readonly number[] = WIDTHS) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

const studentNav = (page: Page) => page.getByRole("navigation", { name: t("student.nav.label") });
const tabBar = (page: Page) => page.getByRole("navigation", { name: t("student.nav.tabBar") });
const attemptIdOf = (url: string) => /\/attempts\/([^/?#]+)\/result/.exec(url)![1];

test.describe("student result page (ru)", () => {
  test.describe.configure({ mode: "serial" });
  test.use({ viewport: VIEWPORTS.desktop });

  test("empty attempt: lobby and result in the student shell, chrome-less player, zero sentence, actions", async ({ page }) => {
    test.setTimeout(240_000);
    const s = seed();
    const user = s.students["result-zero-ru"];
    const total = sectionCounts().reduce((a, b) => a + b, 0);
    await signIn(page, user);
    const exam = new OrtExam(page, L);

    // ---- lobby: inside the student shell (sidebar navigation, tokens), no course header or breadcrumbs
    await exam.openLobby();
    await exam.assertLobby();
    await expect(page.locator(".student-theme").getByRole("heading", { name: "ОРТ E2E", exact: true })).toBeVisible();
    await expect(studentNav(page)).toBeVisible();
    await expect(page.getByRole("link", { name: t("results.backToTests") })).toHaveAttribute("href", `/${L}/courses/${s.course_id}/tests`);
    await expect(page.getByRole("navigation", { name: t("ui.breadcrumbs") })).toHaveCount(0);

    // ---- player: no sidebar, no tab bar; the student tokens and font only
    await exam.start();
    await expect(exam.topBar()).toBeVisible();
    await expect(studentNav(page)).toHaveCount(0);
    await expect(tabBar(page)).toHaveCount(0);
    await expect(page.locator(".student-theme").filter({ has: exam.topBar() })).toHaveCount(1);
    for (const pos of [1, 2, 3, 4]) await exam.skipSection(pos);
    await exam.openSubmit({ unanswered: sectionCounts()[4], flagged: 0 });
    await exam.confirmSubmit();

    // ---- result: the ORT DOM checks, inside the student shell
    const summary = await exam.assertResult(0, total);
    await expect(page.locator(".student-theme").filter({ has: summary })).toHaveCount(1);
    await expect(studentNav(page)).toBeVisible();
    const grade = summary.getByRole("group", { name: t("results.grade.title") });
    await expect(grade.locator("p").nth(1)).toHaveText("0");
    const attemptId = attemptIdOf(page.url());
    const result = await api(user, `/attempts/${attemptId}/result`);
    const min = String(Number(result.grade.scale_min));
    await expect(summary.getByText(t("results.hero.zeroRaw", { min }), { exact: true })).toBeVisible();
    await expect(page.getByTestId("result-mascot")).toContainText(t("mascot.result.encourage"));
    // no pass/fail, no "counts towards the grade", no percentile
    await expect(page.getByText(t("schemes.labels.fail"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("schemes.labels.pass"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("results.grade.kept"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("results.grade.percentile", { value: "" }).trim(), { exact: false })).toHaveCount(0);
    await expect(page.getByText(t("results.hero.percentile", { value: "X" }).split("X")[0].trim(), { exact: false })).toHaveCount(0);
    // header: back to Тесты, no breadcrumbs
    await expect(page.getByRole("link", { name: t("results.backToTests") })).toHaveAttribute("href", `/${L}/courses/${s.course_id}/tests`);
    await expect(page.getByRole("link", { name: t("results.back") })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: t("ui.breadcrumbs") })).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1, name: t("results.title") })).toBeVisible();

    // ---- actions: one primary "Review mistakes" (turns the filter on, scrolls to the review), "Next test"
    const next = page.getByRole("link", { name: t("results.actions.nextTest"), exact: true });
    await expect(next).toHaveAttribute("href", new RegExp(`^/${L}/courses/${s.course_id}/(assessments/[^/]+|tests)$`));
    await settle(page);
    await shoot(page, "result-zero");
    const review = exam.review();
    const only = review.getByRole("button", { name: t("results.review.onlyMistakes") });
    await expect(only).toHaveAttribute("aria-pressed", "false");
    await page.getByRole("button", { name: t("results.actions.reviewMistakes"), exact: true }).click();
    await expect(only).toHaveAttribute("aria-pressed", "true");
    await expect(review.getByRole("heading", { name: t("results.reviewTitle"), exact: true })).toBeInViewport();

    // ---- problem 3: `#item-n` lands on that card once the review has loaded
    const items: { position: number }[] = (await api(user, `/attempts/${attemptId}/review`)).items;
    const last = items[items.length - 1].position;
    const resultPath = new URL(page.url()).pathname;
    await page.goto(exam.lobbyPath);
    await expect(page.locator("ol").first()).toBeVisible();
    await page.goto(`${resultPath}#item-${last}`);
    await expect(page.locator(`#item-${last}`)).toBeInViewport();
    await shoot(page, "review-hash");
  });

  test("result with correct answers: hero, section breakdown, next test; UX screens", async ({ page }) => {
    test.setTimeout(240_000);
    const s = seed();
    const counts = sectionCounts();
    const total = counts.reduce((a, b) => a + b, 0);
    await signIn(page, s.students["result-data-ru"]);
    const exam = new OrtExam(page, L);
    await exam.openLobby();
    await settle(page);
    await shoot(page, "lobby");
    await exam.start();
    await exam.assertSection(1);
    await exam.choose(s.keys[s.picks.math_1[0]].correct);
    await settle(page);
    await shoot(page, "player", [375, 1440]);
    await exam.openSectionEnd(1, { unanswered: counts[0] - 1, flagged: 0 });
    await exam.confirmSectionEnd(2);
    await exam.skipSection(2);
    await exam.skipSection(3);
    await exam.assertSection(4);
    await exam.choose(s.keys[s.picks.reading[0]].correct);
    await exam.openSectionEnd(4, { unanswered: counts[3] - 1, flagged: 0 });
    await exam.confirmSectionEnd(5);
    await exam.openSubmit({ unanswered: counts[4], flagged: 0 });
    await exam.confirmSubmit();

    const summary = await exam.assertResult(2, total);
    const grade = summary.getByRole("group", { name: t("results.grade.title") });
    await expect(grade.locator("p").nth(1)).toHaveText(/^[1-9]\d*([.,]\d+)?$/);
    await expect(summary.getByText(t("results.hero.zeroRaw", { min: "" }).slice(0, 20), { exact: false })).toHaveCount(0);
    await expect(page.getByText(t("schemes.labels.fail"), { exact: true })).toHaveCount(0);
    await expect(page.getByText(t("results.grade.kept"), { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: t("results.actions.reviewMistakes"), exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: t("results.actions.nextTest"), exact: true })).toBeVisible();
    await settle(page);
    await shoot(page, "result");

    // the lobby after the attempt: the attempts list of this test
    await page.goto(exam.lobbyPath);
    await expect(page.getByRole("heading", { name: t("home.attempts.title") })).toBeVisible();
    await settle(page);
    await shoot(page, "lobby-after");
  });

  for (const vp of ["phone", "desktop"] as const) {
    test(`player route has no chrome (${vp})`, async ({ page }) => {
      const s = seed();
      await page.setViewportSize(VIEWPORTS[vp]);
      await signIn(page, s.students["result-zero-ru"]);
      // the attempt requests are held: the player's own loading state stays on screen
      await page.route((url) => url.href.startsWith(s.api) && url.pathname.includes("/attempts/"), () => { /* held */ });
      await page.goto(`/${L}/courses/${s.course_id}/attempts/${s.staff_attempt_id}`);
      const loading = page.getByRole("status").filter({ hasText: t("player.loading") });
      await expect(loading).toHaveCount(1);
      await expect(page.locator(".student-theme").filter({ has: loading })).toHaveCount(1);
      await expect(studentNav(page)).toHaveCount(0);
      await expect(tabBar(page)).toHaveCount(0);
      await expect(page.locator(".lg\\:pl-\\[264px\\]")).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(VIEWPORTS[vp].width);
    });
  }
});
