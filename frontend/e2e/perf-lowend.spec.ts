import { expect, test, type Browser } from "@playwright/test";
import { seed, signIn, type SeedUser } from "./helpers";

/**
 * S5 performance check on a low-end Android profile (docs/ROADMAP_EXAM_PREP.md S5): 4x CPU slowdown and Lighthouse's
 * mobile network ("Slow 4G": 150 ms RTT, 1.6 Mbit/s down, 750 kbit/s up), a 375 px phone, a cold cache per page.
 * Prints LCP and TBT (long tasks' time over 50 ms from the first paint until 3 s after load) for the landing, the
 * student home, the exam-prep page and the exam lobby. Not a gate: runs only with PERF=1.
 *   PERF=1 E2E_WEB_DIR=... npx playwright test e2e/perf-lowend.spec.ts
 */
test.skip(!process.env.PERF, "PERF=1 runs the low-end performance check");

interface Metrics { lcp: number; fcp: number; tbt: number; load: number }

async function measure(browser: Browser, url: string, user?: SeedUser): Promise<Metrics> {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, locale: "ru-RU", timezoneId: "UTC" });
  const page = await ctx.newPage();
  try {
    if (user) await signIn(page, user);
    await page.addInitScript(() => {
      const w = window as unknown as { __perf: { lcp: number; long: { start: number; dur: number }[] } };
      w.__perf = { lcp: 0, long: [] };
      new PerformanceObserver((l) => { for (const e of l.getEntries()) w.__perf.lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver((l) => { for (const e of l.getEntries()) w.__perf.long.push({ start: e.startTime, dur: e.duration }); }).observe({ type: "longtask", buffered: true });
    });
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    await page.goto(url, { waitUntil: "load", timeout: 120_000 });
    await page.waitForTimeout(3000);
    return await page.evaluate(() => {
      const w = window as unknown as { __perf: { lcp: number; long: { start: number; dur: number }[] } };
      const fcp = performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? 0;
      const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
      const tbt = w.__perf.long.filter((t) => t.start + t.dur > fcp).reduce((a, t) => a + Math.max(0, t.dur - 50 - Math.max(0, fcp - t.start)), 0);
      return { lcp: Math.round(w.__perf.lcp), fcp: Math.round(fcp), tbt: Math.round(tbt), load: Math.round(nav.loadEventEnd) };
    });
  } finally {
    await ctx.close();
  }
}

test("low-end Android: LCP and TBT of the landing, home, exam-prep page and lobby", async ({ browser }) => {
  test.setTimeout(600_000);
  const s = seed();
  const user = s.modules.ort_student;
  const pages: [string, string, SeedUser | undefined][] = [
    ["landing", "/ru", undefined],
    ["student home", "/ru/courses", user],
    ["exam-prep page", `/ru/courses/${s.course_id}`, user],
    ["exam lobby", `/ru/courses/${s.course_id}/assessments/${s.exam.id}`, user],
  ];
  const rows: string[] = [];
  for (const [name, url, u] of pages) {
    const runs: Metrics[] = [];
    for (let i = 0; i < 3; i++) runs.push(await measure(browser, url, u));
    const med = (k: keyof Metrics) => runs.map((r) => r[k]).sort((a, b) => a - b)[1];
    rows.push(`${name.padEnd(16)} LCP ${String(med("lcp")).padStart(5)} ms  FCP ${String(med("fcp")).padStart(5)} ms  TBT ${String(med("tbt")).padStart(5)} ms  load ${String(med("load")).padStart(5)} ms`);
    expect(med("lcp")).toBeGreaterThan(0);
  }
  console.log(`\nlow-end Android (4x CPU, Slow 4G, cold cache, median of 3)\n${rows.join("\n")}`);
});
