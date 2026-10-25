import { expect, test, type Locator, type Page } from "@playwright/test";
import { expectScreen, sectionCounts, seed, signIn, tr, VIEWPORTS, type Lang, type ViewportName } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * ORT screenshot baselines (PHASE_6_DESIGN section 6, decision A3): every screen is compared with
 * docs/phases/ORT_BASELINE/<screen>-<viewport>-<lang>.png after its DOM assertions. Student screens: phone and
 * desktop, ru and ky. Teacher screens (`teacher-*`): phone and desktop, ru. See docs/phases/ORT_BASELINE/README.md.
 */

const VIEWPORT_NAMES: ViewportName[] = ["phone", "desktop"];

/** Timer digits change every second: painted over (the timer itself is asserted in the DOM). */
const timerMask = (page: Page): Locator[] => [page.getByRole("timer")];

async function noLoading(page: Page, lang: Lang) {
  await expect(page.getByText(tr(lang, "lms.common.loading"), { exact: true })).toHaveCount(0);
  await expect(page.getByText(tr(lang, "player.loading"), { exact: true })).toHaveCount(0);
}

for (const vp of VIEWPORT_NAMES) {
  for (const lang of ["ru", "ky"] as Lang[]) {
    test.describe(`ORT student screens ${vp} ${lang}`, () => {
      test.use({ viewport: VIEWPORTS[vp] });

      test(`student screens (${vp}, ${lang})`, async ({ page }, info) => {
        const s = seed();
        await signIn(page, s.students[`vis-${vp}-${lang}`]);
        const exam = new OrtExam(page, lang);
        const counts = sectionCounts();
        const shot = (screen: string, mask: Locator[] = [], extra: { element?: Locator; fullPage?: boolean } = {}) =>
          expectScreen(page, info, `${screen}-${vp}-${lang}`, { mask, ...extra });

        // lobby
        await exam.openLobby();
        await exam.assertLobby();
        await shot("lobby", [], { fullPage: true });

        // comparison question with an answer chosen
        await exam.start();
        await exam.assertSection(1);
        await exam.assertComparison();
        await exam.choose(s.keys[s.picks.math_1[0]].correct);
        await page.mouse.move(0, 0);
        await shot("comparison", timerMask(page));

        // palette: #1 answered + flagged, #2 current, #3 unanswered
        await exam.toggleFlag(true);
        await exam.next();
        await exam.assertPaletteEntry(1, { answered: true, flagged: true, current: false });
        await exam.assertPaletteEntry(2, { answered: false, flagged: false, current: true });
        // desktop: the side panel; phones: the palette sheet opened from the header (S7b, P1)
        await exam.showPalette();
        await shot("flagged-palette", timerMask(page));

        // section-end dialog
        await exam.openSectionEnd(1, { unanswered: 2, flagged: 1 });
        await shot("section-end", timerMask(page));
        await exam.confirmSectionEnd(2);
        await exam.skipSection(2);
        await exam.skipSection(3);

        // passage with line numbers
        await exam.assertSection(4);
        await exam.assertPassage();
        await exam.choose(s.keys[s.picks.reading[0]].correct);
        // the player is a fixed, scrolling overlay: back to its top (the passage comes first on phones)
        await page.evaluate(() => document.querySelectorAll("div.fixed.inset-0").forEach((el) => el.scrollTo(0, 0)));
        await shot("passage", timerMask(page));

        // submit dialog
        await exam.openSectionEnd(4, { unanswered: counts[3] - 1, flagged: 0 });
        await exam.confirmSectionEnd(5);
        await exam.openSubmit({ unanswered: counts[4], flagged: 0 });
        await shot("submit", timerMask(page));
        await exam.confirmSubmit();

        // result (submission date masked) and the review below it
        const summary = await exam.assertResult(2, counts.reduce((a, b) => a + b, 0));
        await noLoading(page, lang);
        const submitted = summary.getByText(tr(lang, "results.submittedAt", { date: "" }).trim(), { exact: false });
        await expect(submitted).toBeVisible();
        // the whole result card (raw score, scaled grade, five section rows), whatever the viewport height
        await shot("result", [submitted], { element: summary });
        await expect(exam.review()).toBeVisible();
        await exam.review().getByRole("heading", { name: tr(lang, "results.reviewTitle"), exact: true })
          .evaluate((el) => el.scrollIntoView({ block: "start" }));
        await shot("review", [submitted]);
        // B4 / R1: the result page with the review never scrolls sideways (the page is as wide as the viewport)
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(VIEWPORTS[vp].width);
      });
    });
  }
}

// ----------------------------------------------------------------------------- ORT teacher screens (ru)

for (const vp of VIEWPORT_NAMES) {
  test.describe(`ORT teacher screens ${vp}`, () => {
    test.use({ viewport: VIEWPORTS[vp] });
    const lang: Lang = "ru";

    test(`teacher screens (${vp}, ru)`, async ({ page }, info) => {
      const s = seed();
      await signIn(page, s.admin);
      const c = `/${lang}/courses/${s.course_id}`;
      const shot = (screen: string, opts: { mask?: Locator[]; element?: Locator; fullPage?: boolean } = {}) =>
        expectScreen(page, info, `teacher-${screen}-${vp}-${lang}`, opts);
      const open = async (url: string) => {
        await page.goto(url);
        await noLoading(page, lang);
      };

      // ORT bank: the imported tsoomo19 questions
      await open(`${c}/bank/${s.bank_id}`);
      await expect(page.getByRole("heading", { name: "tsoomo19", exact: true })).toBeVisible();
      await expect(page.getByText("(150)", { exact: false }).first()).toBeVisible();
      await shot("bank");

      // comparison question editor (math_1)
      await open(`${c}/bank/q/${s.comparison_question_id}`);
      await expect(page.getByText(tr(lang, "bank.types.comparison.labels.A")).first()).toBeVisible();
      await shot("question-comparison", { fullPage: true });

      // passage editor (reading)
      await open(`${c}/bank/p/${s.passage_id}`);
      await expect(page.locator("textarea").first()).toBeVisible();
      await shot("passage"); // viewport only: the auto-growing passage textarea makes the full page ~10,000 px

      // import page
      await open(`${c}/bank/import`);
      await expect(page.locator("input[type=file]")).toHaveCount(1);
      await shot("import", { fullPage: true });

      // ORT builder: five ORT sections
      await open(`${c}/assessments/${s.staff_exam.id}/edit`);
      const cards = page.getByRole("region").filter({ has: page.getByRole("heading", { level: 3 }) });
      const keys = ["math_1", "math_2", "analogies", "reading", "grammar"];
      for (const [i, key] of keys.entries()) {
        await expect(page.getByRole("heading", { level: 3, name: `${i + 1}. ${tr(lang, `sections.${key}`)}`, exact: true })).toBeVisible();
      }
      await expect(cards).toHaveCount(5);
      await shot("builder");

      // publish panel after "validate"
      const validate = page.getByRole("button", { name: tr(lang, "assessments.publish.validate") });
      await validate.click();
      await expect(page.getByText(tr(lang, "assessments.publish.valid"))).toBeVisible();
      const panel = validate.locator("xpath=ancestor::div[contains(@class,'rounded-2xl')][1]");
      await shot("publish", { element: panel });

      // staff attempts: the seeded submitted attempt (dates masked)
      await open(`${c}/assessments/${s.staff_exam.id}/attempts`);
      await expect(page.getByText(s.students["staff-seed"].name).first()).toBeVisible();
      await shot("attempts", { mask: [page.locator("time"), page.getByText(/\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}:\d{2}/)] });
    });
  });
}
