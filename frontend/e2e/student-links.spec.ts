import { expect, test, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * SF-1 F3 (docs/phases/STUDENT_UI_FIX_PLAN.md §3): the link audit of the student area. Every new student page (home,
 * Тесты, Аналитика, Повторение with both tabs, Видеоуроки, Практика, /pro, a result) is opened, and every internal
 * link on it is visited: each must land on a page inside the student frame (`.student-theme`; the player route has
 * only that frame) without the old course header, breadcrumbs or "Назад к заданию". The rows of Повторение and of
 * Ошибки land on the review card `#item-n`, in view.
 *
 * Data: `links-ru` takes the seeded ORT exam through the API with every third question flagged.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
/** Public pages outside the signed-in app (no student frame by design). */
const PUBLIC = new Set([`/${L}`, `/${L}/about`, `/${L}/help`, `/${L}/contacts`, `/${L}/for-teachers`, `/${L}/for-teachers/apply`]);
const PLAYER = /^\/[a-z]{2}\/courses\/[^/]+\/attempts\/[^/]+$/;

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

/** One submitted attempt with every third question flagged (some right, some wrong answers); returns its id. */
async function takeExamWithFlags(user: SeedUser): Promise<string> {
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
  return st.id;
}

/** The page has finished loading (no loading line, network quiet). */
async function loaded(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(t("lms.common.loading"), { exact: true })).toHaveCount(0);
}

/** Internal links of the open page (path + query, no hash-only links, no API or downloads), sorted. */
async function internalLinks(page: Page): Promise<string[]> {
  const hrefs = await page.locator("a[href]").evaluateAll((els) => els.map((a) => (a as HTMLAnchorElement).href));
  const out = new Set<string>();
  for (const h of hrefs) {
    const u = new URL(h);
    if (u.origin !== new URL(page.url()).origin) continue;
    if (u.pathname.startsWith("/api/") || u.pathname.startsWith("/_next/")) continue;
    out.add(u.pathname + u.search);
  }
  return [...out].sort();
}

/** The landing page is in the student frame and shows none of the old frame's parts. */
async function assertStudentFrame(page: Page, from: string, href: string) {
  const at = new URL(page.url()).pathname;
  const why = `${href} (linked from ${from}, landed on ${at})`;
  await expect(page.locator(".student-theme").first(), why).toBeAttached();
  if (!PLAYER.test(at)) {
    await expect(page.getByRole("navigation", { name: t("ui.breadcrumbs") }), why).toHaveCount(0);
    await expect(page.getByRole("link", { name: t("results.back"), exact: true }), why).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: t("courses.home.tabsLabel") }), why).toHaveCount(0);
  }
}

test.describe("student link audit (ru)", () => {
  test.use({ viewport: VIEWPORTS.desktop });

  test("every link from the new student pages lands in the student frame; saved and mistakes rows land on #item-n", async ({ page }) => {
    test.setTimeout(600_000);
    const s = seed();
    const c = `/${L}/courses/${s.course_id}`;
    const user = s.students["links-ru"];
    const attemptId = await takeExamWithFlags(user);
    await signIn(page, user);

    const pages = [
      `/${L}/home`, `/${L}/courses`, `${c}/tests`, `${c}/progress`, // step 3a S7: /courses redirects to the hub
      `${c}/saved`, `${c}/saved?tab=mistakes`, `${c}/modules`,
      `${c}/practice`, `/${L}/pro`, `${c}/attempts/${attemptId}/result`,
      `/${L}/courses/choose?first=1`, `/${L}/courses/catalog?welcome=1`, // step 3a S7: the old step redirects; the catalog
    ];
    const visited = new Set<string>();
    for (const from of pages) {
      await page.goto(from);
      await loaded(page);
      await assertStudentFrame(page, "(start)", from);
      const links = await internalLinks(page);
      expect(links.length, `no links on ${from}`).toBeGreaterThan(0);
      for (const href of links) {
        if (visited.has(href) || PUBLIC.has(href.split("?")[0])) continue;
        visited.add(href);
        await page.goto(href);
        await loaded(page);
        await assertStudentFrame(page, from, href);
      }
    }

    // ---- Повторение: a flagged row lands on its review card
    await page.goto(`${c}/saved`);
    await loaded(page);
    const open = page.locator("main").getByRole("link", { name: new RegExp(`^${t("student.saved.open")}\\s*: `) }).first();
    const savedHref = await open.getAttribute("href");
    expect(savedHref).toMatch(/\/result#item-\d+$/);
    await open.click();
    await page.waitForURL(/\/result#item-\d+$/);
    await expect(page.locator(`#item-${savedHref!.split("#item-")[1]}`)).toBeInViewport();
    await settle(page);

    // ---- Ошибки: a mistake row lands on its review card
    await page.goto(`${c}/saved?tab=mistakes`);
    await loaded(page);
    const mistake = page.locator("main").getByRole("link", { name: t("progress.mistakes.viewAttempt") }).first();
    const mistakeHref = await mistake.getAttribute("href");
    expect(mistakeHref).toMatch(/\/result#item-\d+$/);
    await mistake.click();
    await page.waitForURL(/\/result#item-\d+$/);
    await expect(page.locator(`#item-${mistakeHref!.split("#item-")[1]}`)).toBeInViewport();
  });
});
