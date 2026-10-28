import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContextOptions, type Locator, type Page, type TestInfo } from "@playwright/test";
import { expectScreen, seed, settle, signIn, tr, VIEWPORTS, type SeedUser, type ShotOptions, type ViewportName } from "./helpers";

/**
 * Phase 8b S3: the scrolling display mode of the general player (PHASE_8B_DESIGN 8, 12). A 48-item quiz (section 1:
 * 45 questions, section 2: a numbered passage with two questions and one more question) in free navigation: windows
 * of 30 with a visible "Show the next 15", the palette follows the scroll, a palette click scrolls to and focuses the
 * item, ArrowRight/ArrowLeft, F and 2 act on the item in view, answers given below the fold autosave, the timer runs,
 * "Next section" shows the passage once, finish, result and review with numbered lines. A forward-only scrolling quiz
 * closes its first section and lands on the second section's first item. A one-per-page quiz renders as before. At
 * 375 px with reduced motion: no horizontal scroll, the palette sheet jumps instantly. Baselines of the general player
 * are compared with docs/phases/PHASE_8B_screens/general-player/ (macOS; other platforms in a subfolder named after
 * `process.platform`, recorded on CI with ORT_BASELINE_RECORD_MISSING=1, as the ORT baselines).
 *
 * Data: `seed_backend.py` (`seed_scrolling`, after every ORT, quiz-editor and modules row): course "Курс прокрутки E2E"
 * of a third approved teacher with "Длинный тест E2E" (scrolling, free, 60 min, numbered passages), "Пошаговый тест
 * E2E" (scrolling, forward-only, 2 x 2 questions, 10 min each) and "Постраничный тест E2E" (one per page, 3
 * questions); one student per test.
 *
 * Run (same harness as the ORT specs, docs/phases/ORT_BASELINE/README.md "Run"):
 *   cd frontend && E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/scrolling-player.spec.ts
 * (in a git worktree add E2E_PYTHON=<main repo>/backend/venv/bin/python). UPDATE_BASELINES=1 re-records the
 * general-player baselines (run this spec alone, the variable applies to every baseline). With
 * PHASE8B_SCREENS_DIR=<dir> the last test also writes the UX-gate screenshots (docs/phases/PHASE_8B_screens/).
 */

type L3 = "ru" | "ky" | "en";
const L: L3 = "ru";
const t = (key: string, vars: Record<string, string | number> = {}, lang: L3 = L) => tr(lang, key, vars);

interface ScrollSeed {
  course_id: string;
  long_quiz: string;
  forward_quiz: string;
  page_quiz: string;
  teacher: SeedUser;
  students: Record<"walk" | "phone" | "forward" | "page" | "base" | "shots", SeedUser>;
}
const sc = (): ScrollSeed => (seed() as unknown as { scrolling: ScrollSeed }).scrolling;

const SCREENS = process.env.PHASE8B_SCREENS_DIR ? path.resolve(process.env.PHASE8B_SCREENS_DIR) : null;
const GENERAL_BASELINES = path.resolve(__dirname, "../../docs/phases/PHASE_8B_screens/general-player");

interface ItemState { position: number; section_pos: number; response: Record<string, unknown> | null; flagged: boolean }

async function api(user: SeedUser, p: string) {
  const r = await fetch(`${seed().api}/api/v1${p}`, { headers: { Authorization: `Bearer ${user.token}` } });
  expect(r.status, p).toBe(200);
  return r.json();
}

async function studentPage(browser: Browser, user: SeedUser, vp: ViewportName = "desktop", extra: BrowserContextOptions = {}, lang: L3 = L): Promise<Page> {
  const ctx = await browser.newContext({
    viewport: VIEWPORTS[vp], locale: lang === "en" ? "en-US" : lang === "ky" ? "ky-KG" : "ru-RU", timezoneId: "UTC", colorScheme: "light", ...extra,
  });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

/** Lobby -> Start -> player; the attempt id and its items sorted by position. */
async function start(page: Page, user: SeedUser, quizId: string, lang: L3 = L): Promise<{ attemptId: string; items: ItemState[] }> {
  await page.goto(`/${lang}/courses/${sc().course_id}/assessments/${quizId}`);
  await page.getByRole("button", { name: t("assessments.lobby.start", {}, lang) }).click();
  await page.waitForURL(/\/attempts\/[0-9a-f-]{36}$/);
  const attemptId = /\/attempts\/([0-9a-f-]{36})/.exec(page.url())![1];
  const state = await api(user, `/attempts/${attemptId}`);
  const items = [...(state.items as ItemState[])].sort((a, b) => a.position - b.position);
  return { attemptId, items };
}

const listItems = (page: Page) => page.locator('section[id^="item-"]');
const item = (page: Page, pos: number) => page.locator(`#item-${pos}`);
const choice = (page: Page, pos: number, n: number) => item(page, pos).getByRole("radio").nth(n);
const desktopPalette = (page: Page, lang: L3 = L) => page.getByRole("navigation", { name: t("player.palette.title", {}, lang) });
const paletteButton = (scope: Locator, label: number, lang: L3 = L) =>
  scope.getByRole("button", { name: new RegExp(`^${t("player.question", {}, lang)} ${label}(,|$)`) });
const scrollRoot = (page: Page) => page.locator("div.fixed.inset-0.overflow-y-auto").first();

/** Scroll an item under the header the way a reader does (no focus change, no palette). */
async function readerScrollTo(page: Page, pos: number) {
  await item(page, pos).evaluate((el) => el.scrollIntoView({ block: "start" }));
}

async function finishTest(page: Page) {
  await page.getByRole("button", { name: t("player.finishTest") }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: t("player.submit.confirm") }).click();
  await page.waitForURL(/\/result/);
}

/** Compare with the general-player baselines (same comparison as the ORT baselines, another folder). */
async function expectGeneral(page: Page, info: TestInfo, name: string, opts: ShotOptions = {}) {
  const prev = process.env.ORT_BASELINE_DIR;
  process.env.ORT_BASELINE_DIR = process.platform === "darwin" ? GENERAL_BASELINES : path.join(GENERAL_BASELINES, process.platform);
  try {
    await expectScreen(page, info, name, opts);
  } finally {
    if (prev === undefined) delete process.env.ORT_BASELINE_DIR;
    else process.env.ORT_BASELINE_DIR = prev;
  }
}

test.describe("scrolling display mode (general player)", () => {
  test("48-item quiz: windowing, palette and keyboard follow the viewport, autosave across scroll, timer, submit, result", async ({ browser }) => {
    const s = sc();
    const user = s.students.walk;
    const page = await studentPage(browser, user);
    const { attemptId, items } = await start(page, user, s.long_quiz);
    expect(items).toHaveLength(48);
    const sec1 = items.filter((i) => i.section_pos === items[0].section_pos);
    const sec2 = items.filter((i) => i.section_pos !== items[0].section_pos);
    expect(sec1).toHaveLength(45);
    expect(sec2).toHaveLength(3);
    const p = (n: number) => sec1[n - 1].position; // section-1 question n (1-based)

    // ---- first window: 30 items mounted, the footer says where we are and offers the next 15
    await expect(listItems(page)).toHaveCount(30);
    await expect(page.getByText(t("player.scrolling.windowOf", { from: 1, to: 30, total: 45 }))).toBeVisible();
    await expect(page.getByRole("button", { name: t("player.scrolling.showNext", { n: 15 }) })).toBeVisible();
    await expect(item(page, p(1))).toHaveAttribute("aria-current", "true");
    await expect(item(page, p(1)).getByRole("heading", { name: t("player.questionOf", { n: 1, total: 48 }) })).toBeVisible();
    await expect(page.getByRole("timer")).toBeVisible();
    await expect(page.getByRole("timer")).toHaveText(/\d{1,2}:\d{2}/);
    const palette = desktopPalette(page);
    await expect(palette.locator('button[aria-current="true"]')).toHaveText("1");

    // ---- answer item 1, scroll like a reader to item 10: the palette highlight follows, answer it below the fold
    await choice(page, p(1), 1).click();
    await readerScrollTo(page, p(10));
    await expect(item(page, p(10))).toHaveAttribute("aria-current", "true");
    await expect(palette.locator('button[aria-current="true"]')).toHaveText("10");
    await choice(page, p(10), 1).click();
    await readerScrollTo(page, p(25));
    await expect(palette.locator('button[aria-current="true"]')).toHaveText("25");
    await choice(page, p(25), 1).click();

    // ---- palette click scrolls to item 20 and focuses it
    await paletteButton(palette, 20).click();
    await expect(item(page, p(20))).toBeFocused();
    await expect(item(page, p(20))).toBeInViewport();
    await expect(item(page, p(20))).toHaveAttribute("aria-current", "true");

    // ---- keyboard acts on the item in view: ArrowRight moves to 21, F flags it, 2 answers it, ArrowLeft back to 20
    await page.keyboard.press("ArrowRight");
    await expect(item(page, p(21))).toBeFocused();
    await expect(item(page, p(21))).toBeInViewport();
    await page.keyboard.press("KeyF");
    await expect(item(page, p(21)).getByRole("button", { name: t("player.unflag") })).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("Digit2");
    await expect(choice(page, p(21), 1)).toHaveAttribute("aria-checked", "true");
    await expect(choice(page, p(20), 1)).toHaveAttribute("aria-checked", "false");
    await page.keyboard.press("ArrowLeft");
    await expect(item(page, p(20))).toBeFocused();

    // ---- autosave: every answer given across the scroll reaches the server
    await expect(page.getByRole("status").filter({ hasText: t("player.save.saved") })).toBeVisible({ timeout: 20_000 });
    await expect.poll(async () => {
      const st = await api(user, `/attempts/${attemptId}`);
      const byPos = new Map((st.items as ItemState[]).map((i) => [i.position, i]));
      return [1, 10, 21, 25].map((n) => !!byPos.get(p(n))?.response) .concat([!!byPos.get(p(21))?.flagged]);
    }, { timeout: 20_000 }).toEqual([true, true, true, true, true]);

    // ---- the second window: "Show the next 15" mounts items 31-45 only; "Show the previous 30" goes back
    await page.getByRole("button", { name: t("player.scrolling.showNext", { n: 15 }) }).click();
    await expect(item(page, p(31))).toBeFocused();
    await expect(listItems(page)).toHaveCount(15);
    await expect(item(page, p(1))).toHaveCount(0);
    await expect(page.getByText(t("player.scrolling.windowOf", { from: 31, to: 45, total: 45 }))).toBeVisible();
    await expect(page.getByRole("button", { name: t("player.scrolling.showPrevious", { n: 30 }) })).toBeVisible();
    // a palette target outside the window moves the window first
    await paletteButton(palette, 5).click();
    await expect(item(page, p(5))).toBeFocused();
    await expect(listItems(page)).toHaveCount(30);
    await paletteButton(palette, 40).click();
    await expect(item(page, p(40))).toBeFocused();

    // ---- next section: the passage is shown once above its two questions, with numbered lines
    await page.getByRole("button", { name: t("player.scrolling.nextSection") }).click();
    await expect(item(page, sec2[0].position)).toBeFocused();
    await expect(listItems(page)).toHaveCount(3);
    const passage = page.locator('section[id^="passage-"]');
    await expect(passage).toHaveCount(1);
    await expect(passage).toContainText("пик Победы");
    await expect(passage.locator("span.font-mono").filter({ hasText: "5" })).toBeVisible();
    await expect(page.getByRole("button", { name: t("player.scrolling.previousSection") })).toBeVisible();
    await choice(page, sec2[0].position, 1).click();

    // ---- finish from the footer, result with five correct answers, review with numbered passage lines
    await expect(page.getByRole("status").filter({ hasText: t("player.save.saved") })).toBeVisible({ timeout: 20_000 });
    await finishTest(page);
    await expect(page.getByRole("heading", { name: t("results.title") })).toBeVisible();
    const result = await api(user, `/attempts/${attemptId}/result`);
    expect(Number(result.raw_score)).toBe(5);
    expect(result.passage_display).toBe("numbered");
    const review = page.getByRole("region", { name: t("results.reviewTitle") });
    const reviewPassage = review.locator("article details").filter({ hasText: "Текст о горах" }).first();
    await reviewPassage.locator("summary").click();
    await expect(reviewPassage.locator("span.font-mono").filter({ hasText: "5" })).toBeVisible();
    await page.context().close();
  });

  test("forward-only scrolling: closing a section lands on the next section's first item", async ({ browser }) => {
    const s = sc();
    const user = s.students.forward;
    const page = await studentPage(browser, user);
    const { attemptId, items } = await start(page, user, s.forward_quiz);
    const first = items.filter((i) => i.section_pos === items[0].section_pos);
    const second = items.filter((i) => i.section_pos !== items[0].section_pos);
    await expect(listItems(page)).toHaveCount(2);
    await expect(page.locator("header").getByText("Этап 1")).toBeVisible();
    await expect(page.getByRole("timer")).toBeVisible();
    await choice(page, first[0].position, 1).click();
    await choice(page, first[1].position, 1).click();
    await page.getByRole("button", { name: t("player.finishSection") }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: t("player.sectionEnd.confirm") }).click();
    await expect(page.locator("header").getByText("Этап 2")).toBeVisible();
    await expect(listItems(page)).toHaveCount(2);
    await expect(item(page, second[0].position)).toHaveAttribute("aria-current", "true");
    await expect.poll(() => scrollRoot(page).evaluate((el) => el.scrollTop)).toBe(0);
    const st = await api(user, `/attempts/${attemptId}`);
    expect(st.current_section_pos).toBe(second[0].section_pos);
    await choice(page, second[0].position, 1).click();
    await finishTest(page);
    const result = await api(user, `/attempts/${attemptId}/result`);
    expect(Number(result.raw_score)).toBe(3);
    await page.context().close();
  });

  test("one question per page is unchanged", async ({ browser }) => {
    const s = sc();
    const user = s.students.page;
    const page = await studentPage(browser, user);
    const { attemptId } = await start(page, user, s.page_quiz);
    await expect(listItems(page)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: t("player.questionOf", { n: 1, total: 3 }) })).toBeVisible();
    await expect(page.getByText(t("player.scrolling.windowOf", { from: 1, to: 3, total: 3 }))).toHaveCount(0);
    await page.getByRole("radiogroup", { name: t("player.answers") }).getByRole("radio").nth(1).click();
    await page.getByRole("button", { name: t("player.next") }).click();
    await expect(page.getByRole("heading", { name: t("player.questionOf", { n: 2, total: 3 }) })).toBeVisible();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("heading", { name: t("player.questionOf", { n: 3, total: 3 }) })).toBeVisible();
    await expect(page.getByRole("button", { name: t("player.prev") })).toBeEnabled();
    const state = await api(user, `/attempts/${attemptId}`);
    expect(state.display_mode).toBe("one_per_page");
    await finishTest(page);
    await expect(page.getByRole("heading", { name: t("results.title") })).toBeVisible();
    await page.context().close();
  });

  test("375 px, reduced motion: no horizontal scroll, the palette sheet jumps instantly", async ({ browser }) => {
    const s = sc();
    const user = s.students.phone;
    const page = await studentPage(browser, user, "phone", { reducedMotion: "reduce", hasTouch: true });
    const { items } = await start(page, user, s.long_quiz);
    await expect(listItems(page)).toHaveCount(30);
    await settle(page);
    const overflow = await page.evaluate(() => {
      const root = document.querySelector("div.fixed.inset-0.overflow-y-auto") as HTMLElement;
      return { doc: document.documentElement.scrollWidth - window.innerWidth, root: root.scrollWidth - root.clientWidth };
    });
    expect(overflow.doc).toBeLessThanOrEqual(0);
    expect(overflow.root).toBeLessThanOrEqual(0);
    await expect(page.getByRole("button", { name: t("player.scrolling.showNext", { n: 15 }) })).toBeInViewport();

    await page.getByRole("button", { name: t("player.palette.openLabel", { n: 1, total: 48 }) }).click();
    const sheet = page.getByRole("dialog", { name: t("player.palette.title") });
    await expect(sheet).toBeVisible();
    await paletteButton(sheet, 12).click();
    await expect(sheet).toBeHidden();
    const target = item(page, items[11].position);
    await expect(target).toBeFocused();
    // reduced motion: the jump is instant, the item sits right under the sticky header
    const gap = await page.evaluate((pos) => {
      const header = document.querySelector("div.fixed.inset-0 header") as HTMLElement;
      const el = document.getElementById(`item-${pos}`) as HTMLElement;
      return el.getBoundingClientRect().top - header.getBoundingClientRect().bottom;
    }, items[11].position);
    expect(gap).toBeGreaterThanOrEqual(0);
    expect(gap).toBeLessThanOrEqual(12);
    await expect(page.getByRole("button", { name: t("player.palette.openLabel", { n: 12, total: 48 }) })).toBeVisible();
    await choice(page, items[11].position, 1).click();
    await expect(choice(page, items[11].position, 1)).toHaveAttribute("aria-checked", "true");
    await page.context().close();
  });

  test("general player baselines (scrolling and one per page, ru)", async ({ browser }, info) => {
    const s = sc();
    const user = s.students.base;
    for (const [quiz, name, count] of [[s.long_quiz, "scrolling-top", 30], [s.page_quiz, "one-per-page", 0]] as const) {
      const first = await studentPage(browser, user);
      const { attemptId } = await start(first, user, quiz);
      await first.context().close();
      for (const vp of ["desktop", "phone"] as const) {
        const page = await studentPage(browser, user, vp);
        await page.goto(`/${L}/courses/${s.course_id}/attempts/${attemptId}`);
        await expect(page.getByRole("heading", { name: t("player.questionOf", { n: 1, total: quiz === s.long_quiz ? 48 : 3 }) })).toBeVisible();
        await expect(listItems(page)).toHaveCount(count);
        await expectGeneral(page, info, `${name}-${vp}-${L}`, { mask: [page.getByRole("timer")] });
        await page.context().close();
      }
    }
  });

  test("UX-gate screenshots (PHASE8B_SCREENS_DIR)", async ({ browser }) => {
    test.skip(!SCREENS, "set PHASE8B_SCREENS_DIR to write the UX-gate screenshots");
    const dir = SCREENS!;
    fs.mkdirSync(dir, { recursive: true });
    const s = sc();
    const user = s.students.shots;
    const shot = async (page: Page, name: string, opts: { element?: Locator; fullPage?: boolean } = {}) => {
      await settle(page);
      const o = { animations: "disabled" as const, caret: "hide" as const };
      const buf = opts.element ? await opts.element.screenshot(o) : await page.screenshot({ ...o, fullPage: !!opts.fullPage });
      fs.writeFileSync(path.join(dir, `${name}.png`), buf);
    };

    // a few answers and a flag first, so the palette shows its states
    const setup = await studentPage(browser, user);
    const { attemptId, items } = await start(setup, user, s.long_quiz);
    for (const n of [0, 1, 2, 4]) await choice(setup, items[n].position, 1).click();
    await item(setup, items[1].position).getByRole("button", { name: t("player.flag") }).click();
    await expect(setup.getByRole("status").filter({ hasText: t("player.save.saved") })).toBeVisible({ timeout: 20_000 });
    await setup.context().close();

    const playerUrl = (lang: L3) => `/${lang}/courses/${s.course_id}/attempts/${attemptId}`;
    for (const lang of ["ru", "ky", "en"] as const) {
      for (const vp of ["desktop", "phone"] as const) {
        const page = await studentPage(browser, user, vp, {}, lang);
        await page.goto(playerUrl(lang));
        await expect(listItems(page)).toHaveCount(30);
        await shot(page, `scrolling-top-${vp}-${lang}`);
        if (vp === "desktop") await paletteButton(desktopPalette(page, lang), 12, lang).click();
        else await readerScrollTo(page, items[11].position);
        await expect(item(page, items[11].position)).toHaveAttribute("aria-current", "true");
        await page.waitForTimeout(700);
        await shot(page, `scrolling-mid-${vp}-${lang}`);
        await readerScrollTo(page, items[29].position);
        await page.waitForTimeout(300);
        await shot(page, `scrolling-footer-${vp}-${lang}`);
        if (vp === "phone") {
          await page.locator('header button[aria-haspopup="dialog"]').click();
          await expect(page.getByRole("dialog", { name: t("player.palette.title", {}, lang) })).toBeVisible();
          await shot(page, `scrolling-sheet-phone-${lang}`);
          await page.keyboard.press("Escape");
          await expect(page.getByRole("dialog")).toBeHidden();
        }
        await page.getByRole("button", { name: t("player.scrolling.showNext", { n: 15 }, lang) }).click();
        await page.getByRole("button", { name: t("player.scrolling.nextSection", {}, lang) }).click();
        await expect(page.locator('section[id^="passage-"]')).toBeVisible();
        await page.waitForTimeout(700);
        await shot(page, `scrolling-passage-${vp}-${lang}`);
        await page.context().close();
      }
    }

    // submit, then the result and the review with the numbered passage
    const done = await studentPage(browser, user);
    await done.goto(playerUrl("ru"));
    await expect(listItems(done)).toHaveCount(30);
    await finishTest(done);
    await done.context().close();
    for (const lang of ["ru", "ky", "en"] as const) {
      for (const vp of ["desktop", "phone"] as const) {
        const page = await studentPage(browser, user, vp, {}, lang);
        await page.goto(`${playerUrl(lang)}/result`);
        await expect(page.getByRole("heading", { name: t("results.title", {}, lang) })).toBeVisible();
        await shot(page, `result-${vp}-${lang}`);
        const reviewPassage = page.getByRole("region", { name: t("results.reviewTitle", {}, lang) }).locator("article details").filter({ hasText: "Текст о горах" }).first();
        await reviewPassage.locator("summary").click();
        await reviewPassage.evaluate((el) => el.closest("article")?.scrollIntoView({ block: "start" }));
        await shot(page, `review-passage-${vp}-${lang}`);
        await page.context().close();
      }
    }

    // the teacher's "Display" group in the quiz editor's Settings tab (ru, en)
    for (const lang of ["ru", "en"] as const) {
      for (const vp of ["desktop", "phone"] as const) {
        const page = await studentPage(browser, s.teacher, vp, {}, lang);
        await page.goto(`/${lang}/courses/${s.course_id}/assessments/${s.long_quiz}/edit`);
        await page.getByRole("tab", { name: t("quizEditor.tabs.settings", {}, lang) }).click();
        const group = page.locator("fieldset").filter({ has: page.locator("legend", { hasText: t("assessments.settings.display.group", {}, lang) }) }).first();
        await expect(group).toBeVisible();
        await expect(group.getByRole("radio", { name: new RegExp(t("assessments.settings.display.displayMode.options.scrolling.title", {}, lang)) })).toBeChecked();
        await group.scrollIntoViewIfNeeded();
        await shot(page, `settings-display-${vp}-${lang}`, { element: group });
        await page.context().close();
      }
    }
  });
});
