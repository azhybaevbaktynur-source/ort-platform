import { expect, test } from "@playwright/test";
import { seed, tr, watchCsp } from "./helpers";

/**
 * PERFORMANCE_AUDIT P3 (§10.2 item 3): the sign-in starts the shell's bootstrap before the route change to the first
 * page, so that page finds it running or answered. A password student in no course (`seed.login_student`) signs in on
 * /ru/login: `/me/bootstrap?include=home` starts before the address becomes /ru/home (step 3a S3: the hub), is asked once (the home and
 * the shell share it), and the home asks none of its own reads (`/me/home`). The time from the click to the home's first
 * content is written to the test's annotations and stdout ("submit-to-content"); `P3_API_DELAY_MS` delays every API
 * request for that measurement.
 */

const L = "ru" as const;
const t = (key: string) => tr(L, key);

test("P3: the sign-in starts the bootstrap before the route change, and it is asked once", async ({ page }) => {
  const user = seed().login_student;
  const api = `${seed().api}/api/v1/`;
  watchCsp(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  // when the address first becomes the home (a client navigation: the page's clock and resource entries stay)
  await page.addInitScript(() => {
    const w = window as Window & { __homeAt?: number };
    for (const k of ["pushState", "replaceState"] as const) {
      const orig = history[k];
      history[k] = function (this: History, ...args: Parameters<History["pushState"]>) {
        const r = orig.apply(this, args);
        if (w.__homeAt === undefined && /^\/ru\/home\/?$/.test(location.pathname)) w.__homeAt = performance.now();
        return r;
      };
    }
  });
  // measurement only (off in the gate): P3_API_DELAY_MS=270 adds production's proxy round to every API request,
  // P3_WEB_DELAY_MS a CDN round to every route payload and script of the web app
  const slow = async (pattern: string | RegExp, ms: number) => {
    if (ms > 0) await page.route(pattern, async (route) => { await new Promise((r) => setTimeout(r, ms)); await route.continue(); });
  };
  await slow(`${api}**`, Number(process.env.P3_API_DELAY_MS || 0));
  await slow(/\/_next\/static\/chunks\/|[?&]_rsc=/, Number(process.env.P3_WEB_DELAY_MS || 0));
  const seen: string[] = [];
  page.on("request", (r) => {
    if (r.url().startsWith(api) && r.method() !== "OPTIONS") seen.push(r.url().slice(api.length - 1));
  });

  await page.goto(`/${L}/login`);
  await page.locator('input[type="email"]').fill(user.email);
  await page.locator('input[type="password"]').fill(user.password);
  await page.evaluate(() => {
    document.addEventListener("submit", () => { (window as Window & { __submitAt?: number }).__submitAt = performance.now(); }, true);
  });
  await page.getByRole("button", { name: t("auth.signInButton") }).click();
  // first content: the hub's empty state painted (a student in no course), read every frame (the page's own clock)
  const shown = await page.waitForFunction((title) => (document.body?.innerText.includes(title) ? performance.now() : 0),
    t("home.hub.emptyTitle"), { polling: "raf", timeout: 30_000 });
  await expect(page).toHaveURL(new RegExp(`/${L}/home$`));
  await expect(page.getByText(t("home.hub.emptyTitle"))).toBeVisible();
  const submitAt = await page.evaluate(() => (window as Window & { __submitAt?: number }).__submitAt ?? 0);
  const ms = Math.round((await shown.jsonValue()) - submitAt);
  test.info().annotations.push({ type: "submit-to-content", description: `${ms} ms` });
  console.log(`submit-to-content ${ms} ms`);
  await page.waitForLoadState("networkidle");

  const timing = await page.evaluate(() => ({
    homeAt: (window as Window & { __homeAt?: number }).__homeAt ?? null,
    boots: performance.getEntriesByType("resource").filter((e) => e.name.includes("/me/bootstrap")).map((e) => e.startTime),
  }));
  expect(timing.homeAt, "the home was reached by a client navigation").not.toBeNull();
  expect(timing.boots.length, "one bootstrap in this page's resource entries").toBe(1);
  expect(timing.boots[0], "the bootstrap started before the address became the home").toBeLessThan(timing.homeAt!);

  const boots = seen.filter((p) => p.startsWith("/me/bootstrap"));
  expect(boots, "one bootstrap, with the home's reads").toEqual([expect.stringContaining("include=home")]);
  expect(seen.filter((p) => /^\/me\/home(\?|$)/.test(p)), "the home asked nothing of its own").toEqual([]);
});
