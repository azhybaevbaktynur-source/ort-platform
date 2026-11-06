import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * Student UI U8 (docs/phases/STUDENT_UI_DESIGN.md §3.4, §3.6, §5.1): Сохранённые (flagged questions and the mistakes
 * notebook, `/progress?tab=mistakes` redirects there), the history-only analytics cards, the "Начало работы" checklist
 * (sidebar pill, phone "More", home card), the practice list and /unlock in the student shell, at 375, 1440 and 1920 px
 * in ru; fails on sideways page scroll. One student without flags, one who takes the seeded ORT exam through the API and
 * flags three questions. With UX_SCREENS_DIR set it saves the screens there and adds a practice set to the ORT course
 * (run it alone then: that set changes what other specs see).
 */
const OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
const SIZES = [[375, 812], [1440, 900], [1920, 1080]] as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);

async function api(user: SeedUser, method: string, p: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method, headers: { Authorization: `Bearer ${user.token}`, "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(r.status, `${method} ${p}: ${text.slice(0, 300)}`).toBeLessThan(300);
  return text ? JSON.parse(text) : null;
}

type Started = { id: string; sections: { pos: number }[]; items: { section_pos: number; position: number; qv: string; choice_order?: string[] | null }[] };

/** One submitted attempt with every third question flagged (some right, some wrong answers). */
async function takeExamWithFlags(user: SeedUser) {
  const s = seed();
  const st = (await api(user, "POST", `/courses/${s.course_id}/assessments/${s.exam.id}/attempts`, { language: "ru" })) as Started;
  let ts = 1000;
  const sections = st.sections.map((x) => x.pos).sort((a, b) => a - b);
  for (const pos of sections) {
    const content = await api(user, "GET", `/attempts/${st.id}/content?section=${pos}`);
    const answers = st.items.filter((i) => i.section_pos === pos).sort((a, b) => a.position - b.position).map((it, k) => {
      const q = content.questions[it.qv];
      ts += 1;
      const flagged = it.position % 3 === 1;
      if (q.type === "comparison") return { position: it.position, response: { choice: "ABCD"[k % 4] }, flagged, client_ts: ts };
      const order: string[] = it.choice_order ?? q.data.choices.map((c: { id: string }) => c.id);
      return { position: it.position, response: { choice_id: order[(k * 3) % order.length] }, flagged, client_ts: ts };
    });
    await api(user, "PUT", `/attempts/${st.id}/answers`, { answers });
    if (pos < sections.length) await api(user, "POST", `/attempts/${st.id}/sections/${pos}/close`, {});
  }
  await api(user, "POST", `/attempts/${st.id}/submit`, {});
}

async function noSideScroll(page: Page, name: string) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, `${name} scrolls sideways`).toBeLessThanOrEqual(0);
}

async function shot(page: Page, name: string) {
  if (OUT) await page.screenshot({ path: path.join(OUT, `${name}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
}

/** Each size in its own context: signed in, then `check(page, width)`. */
async function sizes(browser: Browser, user: SeedUser, check: (page: Page, w: number) => Promise<void>) {
  for (const [w, h] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ru-RU", timezoneId: "UTC" });
    const page = await ctx.newPage();
    await signIn(page, user);
    await check(page, w);
    await ctx.close();
  }
}

const savedUrl = () => `/ru/courses/${seed().course_id}/saved`;

test.describe("student saved, checklist, practice, unlock (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("empty: both tabs, getting started in the sidebar, More and on the home", async ({ browser }) => {
    if (OUT) fs.mkdirSync(OUT, { recursive: true });
    const user = seed().students["saved-empty-ru"];
    await sizes(browser, user, async (page, w) => {
      await page.goto(savedUrl());
      await expect(page.getByRole("heading", { level: 1, name: t("student.saved.title") })).toBeVisible();
      await expect(page.getByText(t("student.saved.empty"))).toBeVisible();
      const nav = w >= 1024 ? page.getByRole("navigation", { name: t("student.nav.label") }) : null;
      if (nav) {
        await expect(nav.getByRole("link", { name: t("student.nav.saved") })).toHaveAttribute("aria-current", "page");
        await expect(nav.getByRole("link", { name: t("student.nav.mistakes") })).toHaveCount(0);
      }
      await settle(page);
      await noSideScroll(page, `saved empty at ${w}px`);
      await shot(page, `saved-empty-${w}`);
      await page.getByRole("tab", { name: t("student.saved.tabs.mistakes") }).click();
      await page.waitForURL(/\/saved\?tab=mistakes$/);
      await expect(page.getByText(t("progress.mistakes.emptyOpen"))).toBeVisible();
      await settle(page);
      await noSideScroll(page, `mistakes empty at ${w}px`);
      await shot(page, `mistakes-empty-${w}`);

      // getting started: the home card and the pill (sidebar on desktop, "More" on phones) open the checklist
      await page.goto("/ru/courses");
      await expect(page.getByRole("heading", { level: 2, name: t("student.nav.gettingStarted") })).toBeVisible();
      const pillName = new RegExp(`^${t("student.nav.gettingStarted")}\\s*\\d/\\d$`);
      if (w >= 1024) {
        await page.getByRole("button", { name: pillName }).click();
      } else {
        await page.getByRole("navigation", { name: t("student.nav.tabBar") }).getByRole("button", { name: t("student.nav.more") }).click();
        const more = page.getByRole("dialog", { name: t("student.nav.more") });
        await more.getByRole("button", { name: pillName }).click();
        await expect(more).toBeHidden();
      }
      const sheet = page.getByRole("dialog", { name: t("student.nav.gettingStarted") });
      await expect(sheet).toBeVisible();
      await expect(sheet.getByRole("link", { name: new RegExp(t("student.gettingStarted.items.test")) })).toHaveAttribute("href", `/ru/courses/${seed().course_id}/tests`);
      await settle(page);
      await noSideScroll(page, `getting started at ${w}px`);
      await shot(page, `getting-started-${w}`);
      await page.keyboard.press("Escape");
      await expect(sheet).toBeHidden();
    });
  });

  test("with data: flagged rows open the review; analytics without history hides the history cards", async ({ browser }) => {
    const user = seed().students["saved-data-ru"];
    await takeExamWithFlags(user);
    if (OUT) {
      // screens only: a practice set in the ORT course, so the practice list has a card
      const s = seed();
      await api(s.admin, "POST", `/courses/${s.course_id}/practice`, {
        title: { ru: "Математика: сравнение" }, languages: ["ru"],
        blocks: [{ bank_id: s.bank_id, count: 2, section: "math_1" }, { bank_id: s.bank_id, count: 2, section: "math_2" }],
      });
    }
    await sizes(browser, user, async (page, w) => {
      await page.goto(savedUrl());
      await expect(page.getByRole("heading", { level: 1, name: t("student.saved.title") })).toBeVisible();
      const open = page.locator("main").getByRole("link", { name: new RegExp(`^${t("student.saved.open")}\\s*: `) });
      await expect(open.first()).toBeVisible();
      await expect(open.first()).toHaveAttribute("href", new RegExp(`/attempts/[0-9a-f-]{36}/result#item-\\d+$`));
      await settle(page);
      await noSideScroll(page, `saved at ${w}px`);
      await shot(page, `saved-data-${w}`);
      await page.getByRole("tab", { name: t("student.saved.tabs.mistakes") }).click();
      await page.waitForURL(/\/saved\?tab=mistakes$/);
      await settle(page);
      await noSideScroll(page, `mistakes at ${w}px`);
      await shot(page, `mistakes-data-${w}`);

      // one day of answers: no study time, active hours or sessions card (not even an empty one)
      await page.goto(`/ru/courses/${seed().course_id}/progress`);
      await expect(page.getByRole("heading", { level: 1, name: t("progress.analytics.title") })).toBeVisible();
      await expect(page.getByRole("img", { name: /Ответов за период/ })).toBeVisible();
      for (const k of ["time", "hours", "sessions"]) await expect(page.getByText(t(`progress.analytics.${k}.title`), { exact: true })).toHaveCount(0);
      await settle(page);
      await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
      await noSideScroll(page, `analytics at ${w}px`);
      await shot(page, `analytics-little-${w}`);

      await page.goto(`/ru/courses/${seed().course_id}/practice`);
      await expect(page.getByRole("heading", { level: 1, name: t("practice.title") })).toBeVisible();
      await settle(page);
      await noSideScroll(page, `practice at ${w}px`);
      await shot(page, `practice-${w}`);

      await page.goto("/ru/unlock");
      await expect(page.getByRole("heading", { level: 1, name: t("access.unlock.title") })).toBeVisible();
      // inside the student shell: its navigation, not the AppHeader's areas
      const shellNav = w >= 1024 ? t("student.nav.label") : t("student.nav.tabBar");
      await expect(page.getByRole("navigation", { name: shellNav })).toBeVisible();
      await settle(page);
      await noSideScroll(page, `unlock at ${w}px`);
      await shot(page, `unlock-${w}`);
    });
  });
});
