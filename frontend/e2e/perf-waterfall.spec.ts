import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { E2E_DIR, seed, signIn, type SeedUser } from "./helpers";

/**
 * PERFORMANCE_AUDIT (owner round 2026-11-09 item 1): the network waterfall, the time to first content and the shell
 * swaps of the main pages, on two profiles (laptop: 1440 px, no throttling; phone: 390 px, 4x CPU slowdown, Slow 4G
 * 400 kbit/s / 400 ms RTT), each page loaded cold (a fresh browser context: no sessionStorage, empty HTTP cache),
 * warm (a second load in the same context) and, where the shell has a link to the next page, by a client-side
 * navigation. Every API answer's Server-Timing header (total, DB time, query count) is collected per route.
 *
 * Not a gate: runs only with PERF_RUN=1, against servers that are already up (frontend/playwright.perf.config.ts;
 * no webServer). Writes $E2E_DIR/perf/<PERF_LABEL>.json and .md and prints the summary. Method:
 *   docs/phases/PERFORMANCE_AUDIT.md "Measurement script".
 *   PERF_RUN=1 PERF_LABEL=after PERF_WEB=http://127.0.0.1:3031 E2E_DIR=... \
 *     npx playwright test -c playwright.perf.config.ts e2e/perf-waterfall.spec.ts
 */
test.skip(!process.env.PERF_RUN, "PERF_RUN=1 runs the waterfall measurement");

type ProfileKey = "laptop" | "phone";
type Mode = "cold" | "warm" | "client";

interface Req {
  url: string;
  method: string;
  /** ms after the navigation started */
  start: number;
  end: number;
  status: number;
  type: string;
  bytes: number;
  serverTiming: string | null;
}

interface ShellEvent { t: number; state: string }

interface Load {
  page: string;
  profile: ProfileKey;
  mode: Mode;
  url: string;
  /** ms until the first content (main text without skeletons), -1 when it never came */
  firstContent: number;
  /** ms until the network went idle (all requests of the load done) */
  settled: number;
  /** The frames seen, in order (`student-skeleton`, `student`, `header-skeleton`, `header`, `neutral`, `none`). */
  shells: ShellEvent[];
  /** A student frame followed by a header frame or the reverse. */
  swap: boolean;
  requests: Req[];
  api: Req[];
  /** Longest chain of API requests that start after another one ended. */
  apiDepth: number;
  jsBytes: number;
}

const PROFILES: Record<ProfileKey, { viewport: { width: number; height: number }; mobile: boolean; cpu: number; net: null | { latency: number; kbps: number } }> = {
  laptop: { viewport: { width: 1440, height: 900 }, mobile: false, cpu: 1, net: null },
  phone: { viewport: { width: 390, height: 844 }, mobile: true, cpu: 4, net: { latency: 400, kbps: 400 } },
};

const LABEL = process.env.PERF_LABEL || "run";
const RUNS = Number(process.env.PERF_RUNS || 1);
const ONLY = (process.env.PERF_PROFILES || "laptop,phone").split(",") as ProfileKey[];

/** Injected before any script: watches which frame is on screen and when the main content (not a skeleton) arrived. */
function observer() {
  const w = window as unknown as { __shell: ShellEvent[]; __content: number };
  w.__shell = [];
  w.__content = -1;
  let last = "";
  const check = () => {
    const student = !!document.querySelector("aside.fixed.inset-y-0.left-0");
    const studentSkeleton = !student && !!document.querySelector('div[aria-hidden="true"].fixed.inset-y-0.left-0');
    const headerSkeleton = !!document.querySelector('[data-testid="areas-loading"]');
    // PERFORMANCE_AUDIT S1: the neutral loading frame (`LmsShell`), under which a cold page renders hidden
    const neutral = !!document.querySelector('[data-testid="shell-neutral"]');
    // the app header (teacher/admin frame); the student frame's phone header carries `lg:hidden`; S1: a page's own
    // <header> rendered hidden (display: none) under the neutral frame is not a frame
    const header = !headerSkeleton && !student
      && [...document.querySelectorAll("header")].some((h) => !h.className.includes("lg:hidden") && !h.closest("aside") && h.getClientRects().length > 0);
    const state = student ? "student" : studentSkeleton ? "student-skeleton" : header ? "header" : headerSkeleton ? "header-skeleton" : neutral ? "neutral" : "none";
    if (state !== last) {
      last = state;
      w.__shell.push({ t: Math.round(performance.now()), state });
    }
    if (w.__content < 0) {
      const main = document.querySelector("main") || document.querySelector("form") || document.body;
      const busy = main.querySelector(".animate-pulse, [role=\"status\"][aria-live]");
      const text = (main.textContent || "").replace(/\s+/g, " ").trim();
      if (!busy && text.length > 40) w.__content = Math.round(performance.now());
    }
  };
  let scheduled = false;
  new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; check(); });
  }).observe(document, { childList: true, subtree: true, characterData: true, attributes: true }); // the init script runs before <html> exists
  document.addEventListener("DOMContentLoaded", check);
}

async function newContext(browser: Browser, profile: ProfileKey, user: SeedUser | null): Promise<{ ctx: BrowserContext; page: Page }> {
  const p = PROFILES[profile];
  const ctx = await browser.newContext({
    viewport: p.viewport, isMobile: p.mobile, hasTouch: p.mobile, deviceScaleFactor: p.mobile ? 3 : 1,
    locale: "ru-RU", timezoneId: "UTC",
  });
  const page = await ctx.newPage();
  if (user) await signIn(page, user);
  await page.addInitScript(observer);
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  if (p.net) {
    const bps = (p.net.kbps * 1000) / 8;
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: p.net.latency, downloadThroughput: bps, uploadThroughput: bps });
  }
  if (p.cpu > 1) await cdp.send("Emulation.setCPUThrottlingRate", { rate: p.cpu });
  return { ctx, page };
}

function track(page: Page): { requests: Req[]; reset: () => void; idle: () => Promise<void> } {
  const requests: Req[] = [];
  let origin = Date.now();
  const open = new Map<string, Req>();
  page.on("request", (r) => {
    const req: Req = { url: r.url(), method: r.method(), start: Date.now() - origin, end: -1, status: 0, type: r.resourceType(), bytes: 0, serverTiming: null };
    open.set(r.url() + "#" + req.start, req);
    requests.push(req);
    (r as unknown as { __req: Req }).__req = req;
  });
  const done = async (r: import("@playwright/test").Request, failed: boolean) => {
    const req = (r as unknown as { __req?: Req }).__req;
    if (!req) return;
    req.end = Date.now() - origin;
    if (!failed) {
      const res = await r.response().catch(() => null);
      if (res) {
        req.status = res.status();
        req.serverTiming = res.headers()["server-timing"] ?? null;
        const len = res.headers()["content-length"];
        if (len) req.bytes = Number(len);
        else if (/\.js(\?|$)/.test(req.url)) req.bytes = (await res.body().catch(() => Buffer.alloc(0))).length;
      }
    }
  };
  page.on("requestfinished", (r) => { void done(r, false); });
  page.on("requestfailed", (r) => { void done(r, true); });
  return {
    requests,
    reset: () => { requests.length = 0; origin = Date.now(); },
    idle: async () => {
      // the pages keep polling nothing, so "no request for 1.5 s" means the load is complete
      const deadline = Date.now() + 90_000;
      for (;;) {
        const pending = requests.some((r) => r.end < 0);
        const lastEnd = Math.max(0, ...requests.map((r) => r.end));
        if (!pending && Date.now() - origin - lastEnd > 1500) return;
        if (Date.now() > deadline) return;
        await page.waitForTimeout(100);
      }
    },
  };
}

function apiDepth(api: Req[]): number {
  const sorted = [...api].sort((a, b) => a.start - b.start);
  const depth: number[] = [];
  sorted.forEach((r, i) => {
    let d = 1;
    for (let j = 0; j < i; j++) if (sorted[j].end >= 0 && sorted[j].end <= r.start) d = Math.max(d, depth[j] + 1);
    depth.push(d);
  });
  return Math.max(0, ...depth);
}

async function collect(page: Page, tracker: ReturnType<typeof track>, meta: { page: string; profile: ProfileKey; mode: Mode; url: string }): Promise<Load> {
  await tracker.idle();
  await page.waitForTimeout(300);
  const { shells, content } = await page.evaluate(() => {
    const w = window as unknown as { __shell: ShellEvent[]; __content: number; __t0?: number };
    const t0 = w.__t0 ?? 0; // a client navigation counts from its click
    return {
      shells: (w.__shell ?? []).map((s) => ({ ...s, t: s.t - t0 })),
      content: w.__content >= 0 ? w.__content - t0 : -1,
    };
  });
  const requests = tracker.requests.map((r) => ({ ...r }));
  const api = requests.filter((r) => r.url.includes("/api/v1/"));
  const seen = shells.map((s) => s.state);
  const studentAt = seen.findIndex((s) => s.startsWith("student"));
  const headerAt = seen.findIndex((s) => s.startsWith("header"));
  const swap = studentAt >= 0 && headerAt >= 0;
  return {
    ...meta, firstContent: content, settled: Math.max(0, ...requests.map((r) => r.end)), shells, swap, requests, api,
    apiDepth: apiDepth(api), jsBytes: requests.filter((r) => r.type === "script").reduce((a, r) => a + r.bytes, 0),
  };
}

interface PageSpec { key: string; url: string; user: SeedUser | null; next?: string }

function pagesOf(): PageSpec[] {
  // PERF_PUBLIC_ONLY=1: the public pages of any origin (production too), no seed and no sign-in
  if (process.env.PERF_PUBLIC_ONLY) {
    return [
      { key: "landing", url: "/ru", user: null },
      { key: "login", url: "/ru/login", user: null },
    ];
  }
  const s = seed();
  const student = s.students["flow-ru"];
  const sc = s.course_id;
  const teacher = s.course_nav.teacher;
  const tc = s.course_nav.course_id;
  return [
    { key: "login", url: "/ru/login", user: null },
    { key: "student-home", url: "/ru/courses", user: student, next: `/ru/courses/${sc}/tests` },
    { key: "student-tests", url: `/ru/courses/${sc}/tests`, user: student, next: `/ru/courses/${sc}/progress` },
    { key: "student-analytics", url: `/ru/courses/${sc}/progress`, user: student, next: "/ru/courses" },
    { key: "teacher-courses", url: "/ru/courses", user: teacher, next: `/ru/courses/${tc}` },
    { key: "teacher-course", url: `/ru/courses/${tc}`, user: teacher, next: `/ru/courses/${tc}/people` },
    { key: "admin-overview", url: "/ru/admin", user: s.admin, next: "/ru/admin/users" },
  ];
}

const routeOf = (url: string) => new URL(url).pathname.replace(/^\/api\/v1/, "")
  .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g, "{id}");

function parseTiming(h: string | null): { total: number; db: number; n: number } | null {
  if (!h) return null;
  const m = /total;dur=([\d.]+), db;dur=([\d.]+);desc="n=(\d+)"/.exec(h);
  return m ? { total: Number(m[1]), db: Number(m[2]), n: Number(m[3]) } : null;
}

const med = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0; };

function summary(loads: Load[]): string {
  const lines: string[] = [];
  lines.push(`### ${LABEL}: page loads (ms; first content = main text without skeletons; depth = sequential API rounds)`);
  lines.push("");
  lines.push("| page | profile | mode | requests | API | API depth | first content | settled | JS kB | frames seen | swap |");
  lines.push("|---|---|---|---|---|---|---|---|---|---|---|");
  for (const l of loads) {
    lines.push(`| ${l.page} | ${l.profile} | ${l.mode} | ${l.requests.length} | ${l.api.length} | ${l.apiDepth} | ${l.firstContent} | ${l.settled} | ${Math.round(l.jsBytes / 1024)} | ${l.shells.map((s) => s.state).join(" → ") || "-"} | ${l.swap ? "YES" : "no"} |`);
  }
  lines.push("");
  lines.push(`### ${LABEL}: API requests per load (laptop, cold), in start order`);
  lines.push("");
  for (const l of loads.filter((x) => x.profile === "laptop" && x.mode === "cold")) {
    lines.push(`**${l.page}**`);
    lines.push("");
    lines.push("| start | end | method | route | status | server total | db | queries |");
    lines.push("|---|---|---|---|---|---|---|---|");
    for (const r of [...l.api].sort((a, b) => a.start - b.start)) {
      const t = parseTiming(r.serverTiming);
      lines.push(`| ${r.start} | ${r.end} | ${r.method} | ${routeOf(r.url)}${new URL(r.url).search ? " ?" : ""} | ${r.status} | ${t ? t.total : "-"} | ${t ? t.db : "-"} | ${t ? t.n : "-"} |`);
    }
    lines.push("");
  }
  const byRoute = new Map<string, { total: number[]; db: number[]; n: number[] }>();
  for (const l of loads) for (const r of l.api) {
    const t = parseTiming(r.serverTiming);
    if (!t) continue;
    const key = `${r.method} ${routeOf(r.url)}`;
    const e = byRoute.get(key) ?? { total: [], db: [], n: [] };
    e.total.push(t.total); e.db.push(t.db); e.n.push(t.n);
    byRoute.set(key, e);
  }
  lines.push(`### ${LABEL}: backend Server-Timing per route (median over every load)`);
  lines.push("");
  lines.push("| route | calls | total ms | db ms | queries |");
  lines.push("|---|---|---|---|---|");
  for (const [k, e] of [...byRoute.entries()].sort((a, b) => med(b[1].total) - med(a[1].total))) {
    lines.push(`| ${k} | ${e.total.length} | ${med(e.total)} | ${med(e.db)} | ${med(e.n)} |`);
  }
  return lines.join("\n");
}

test("waterfall, first content and shell swaps of the main pages", async ({ browser }) => {
  test.setTimeout(3_000_000);
  const loads: Load[] = [];
  for (const profile of ONLY) {
    for (const spec of pagesOf()) {
      for (let run = 0; run < RUNS; run++) {
        const { ctx, page } = await newContext(browser, profile, spec.user);
        const tracker = track(page);
        try {
          await page.goto(spec.url, { waitUntil: "commit", timeout: 120_000 });
          loads.push(await collect(page, tracker, { page: spec.key, profile, mode: "cold", url: spec.url }));
          if (spec.next) {
            const link = page.locator(`a[href="${spec.next}"]`).first();
            if (await link.count()) {
              tracker.reset();
              await page.evaluate(() => {
                const w = window as unknown as { __shell: ShellEvent[]; __content: number; __t0: number };
                w.__shell = []; w.__content = -1; w.__t0 = performance.now();
              });
              // a programmatic click: the link may sit in a sidebar hidden at phone width; the router still handles it
              await link.evaluate((el) => (el as HTMLAnchorElement).click()).catch(() => null);
              loads.push(await collect(page, tracker, { page: spec.key, profile, mode: "client", url: spec.next }));
            }
          }
          tracker.reset();
          await page.goto(spec.url, { waitUntil: "commit", timeout: 120_000 });
          loads.push(await collect(page, tracker, { page: spec.key, profile, mode: "warm", url: spec.url }));
        } finally {
          await ctx.close();
        }
      }
    }
  }
  const dir = path.join(E2E_DIR, "perf");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, `${LABEL}.json`), JSON.stringify(loads, null, 1));
  const md = summary(loads);
  fs.writeFileSync(path.join(dir, `${LABEL}.md`), md);
  console.log(`\n${md}\n`);
  expect(loads.length).toBeGreaterThan(0);
});
