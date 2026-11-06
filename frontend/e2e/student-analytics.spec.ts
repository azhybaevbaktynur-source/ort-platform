import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * Student UI U6 (docs/phases/STUDENT_UI_DESIGN.md §3.3): the analytics page of the ORT (Russian) course, empty and
 * with data, at 375, 1440 and 1920 px; fails on sideways page scroll. The data student takes the seeded ORT exam
 * through the API. With UX_SCREENS_DIR set it also spreads that student's answers over the last weeks and gives the
 * bank questions topics, straight in the scratch e2e database, so the screenshots show full charts (run it alone:
 * the topics change other specs' data).
 */
const OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
const SIZES = [[375, 812], [1440, 900], [1920, 1080]] as const;

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

/** One submitted attempt: a mix of choices (some right, some wrong), every section closed in order. */
async function takeExam(user: SeedUser) {
  const s = seed();
  const st = (await api(user, "POST", `/courses/${s.course_id}/assessments/${s.exam.id}/attempts`, { language: "ru" })) as Started;
  let ts = 1000;
  const sections = st.sections.map((x) => x.pos).sort((a, b) => a - b);
  for (const pos of sections) {
    const content = await api(user, "GET", `/attempts/${st.id}/content?section=${pos}`);
    const answers = st.items.filter((i) => i.section_pos === pos).sort((a, b) => a.position - b.position).map((it, k) => {
      const q = content.questions[it.qv];
      ts += 1;
      if (q.type === "comparison") return { position: it.position, response: { choice: "ABCD"[k % 4] }, client_ts: ts };
      const order: string[] = it.choice_order ?? q.data.choices.map((c: { id: string }) => c.id);
      return { position: it.position, response: { choice_id: order[(k * 3) % order.length] }, client_ts: ts };
    });
    await api(user, "PUT", `/attempts/${st.id}/answers`, { answers });
    if (pos < sections.length) await api(user, "POST", `/attempts/${st.id}/sections/${pos}/close`, {});
  }
  await api(user, "POST", `/attempts/${st.id}/submit`, {});
}

/** Screens only: answers of `userId` spread over the last 40 days at different hours; bank questions get topics. */
function spreadInDb(userId: string, courseId: string) {
  const code = `
import sqlite3, sys, datetime
db, uid, cid = sys.argv[1], sys.argv[2], sys.argv[3]
con = sqlite3.connect(db)
cur = con.cursor()
rows = cur.execute("select i.rowid, i.answered_at from attempt_items i join attempts a on a.id = i.attempt_id "
                   "where a.user_id = ? and i.answered_at is not null order by i.position", (uid,)).fetchall()
now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
days = [0, 0, 1, 2, 2, 4, 5, 7, 9, 12, 15, 19, 23, 30, 38]
hours = [14, 15, 15, 16, 13, 14, 9, 15, 17, 14, 12, 15, 16, 10, 14]
for k, (iid, old) in enumerate(rows):
    d = days[k % len(days)] + 7 * (k // len(days))
    when = (now - datetime.timedelta(days=d)).replace(hour=hours[k % len(hours)], minute=(k * 7) % 50)
    if when > now:
        when -= datetime.timedelta(days=1)
    text = when.strftime("%Y-%m-%d %H:%M:%S.000000")
    if old and ("+" in str(old)[10:] or str(old).endswith("Z")):
        text += "+00:00"
    cur.execute("update attempt_items set answered_at = ? where rowid = ?", (text, iid))
topics = {"math_1": ["Дроби", "Проценты"], "math_2": ["Уравнения", "Геометрия"], "analogies": ["Синонимы", "Части целого"],
          "reading": ["Главная мысль", "Детали текста"], "grammar": ["Падежи", "Пунктуация"]}
for sec, names in topics.items():
    ids = [r[0] for r in cur.execute("select id from bank_questions where section = ? order by id", (sec,)).fetchall()]
    for n, qid in enumerate(ids):
        cur.execute("update bank_questions set topic = ? where id = ?", (names[n % len(names)], qid))
con.commit()
print(len(rows))
`;
  const out = execFileSync("python3", ["-I", "-c", code, path.join(E2E_DIR, "e2e.db"), userId, courseId], { encoding: "utf-8" });
  expect(Number(out.trim()), "answers moved").toBeGreaterThan(0);
}

async function noSideScroll(page: Page, name: string) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, `${name} scrolls sideways`).toBeLessThanOrEqual(0);
}

async function walk(browser: Browser, user: SeedUser, name: string, check: (page: Page) => Promise<void>) {
  const url = `/ru/courses/${seed().course_id}/progress`;
  for (const [w, h] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ru-RU", timezoneId: "UTC" });
    const page = await ctx.newPage();
    await signIn(page, user);
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1, name: tr("ru", "progress.analytics.title") })).toBeVisible();
    await settle(page);
    await check(page);
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0); // the period switch has reloaded
    await noSideScroll(page, `${name} at ${w}px`);
    if (OUT) await page.screenshot({ path: path.join(OUT, `${name}-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
    if (name === "analytics-data") {
      await page.goto(`${url}?tab=mistakes`);
      await settle(page);
      await noSideScroll(page, `mistakes at ${w}px`);
      if (OUT) await page.screenshot({ path: path.join(OUT, `analytics-mistakes-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true, animations: "disabled" });
    }
    await ctx.close();
  }
}

test.describe("student analytics", () => {
  test.describe.configure({ mode: "serial" });

  test("empty: designed empty states, no sideways scroll", async ({ browser }) => {
    if (OUT) fs.mkdirSync(OUT, { recursive: true });
    await walk(browser, seed().students["analytics-empty-ru"], "analytics-empty", async (page) => {
      await expect(page.getByText(tr("ru", "progress.analytics.empty.pageTitle"))).toBeVisible();
      await expect(page.getByText(tr("ru", "progress.analytics.empty.title")).first()).toBeVisible();
    });
  });

  test("with data: tiles, charts, period switch", async ({ browser }) => {
    const user = seed().students["analytics-data-ru"];
    await takeExam(user);
    if (OUT) spreadInDb(String(user.profile.id), seed().course_id);
    await walk(browser, user, "analytics-data", async (page) => {
      await expect(page.getByText(tr("ru", "progress.analytics.empty.pageTitle"))).toHaveCount(0);
      await expect(page.getByRole("img", { name: /Ответов за период/ })).toBeVisible();
      const year = page.getByRole("button", { name: tr("ru", "progress.analytics.period.d365") });
      await year.click();
      await expect(year).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByText(tr("ru", "progress.analytics.activity.byWeek"))).toBeVisible();
      await page.getByRole("button", { name: tr("ru", "progress.analytics.period.d30") }).click();
      await expect(page.getByText(tr("ru", "progress.analytics.activity.byDay"))).toBeVisible();
    });
  });
});
