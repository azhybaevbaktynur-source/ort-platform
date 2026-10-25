import { expect, type Locator, type Page } from "@playwright/test";
import { ORT_SECTIONS, sectionCounts, seed, tr, type Lang } from "./helpers";

/**
 * Drives the ORT exam as a student (lobby -> player -> result) with the DOM assertions of PHASE_6_DESIGN
 * section 6. Selectors are roles and the app's own i18n strings (CSS only for the passage line-number gutter,
 * which has no role).
 */
export class OrtExam {
  constructor(readonly page: Page, readonly lang: Lang) {}

  t(key: string, vars?: Record<string, string | number>) {
    return tr(this.lang, key, vars);
  }

  sectionName(pos: number) {
    return this.t(`sections.${ORT_SECTIONS[pos - 1]}`);
  }

  get lobbyPath() {
    const s = seed();
    return `/${this.lang}/courses/${s.course_id}/assessments/${s.exam.id}`;
  }

  // ---- lobby
  startButton() {
    return this.page.getByRole("button", { name: this.t("assessments.lobby.start"), exact: true });
  }

  async openLobby() {
    await this.page.goto(this.lobbyPath);
    await expect(this.startButton()).toBeVisible();
  }

  /** Five sections in ORT order with the seeded item counts, forward-only notice. */
  async assertLobby() {
    const list = this.page.locator("ol").filter({ hasText: this.sectionName(1) });
    const rows = list.locator("li");
    await expect(rows).toHaveCount(5);
    const counts = sectionCounts();
    for (let pos = 1; pos <= 5; pos++) {
      const row = rows.nth(pos - 1);
      await expect(row).toContainText(`${pos}. ${this.sectionName(pos)}`);
      await expect(row).toContainText(this.t("assessments.section.itemCount", { n: counts[pos - 1] }));
    }
    await expect(this.page.getByText(this.t("assessments.lobby.forwardOnly"))).toBeVisible();
  }

  async start() {
    await this.startButton().click();
    await this.page.waitForURL(/\/attempts\/[0-9a-f-]+$/);
    await this.withPalette(async () => {
      await expect(this.palette()).toBeVisible();
    });
  }

  // ---- player
  palette(): Locator {
    return this.page.getByRole("navigation", { name: this.t("player.palette.title") });
  }

  paletteButtons(): Locator {
    return this.palette().getByRole("button");
  }

  /** Phones and tablets (S7b, P1): the header button that opens the palette sheet. Hidden on desktop. */
  paletteToggle(): Locator {
    // accessible name "Question list: question n of total", any n / total
    const label = this.t("player.palette.openLabel", { n: 999, total: 999 });
    const pattern = label.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&").replace(/999/g, "\\d+");
    return this.page.locator("header").getByRole("button", { name: new RegExp(`^${pattern}$`) });
  }

  paletteSheet(): Locator {
    return this.page.getByRole("dialog", { name: this.t("player.palette.title") });
  }

  /** Make the palette visible: on phones open the sheet (and leave it open); on desktop it is always there. */
  async showPalette() {
    if (await this.paletteToggle().isVisible()) {
      if (!(await this.paletteSheet().isVisible())) await this.paletteToggle().click();
      await expect(this.paletteSheet()).toBeVisible();
    } else {
      await this.palette().scrollIntoViewIfNeeded();
    }
    await expect(this.palette()).toBeVisible();
  }

  /** Run palette checks; on phones inside the sheet, which is closed again unless it was already open. */
  async withPalette(fn: () => Promise<void>) {
    // the header is rendered once the attempt has loaded
    await expect(this.page.getByRole("progressbar", { name: this.t("player.progressBar") })).toBeVisible();
    const phone = await this.paletteToggle().isVisible();
    const wasOpen = phone && (await this.paletteSheet().isVisible());
    if (phone && !wasOpen) await this.showPalette();
    await fn();
    if (phone && !wasOpen) {
      await this.page.keyboard.press("Escape");
      await expect(this.paletteSheet()).toBeHidden();
    }
  }

  timer(): Locator {
    return this.page.getByRole("timer", { name: this.t("player.timer.label") });
  }

  question(): Locator {
    return this.page.locator("article");
  }

  answers(): Locator {
    return this.question().getByRole("radiogroup", { name: this.t("player.answers") }).getByRole("radio");
  }

  saved(): Locator {
    return this.page.getByText(this.t("player.save.saved"), { exact: true });
  }

  /** On phones the aside finish button lives in the palette sheet: open it first. */
  async openFinish() {
    if (await this.paletteToggle().isVisible()) await this.showPalette();
  }

  /**
   * The "finish section / finish test" button (present on every question): desktop in the side panel, phones in
   * the palette sheet's footer (S11a, F4). Only the visible one.
   */
  finishButton(last: boolean): Locator {
    const name = this.t(last ? "player.finishTest" : "player.finishSection");
    return this.page.locator("aside").or(this.paletteSheet()).getByRole("button", { name, exact: true }).filter({ visible: true });
  }

  dialog(): Locator {
    return this.page.getByRole("dialog");
  }

  /** Header: section name and "section n of 5"; palette: one button per item of the section; timer shown. */
  async assertSection(pos: number) {
    const header = this.page.locator("header").filter({ has: this.page.getByRole("progressbar") });
    await expect(header).toContainText(this.sectionName(pos));
    await expect(header).toContainText(this.t("player.sectionOf", { n: pos, total: 5 }));
    await this.withPalette(async () => {
      await expect(this.paletteButtons()).toHaveCount(sectionCounts()[pos - 1]);
    });
    await expect(this.timer()).toBeVisible();
    await expect(this.timer()).toHaveText(/^\d{1,2}:\d{2}(:\d{2})?$/);
  }

  async assertQuestionNumber(n: number, total: number) {
    await expect(this.question().getByRole("heading", { level: 2 })).toHaveText(this.t("player.questionOf", { n, total }));
  }

  /** math_1 comparison card: Column A and Column B, four answers A-D. */
  async assertComparison() {
    const q = this.question();
    await expect(q.getByText(this.t("player.comparison.columnA"), { exact: true })).toBeVisible();
    await expect(q.getByText(this.t("player.comparison.columnB"), { exact: true })).toBeVisible();
    const radios = this.answers();
    await expect(radios).toHaveCount(4);
    for (const [i, id] of ["A", "B", "C", "D"].entries()) {
      await expect(radios.nth(i)).toContainText(this.t(`bank.types.comparison.labels.${id}`));
    }
  }

  async choose(index: number) {
    const radio = this.answers().nth(index);
    await radio.click();
    await expect(radio).toHaveAttribute("aria-checked", "true");
    await expect(this.saved()).toBeVisible();
  }

  async toggleFlag(expectFlagged: boolean) {
    const name = this.t(expectFlagged ? "player.flag" : "player.unflag");
    await this.question().getByRole("button", { name }).click();
    await expect(this.question().getByRole("button", { name: this.t(expectFlagged ? "player.unflag" : "player.flag") }))
      .toHaveAttribute("aria-pressed", String(expectFlagged));
    await expect(this.saved()).toBeVisible();
  }

  async next() {
    await this.page.getByRole("button", { name: this.t("player.next") }).click();
  }

  /** Palette entry n: its accessible name tells answered / flagged; aria-current marks the shown question. */
  async assertPaletteEntry(n: number, state: { answered: boolean; flagged: boolean; current: boolean }) {
    let name = `${this.t("player.question")} ${n}`;
    if (state.answered) name += `, ${this.t("player.palette.answered")}`;
    if (state.flagged) name += `, ${this.t("player.palette.flagged")}`;
    await this.withPalette(async () => {
      const btn = this.paletteButtons().nth(n - 1);
      await expect(btn).toHaveAccessibleName(name);
      if (state.current) await expect(btn).toHaveAttribute("aria-current", "true");
      else await expect(btn).not.toHaveAttribute("aria-current", "true");
    });
  }

  /** Open the section-end dialog: title names the section, no-return warning, unanswered/flagged counts. */
  async openSectionEnd(pos: number, counts: { unanswered: number; flagged: number }) {
    await this.openFinish();
    await this.finishButton(false).click();
    const d = this.dialog();
    await expect(d).toBeVisible();
    await expect(d.getByRole("heading")).toHaveText(this.t("player.sectionEnd.title", { section: this.sectionName(pos) }));
    await expect(d).toContainText(this.t("player.sectionEnd.noReturn"));
    await expect(d).toContainText(this.t("player.counts.unanswered", { n: counts.unanswered }));
    await expect(d).toContainText(this.t("player.counts.flagged", { n: counts.flagged }));
  }

  async confirmSectionEnd(nextPos: number) {
    await this.dialog().getByRole("button", { name: this.t("player.sectionEnd.confirm") }).click();
    await expect(this.dialog()).toBeHidden();
    await this.assertSection(nextPos);
  }

  /** Close the current section without answering (sections the walk does not look at). */
  async skipSection(pos: number) {
    await this.assertSection(pos);
    await this.openSectionEnd(pos, { unanswered: sectionCounts()[pos - 1], flagged: 0 });
    await this.confirmSectionEnd(pos + 1);
  }

  /** Reading: the passage pane renders line numbers (every fifth line, or the passage's own [n] markers). */
  async assertPassage() {
    const pane = this.page.locator("section").filter({ has: this.page.locator("span.font-mono[aria-hidden='true']") }).first();
    await expect(pane).toBeVisible();
    const numbers = await pane.locator("span.font-mono[aria-hidden='true']").allInnerTexts();
    expect(numbers.length).toBeGreaterThan(0);
    const values = numbers.map((n) => Number(n.trim()));
    expect(values.every((v) => Number.isInteger(v) && v > 0)).toBe(true);
    expect(values).toEqual([...values].sort((a, b) => a - b));
    return pane;
  }

  async openSubmit(counts: { unanswered: number; flagged: number }) {
    await this.openFinish();
    await this.finishButton(true).click();
    const d = this.dialog();
    await expect(d).toBeVisible();
    await expect(d.getByRole("heading")).toHaveText(this.t("player.submit.title"));
    await expect(d).toContainText(this.t("player.submit.body"));
    await expect(d).toContainText(this.t("player.counts.unanswered", { n: counts.unanswered }));
    await expect(d).toContainText(this.t("player.counts.flagged", { n: counts.flagged }));
  }

  async confirmSubmit() {
    await this.dialog().getByRole("button", { name: this.t("player.submit.confirm") }).click();
    await this.page.waitForURL(/\/result(\?.*)?$/);
  }

  // ---- result
  /** Raw score, the scaled grade card, five section rows in ORT order plus the overall row. */
  async assertResult(raw: number, possible: number) {
    const summary = this.page.getByRole("region", { name: this.t("results.title") });
    await expect(summary).toBeVisible();
    await expect(summary).toContainText(this.t("results.rawScore"));
    await expect(summary).toContainText(`${raw}`);
    await expect(summary).toContainText(`/ ${possible}`);
    const grade = summary.getByRole("group", { name: this.t("results.grade.title") });
    await expect(grade).toBeVisible();
    await expect(grade.locator("p").nth(1)).toHaveText(/^\d+([.,]\d+)?/);
    const table = summary.locator("table");
    await expect(table.locator("caption")).toHaveText(this.t("results.grade.sectionsTitle"));
    const rows = table.locator("tbody tr");
    await expect(rows).toHaveCount(6);
    for (let pos = 1; pos <= 5; pos++) {
      await expect(rows.nth(pos - 1).locator("td").first()).toHaveText(this.sectionName(pos));
      await expect(rows.nth(pos - 1).locator("td").nth(1)).toContainText(`/ ${sectionCounts()[pos - 1]}`);
    }
    await expect(rows.nth(5).locator("td").first()).toHaveText(this.t("results.grade.overall"));
    return summary;
  }

  review(): Locator {
    return this.page.getByRole("region", { name: this.t("results.reviewTitle") });
  }
}
