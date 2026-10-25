import { expect, test } from "@playwright/test";
import { ORT_SECTIONS, sectionCounts, seed, signIn, VIEWPORTS, type Lang } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * ORT browser e2e (PHASE_6_DESIGN section 6, "ORT browser e2e"): the student walk through the real `ort_main`
 * exam of ORT (Russian), in the ru and ky interface. Lobby -> start -> comparison question -> flag -> palette
 * states -> section-end dialog -> passage question with line numbers -> submit dialog -> result page.
 */

/** Index of the correct / a wrong answer button for item n (1-based) of an ORT section. */
function answerIndex(section: (typeof ORT_SECTIONS)[number], n: number, correct: boolean): number {
  const k = seed().keys[seed().picks[section][n - 1]];
  return correct ? k.correct : (k.correct + 1) % k.choices;
}

for (const lang of ["ru", "ky"] as Lang[]) {
  test.describe(`ORT exam walk (${lang})`, () => {
    test.use({ viewport: VIEWPORTS.desktop });

    test(`lobby to result (${lang})`, async ({ page }) => {
      const s = seed();
      await signIn(page, s.students[`flow-${lang}`]);
      const exam = new OrtExam(page, lang);
      const counts = sectionCounts();
      const total = counts.reduce((a, b) => a + b, 0);
      expect(counts).toEqual([3, 2, 2, s.picks.reading.length, 2]);

      // ---- lobby: five sections in ORT order, forward-only
      await exam.openLobby();
      await exam.assertLobby();
      await exam.start();

      // ---- section 1 (math_1): the comparison card, flag, palette states
      await exam.assertSection(1);
      await exam.assertQuestionNumber(1, counts[0]);
      await exam.assertComparison();
      await exam.assertPaletteEntry(1, { answered: false, flagged: false, current: true });
      await exam.choose(answerIndex("math_1", 1, true));
      await exam.toggleFlag(true);
      await exam.assertPaletteEntry(1, { answered: true, flagged: true, current: true });
      await exam.next();
      await exam.assertQuestionNumber(2, counts[0]);
      await exam.assertComparison();
      await exam.choose(answerIndex("math_1", 2, false));
      await exam.assertPaletteEntry(1, { answered: true, flagged: true, current: false });
      await exam.assertPaletteEntry(2, { answered: true, flagged: false, current: true });
      await exam.assertPaletteEntry(3, { answered: false, flagged: false, current: false });
      // unflag and flag again: the state follows the button
      await exam.paletteButtons().nth(0).click();
      await exam.assertQuestionNumber(1, counts[0]);
      await exam.toggleFlag(false);
      await exam.assertPaletteEntry(1, { answered: true, flagged: false, current: true });
      await exam.toggleFlag(true);

      // ---- section-end dialog: "stay" keeps the section, "close" moves forward for good
      await exam.openSectionEnd(1, { unanswered: 1, flagged: 1 });
      await exam.dialog().getByRole("button", { name: exam.t("player.sectionEnd.stay") }).click();
      await expect(exam.dialog()).toBeHidden();
      await exam.assertSection(1);
      await exam.openSectionEnd(1, { unanswered: 1, flagged: 1 });
      await exam.confirmSectionEnd(2);
      // forward-only: only the new section is offered
      await expect(exam.paletteButtons()).toHaveCount(counts[1]);
      await expect(exam.question().getByText(exam.t("player.comparison.columnA"), { exact: true })).toHaveCount(0);

      await exam.skipSection(2);
      await exam.skipSection(3);

      // ---- section 4 (reading): passage with line numbers next to the question
      await exam.assertSection(4);
      await exam.assertPassage();
      await exam.assertQuestionNumber(1, counts[3]);
      await exam.choose(answerIndex("reading", 1, true));
      await exam.openSectionEnd(4, { unanswered: counts[3] - 1, flagged: 0 });
      await exam.confirmSectionEnd(5);

      // ---- section 5 (grammar, last): the submit dialog
      await exam.assertSection(5);
      await expect(exam.finishButton(true)).toBeVisible();
      await exam.openSubmit({ unanswered: counts[4], flagged: 0 });
      await exam.dialog().getByRole("button", { name: exam.t("player.submit.back") }).click();
      await expect(exam.dialog()).toBeHidden();
      await exam.openSubmit({ unanswered: counts[4], flagged: 0 });
      await exam.confirmSubmit();

      // ---- result: raw 2 of 19 (math_1 #1 and reading #1 correct), scaled grade card, five section rows
      await exam.assertResult(2, total);
      await expect(exam.review()).toBeVisible();
      await expect(exam.review().getByRole("heading", { name: exam.t("results.reviewTitle"), exact: true })).toBeVisible();
      // one review card per item (its heading), after the review title
      await expect(exam.review().getByRole("heading", { level: 3 })).toHaveCount(total + 1);
    });
  });
}

// S11a (F4, F5): on phones "finish section" sits in the palette sheet's pinned footer, and after the sheet closes
// the section-end dialog's "stay" returns focus to the header palette button (a live element).
test.describe("ORT palette sheet (phone, ru)", () => {
  test.use({ viewport: VIEWPORTS.phone });

  test("finish from the palette sheet (phone, ru)", async ({ page }) => {
    const s = seed();
    await signIn(page, s.students["flow-phone-ru"]);
    const exam = new OrtExam(page, "ru");
    const counts = sectionCounts();
    await exam.openLobby();
    await exam.start();
    await exam.assertSection(1);

    await exam.showPalette();
    const finish = exam.finishButton(false);
    await expect(finish).toBeVisible();
    await expect(finish).toBeInViewport();
    // pinned: inside the sheet, but not inside its scrolling body (the palette alone scrolls)
    const pinned = await finish.evaluate((el) => {
      let p = el.parentElement;
      while (p && p.tagName !== "DIALOG") {
        if (["auto", "scroll"].includes(getComputedStyle(p).overflowY)) return false;
        p = p.parentElement;
      }
      return p?.tagName === "DIALOG";
    });
    expect(pinned).toBe(true);
    await expect(exam.palette().getByRole("button", { name: exam.t("player.finishSection") })).toHaveCount(0);

    await exam.openSectionEnd(1, { unanswered: counts[0], flagged: 0 });
    await expect(exam.paletteSheet()).toBeHidden();
    await exam.dialog().getByRole("button", { name: exam.t("player.sectionEnd.stay") }).click();
    await expect(exam.dialog()).toBeHidden();
    await expect(exam.paletteToggle()).toBeFocused();
    await exam.assertSection(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(VIEWPORTS.phone.width);
  });
});
