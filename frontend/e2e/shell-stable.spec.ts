import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, signIn, type SeedUser } from "./helpers";

/**
 * PERFORMANCE_AUDIT §5.1 (S1): the frame is decided once. A MutationObserver installed before any script records every
 * frame on screen from the first byte (`neutral` loading frame, `student` sidebar shell, `header` app header, `none`);
 * for a teacher, a student and a platform admin, on a cold load (new context: no sessionStorage) and a warm one (same
 * context, cached /me/lms), at 1440 and 390 px, the sequence holds at most one of `student` / `header`: teachers and
 * admins never see the student sidebar, students never see the app header. Read-only: no data changes.
 */

type Frame = "neutral" | "student" | "header" | "none";

/** Injected before any script: the frames seen, in order. */
function frameObserver() {
  const w = window as unknown as { __frames: string[] };
  w.__frames = [];
  const check = () => {
    // the student shell's sidebar is in the DOM at every width (hidden below lg)
    const student = !!document.querySelector("aside.fixed.inset-y-0.left-0");
    const neutral = !student && !!document.querySelector('[data-testid="shell-neutral"]');
    // the app header; the student frame's phone top bar carries `lg:hidden`
    const header = !student && !neutral
      && [...document.querySelectorAll("header")].some((h) => !h.className.includes("lg:hidden") && !h.closest("aside") && h.getClientRects().length > 0);
    const state = student ? "student" : neutral ? "neutral" : header ? "header" : "none";
    if (w.__frames[w.__frames.length - 1] !== state) w.__frames.push(state);
  };
  // synchronous on every mutation (not per animation frame), so even a frame that lives one task is seen
  new MutationObserver(check).observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "data-testid"] });
  document.addEventListener("DOMContentLoaded", check);
}

const frames = (page: Page) => page.evaluate(() => (window as unknown as { __frames: Frame[] }).__frames ?? []);

const VIEWPORTS = [
  { name: "1440", viewport: { width: 1440, height: 900 } },
  { name: "390", viewport: { width: 390, height: 844 } },
] as const;

interface Case { who: string; user: () => SeedUser; urls: () => string[]; frame: "student" | "header" }

const CASES: Case[] = [
  {
    who: "teacher", frame: "header", user: () => seed().course_nav.teacher,
    urls: () => ["/ru/courses", `/ru/courses/${seed().course_nav.course_id}`],
  },
  {
    who: "student", frame: "student", user: () => seed().students["flow-ru"],
    urls: () => ["/ru/home", "/ru/courses", `/ru/courses/${seed().course_id}/tests`], // step 3a S3: the hub
  },
  { who: "admin", frame: "header", user: () => seed().admin, urls: () => ["/ru/admin", "/ru/courses"] },
];

async function load(page: Page, url: string, expected: Case["frame"]): Promise<Frame[]> {
  await page.goto(url);
  // the page's own content is on screen in the expected frame, and the network has settled
  await expect.poll(async () => (await frames(page)).at(-1), { message: `${url}: final frame`, timeout: 30_000 }).toBe(expected);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  return frames(page);
}

function assertStable(seen: Frame[], c: Case, label: string) {
  const other = c.frame === "student" ? "header" : "student";
  expect(seen, `${label}: frames ${seen.join(" → ")}`).toContain(c.frame);
  expect(seen, `${label}: frames ${seen.join(" → ")}`).not.toContain(other);
}

async function newPage(browser: Browser, viewport: { width: number; height: number }, user: SeedUser) {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC" });
  const page = await ctx.newPage();
  await signIn(page, user);
  await page.addInitScript(frameObserver);
  return { ctx, page };
}

test.describe("shell decided once", () => {
  for (const vp of VIEWPORTS) {
    for (const c of CASES) {
      test(`${c.who} at ${vp.name}: cold and warm loads never swap frames`, async ({ browser }) => {
        for (const url of c.urls()) {
          const { ctx, page } = await newPage(browser, vp.viewport, c.user());
          try {
            assertStable(await load(page, url, c.frame), c, `${url} cold`);
            // warm: the same tab again, /me/lms cached in sessionStorage
            assertStable(await load(page, url, c.frame), c, `${url} warm`);
          } finally {
            await ctx.close();
          }
        }
      });
    }
  }

  test("teacher: the course list is asked once; the warm frame comes from the cache", async ({ browser }) => {
    const c = CASES[0];
    const { ctx, page } = await newPage(browser, VIEWPORTS[0].viewport, c.user());
    try {
      const lists: string[] = [];
      page.on("request", (r) => { if (/\/api\/v1\/courses\?(.*&)?as=teaching(&|$)/.test(r.url())) lists.push(r.url()); });
      await load(page, "/ru/courses", "header"); // cold: the list must not remount when /me/lms arrives
      expect(lists).toHaveLength(1);
      const seen = await load(page, "/ru/courses", "header");
      // the server-rendered neutral frame may show before hydration; after it, the header comes at once and stays
      expect(seen.filter((f) => f !== "none" && f !== "neutral"), seen.join(" → ")).toEqual(["header"]);
      expect(seen.lastIndexOf("neutral") < seen.indexOf("header"), seen.join(" → ")).toBe(true);
    } finally {
      await ctx.close();
    }
  });
});
