import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { sectionCounts, seed, settle, signIn, tr, type SeedUser } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * Exam prep S2 (docs/ROADMAP_EXAM_PREP.md S2): a newcomer finds ORT (Russian) under "From the platform" on the home,
 * joins it with one tap, lands on the exam-prep page (countdown, target, Next, library), sets a target, takes the
 * seeded test from the Next card, and back on the page sees the score, the history, five section bars and the next
 * step. The exam player and the result page are the ORT ones, unchanged (OrtExam asserts them).
 *
 * Data: `seed.exam_prep.newcomer` (registered, in no course); the exam date is set by the admin and cleared after.
 * Screens of the page at 375 / 1440 / 1920 (ru) go to $S2_SHOTS (default /tmp/s2_shots).
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.S2_SHOTS || "/tmp/s2_shots";
const WIDTHS = [375, 1440, 1920] as const;

async function api(user: SeedUser, method: string, p: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  expect(r.status, `${method} ${p}`).toBeLessThan(300);
  return r.status === 204 ? null : r.json();
}

async function shoot(page: Page, name: string) {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal scroll at ${width}px (${name})`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

function isoInDays(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

test.describe("exam-prep page (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("home -> join ORT -> exam-prep page -> take the test -> score, sections, next", async ({ browser }) => {
    test.setTimeout(300_000);
    const s = seed();
    const cid = s.course_id;
    const newcomer = s.exam_prep!.newcomer;
    await api(s.admin, "PATCH", `/courses/${cid}`, { exam_date: isoInDays(30) });
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const page = await ctx.newPage();
    try {
      await signIn(page, newcomer);

      // ---- home: "From the platform" lists the ORT courses; one tap joins
      await page.goto(`/${L}/courses`);
      const platform = page.getByRole("region", { name: t("home.platform.title") });
      await expect(platform).toBeVisible();
      const card = platform.locator("li").filter({ has: page.locator(`a[href="/${L}/courses/catalog/${cid}"]`) });
      await expect(card).toHaveCount(1);
      await shoot(page, "home-platform");
      await card.getByRole("button", { name: t("catalog.join"), exact: true }).click();
      await page.waitForURL(new RegExp(`/${L}/courses/${cid}$`));

      // ---- the exam-prep page: countdown, no score yet, Next = the first test of the library
      await expect(page.getByText(t("examPrep.goal.daysLabel"), { exact: true })).toBeVisible();
      await expect(page.getByText("30", { exact: true })).toBeVisible();
      await expect(page.getByText(t("examPrep.goal.noScore"))).toBeVisible();
      const next = page.getByRole("region", { name: t("examPrep.next.title") });
      await expect(next).toContainText("ОРТ E2E");
      await expect(next).toContainText(t("examPrep.next.reason.start"));
      const library = page.getByRole("region", { name: t("examPrep.library.title") });
      await expect(library.getByRole("link", { name: "ОРТ E2E", exact: true })).toBeVisible();
      await expect(library.getByRole("link", { name: "ОРТ E2E staff", exact: true })).toBeVisible();
      await expect(library.getByText(t("examPrep.library.status.not_started")).first()).toBeVisible();
      await shoot(page, "exam-prep-new");

      // ---- Student UI U3: the home is now the exam-prep home of ORT (Russian): greeting, countdown, Next, no score yet
      await page.goto(`/${L}/courses`);
      await expect(page.getByRole("heading", { level: 1 })).toContainText(newcomer.name.split(" ")[0]);
      await expect(page.getByRole("group", { name: new RegExp(`^${t("examPrep.goal.daysLabel")}: \\d+ `) })).toBeVisible();
      await expect(page.getByRole("region", { name: t("examPrep.next.title") })).toContainText("ОРТ E2E");
      await expect(page.getByRole("region", { name: t("home.prep.score.title") })).toContainText(t("examPrep.goal.noScore"));
      await shoot(page, "home-prep-new");
      await page.goto(`/${L}/courses/${cid}`);

      // ---- the target, inline: out of range is refused, 200 is kept
      await page.getByRole("button", { name: t("examPrep.goal.setTarget") }).click();
      const input = page.getByLabel(t("examPrep.goal.inputLabel", { min: 60, max: 245 }));
      await input.fill("300");
      await page.getByRole("button", { name: t("examPrep.goal.save"), exact: true }).click();
      await expect(page.getByText(t("examPrep.goal.invalid", { min: 60, max: 245 }))).toBeVisible();
      await input.fill("200");
      await page.getByRole("button", { name: t("examPrep.goal.save"), exact: true }).click();
      await expect(page.getByText("200", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: t("examPrep.goal.edit") })).toBeVisible();

      // ---- Next -> the lobby -> the ORT player -> the ORT result (both unchanged)
      await next.getByRole("link", { name: t("examPrep.next.action.start") }).click();
      await page.waitForURL(new RegExp(`/courses/${cid}/assessments/${s.exam.id}$`));
      const exam = new OrtExam(page, L);
      await exam.assertLobby();
      await exam.start();
      const counts = sectionCounts();
      const total = counts.reduce((a, b) => a + b, 0);
      await exam.assertSection(1);
      const k = s.keys[s.picks.math_1[0]];
      await exam.choose(k.correct);
      await exam.openSectionEnd(1, { unanswered: counts[0] - 1, flagged: 0 });
      await exam.confirmSectionEnd(2);
      for (const pos of [2, 3, 4]) await exam.skipSection(pos);
      await exam.openSubmit({ unanswered: counts[4], flagged: 0 });
      await exam.confirmSubmit();
      await exam.assertResult(1, total);

      // ---- back on the page: latest score, history, five section bars, the next test
      await page.goto(`/${L}/courses/${cid}`);
      await expect(page.getByText(t("examPrep.goal.latestLabel"), { exact: true })).toBeVisible();
      await expect(page.getByText(t("examPrep.goal.outOf", { max: 245 })).first()).toBeVisible();
      await expect(page.getByRole("img", { name: t("examPrep.history.chart") })).toBeVisible();
      const sections = page.getByRole("region", { name: t("examPrep.sections.title") });
      await expect(sections.getByRole("progressbar")).toHaveCount(5);
      for (const key of ["math_1", "math_2", "analogies", "reading", "grammar"]) {
        await expect(sections).toContainText(t(`sections.${key}`));
      }
      await expect(sections).toContainText(t("examPrep.sections.score", { raw: 1, possible: counts[0] }));
      await expect(next).toContainText("ОРТ E2E staff");
      await expect(next).toContainText(t("examPrep.next.reason.start"));
      const done = library.locator("li").filter({ has: page.getByRole("link", { name: "ОРТ E2E", exact: true }) });
      await expect(done).toContainText(t("examPrep.library.status.done"));
      await expect(done).toContainText(t("examPrep.library.best"));
      await shoot(page, "exam-prep-after");

      // ---- the home: ORT (Russian) is one of the student's courses now, no longer under "From the platform"
      await page.goto(`/${L}/courses`);
      await expect(page.getByRole("region", { name: t("home.courses.title") }).locator(`a[href="/${L}/courses/${cid}"]`)).toHaveCount(1);
      await expect(page.locator(`a[href="/${L}/courses/catalog/${cid}"]`)).toHaveCount(0);
      // Student UI U3: current vs target, the section rows of the latest result, the streak of today's answers
      const scores = page.getByRole("region", { name: t("home.prep.score.title") });
      await expect(scores).toContainText(t("examPrep.goal.outOf", { max: 245 }));
      await expect(scores).toContainText("200");
      await expect(page.getByRole("region", { name: t("examPrep.sections.title") }).getByRole("meter")).toHaveCount(5);
      await expect(page.getByRole("region", { name: t("home.prep.streak.title") })).toContainText(t("home.prep.streak.days_one", { count: 1 }));
      await expect(page.getByRole("region", { name: t("examPrep.next.title") })).toContainText("ОРТ E2E staff");
      await shoot(page, "home-prep-after");
    } finally {
      await api(s.admin, "PATCH", `/courses/${cid}`, { exam_date: null });
      await ctx.close();
    }
  });
});
