import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * S5 installable app (docs/ROADMAP_EXAM_PREP.md): manifest and icons, the service worker (production build only),
 * nothing from the API or any page in its caches, the offline page, the update toast (never on exam routes) and the
 * "Install the app" account menu entry (Chrome prompt, iOS sheet, hidden in the installed app).
 *
 * Screens (ru, 375 / 1440 / 1920) go to $S5_SHOTS (default /tmp/s5_shots).
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.S5_SHOTS || "/tmp/s5_shots";
const WIDTHS = [375, 1440, 1920] as const;
const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";
/** What the worker may keep: build files, icons, the manifest, mascot images and the three offline pages. */
const CACHEABLE = /^\/(?:_next\/static\/|icons\/|mascot\/|manifest\.webmanifest$|(?:ru|ky|en)\/offline$)/;

async function shoot(page: Page, name: string, widths: readonly number[] = WIDTHS, fullPage = false) {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page, false);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${width}-ru.png`), fullPage, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function newContext(browser: Browser, opts: Parameters<Browser["newContext"]>[0] = {}): Promise<BrowserContext> {
  return browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light", serviceWorkers: "allow", ...opts });
}

/** The page is controlled by the app's worker (registered after load, it claims the page on activation). */
async function waitForWorker(page: Page) {
  await page.waitForFunction(() => !!navigator.serviceWorker?.controller, undefined, { timeout: 30_000 });
}

async function cachedUrls(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const out: string[] = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      for (const req of await cache.keys()) out.push(req.url);
    }
    return out;
  });
}

const accountMenu = (page: Page, user: SeedUser) => page.getByRole("button", { name: t("shell.account.menu", { name: user.name }) });

test.describe("installable app (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("manifest and icons are valid and linked", async ({ browser }) => {
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    try {
      await page.goto(`/${L}`);
      const href = await page.locator('link[rel="manifest"]').getAttribute("href");
      expect(href).toBe("/manifest.webmanifest");
      const res = await page.request.get(href!);
      expect(res.ok()).toBe(true);
      expect(res.headers()["content-type"]).toContain("manifest+json");
      const m = await res.json();
      expect(m.name).toBe(tr("ru", "common.appName"));
      expect(m.short_name).toBeTruthy();
      expect(m.start_url).toBe("/ru/");
      expect(m.display).toBe("standalone");
      expect(m.theme_color).toMatch(/^#[0-9a-f]{6}$/);
      expect(m.background_color).toMatch(/^#[0-9a-f]{6}$/);
      const sizes = m.icons.map((i: { sizes: string; purpose: string }) => `${i.sizes}:${i.purpose}`);
      expect(sizes).toEqual(expect.arrayContaining(["192x192:any", "512x512:any", "512x512:maskable"]));
      for (const icon of m.icons as { src: string; sizes: string }[]) {
        const r = await page.request.get(icon.src);
        expect(r.ok(), icon.src).toBe(true);
        expect(r.headers()["content-type"]).toBe("image/png");
        const png = await r.body();
        const [w, h] = [png.readUInt32BE(16), png.readUInt32BE(20)];
        expect(`${w}x${h}`).toBe(icon.sizes);
      }
      const apple = await page.locator('link[rel="apple-touch-icon"]').getAttribute("href");
      expect((await page.request.get(apple!)).ok()).toBe(true);
      await expect(page.locator('meta[name="apple-mobile-web-app-title"]')).toHaveAttribute("content", tr("ru", "common.appName"));
      const csp = (await page.request.get(`/${L}`)).headers()["content-security-policy"];
      expect(csp).toContain("worker-src 'self'");
      expect(csp).toContain("manifest-src 'self'");
    } finally {
      await ctx.close();
    }
  });

  test("the worker registers; API answers and pages are never cached; offline pages", async ({ browser }) => {
    const s = seed();
    const user = s.modules.ort_student;
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    const fromWorker: string[] = [];
    page.on("response", (r) => { if (r.url().startsWith(s.api) && r.fromServiceWorker()) fromWorker.push(r.url()); });
    try {
      await signIn(page, user);
      await page.goto(`/${L}/courses`);
      await waitForWorker(page);
      const script = await page.evaluate(async () => (await navigator.serviceWorker.ready).active?.scriptURL || "");
      expect(new URL(script).pathname).toBe("/service-worker.js");

      // signed-in pages with API traffic, twice (a second visit would hit any cache)
      for (let i = 0; i < 2; i++) {
        await page.goto(`/${L}/courses`);
        await expect(page.getByRole("link", { name: /ORT|ОРТ/ }).first()).toBeVisible();
        await page.goto(`/${L}/courses/${s.course_id}`);
        await settle(page);
      }
      expect(fromWorker, "API answers served by the worker").toEqual([]);
      const urls = await cachedUrls(page);
      expect(urls.length).toBeGreaterThan(5);
      const origin = new URL(page.url()).origin;
      for (const u of urls) {
        const url = new URL(u);
        expect(url.origin, u).toBe(origin);
        expect(url.pathname, u).toMatch(CACHEABLE);
        expect(u).not.toContain("/api/");
      }
      expect(urls.map((u) => new URL(u).pathname)).toEqual(expect.arrayContaining(["/ru/offline", "/ky/offline", "/en/offline"]));

      // offline: a page navigation shows the offline page of the URL's language; online again, "Try again" loads it
      await ctx.setOffline(true);
      await page.goto(`/${L}/courses/${s.course_id}`).catch(() => undefined);
      await expect(page.getByRole("heading", { name: t("pwa.offline.title") })).toBeVisible();
      expect(new URL(page.url()).pathname).toBe(`/${L}/courses/${s.course_id}`);
      await shoot(page, "offline", WIDTHS, true);
      await page.goto(`/ky/courses`).catch(() => undefined);
      await expect(page.getByRole("heading", { name: tr("ky", "pwa.offline.title") })).toBeVisible();
      await ctx.setOffline(false);
      await page.getByRole("button", { name: tr("ky", "pwa.offline.retry") }).click();
      await expect(page.getByRole("heading", { name: tr("ky", "pwa.offline.title") })).toHaveCount(0);
      expect(fromWorker).toEqual([]);
    } finally {
      await ctx.close();
    }
  });

  test("update toast: offered on ordinary pages, never on exam routes; only the tapping tab reloads", async ({ browser }) => {
    const s = seed();
    const user = s.modules.ort_student;
    const ctx = await newContext(browser);
    try {
      const home = await ctx.newPage();
      await signIn(home, user);
      await home.goto(`/${L}/courses`);
      await waitForWorker(home);
      const lobby = await ctx.newPage();
      await lobby.goto(`/${L}/courses/${s.course_id}/assessments/${s.exam.id}`);
      await waitForWorker(lobby);
      await lobby.evaluate(() => { (window as unknown as { __stay: number }).__stay = 1; });
      const player = await ctx.newPage();
      await player.goto(`/${L}/courses/${s.course_id}/attempts/00000000-0000-4000-8000-000000000000`);
      await waitForWorker(player);

      // a new worker version (another script URL stands in for a new deploy) installs and waits
      await home.evaluate(() => navigator.serviceWorker.register("/service-worker.js?next=1", { scope: "/", updateViaCache: "none" }));
      const toast = home.getByTestId("pwa-update");
      await expect(toast).toBeVisible({ timeout: 30_000 });
      await expect(toast).toContainText(t("pwa.update.message"));
      await shoot(home, "update-toast");

      // exam routes: the lobby and the player know about the waiting version and show nothing
      for (const p of [lobby, player]) {
        await p.waitForFunction(async () => !!(await navigator.serviceWorker.getRegistration())?.waiting);
        await p.waitForTimeout(1000);
        await expect(p.getByTestId("pwa-update")).toHaveCount(0);
      }

      // "Update": this tab reloads under the new worker; the exam tab is not reloaded
      await Promise.all([home.waitForEvent("load"), toast.getByRole("button", { name: t("pwa.update.action") }).click()]);
      await home.waitForFunction(() => navigator.serviceWorker.controller?.scriptURL.includes("next=1"));
      expect(await lobby.evaluate(() => (window as unknown as { __stay?: number }).__stay)).toBe(1);
      await expect(lobby.getByTestId("pwa-update")).toHaveCount(0);
    } finally {
      await ctx.close();
    }
  });

  test("Install the app: Chrome prompt from the account menu, dismissal remembered", async ({ browser }) => {
    const s = seed();
    const user = s.modules.ort_student;
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    try {
      await signIn(page, user);
      await page.goto(`/${L}/courses`);
      await expect(accountMenu(page, user)).toBeVisible();
      await accountMenu(page, user).click();
      await expect(page.getByRole("button", { name: t("pwa.install.menu") })).toHaveCount(0); // no prompt yet
      await accountMenu(page, user).click();

      // Chrome offers installation (the event the browser fires, with a stub prompt)
      await page.evaluate(() => {
        const e = new Event("beforeinstallprompt", { cancelable: true }) as Event & Record<string, unknown>;
        e.prompt = async () => { (window as unknown as { __prompted: number }).__prompted = 1; };
        e.userChoice = Promise.resolve({ outcome: "dismissed" });
        window.dispatchEvent(e);
      });
      await accountMenu(page, user).click();
      const entry = page.getByRole("button", { name: t("pwa.install.menu") });
      await expect(entry).toBeVisible();
      await shoot(page, "menu-install");
      await entry.click();
      await page.waitForFunction(() => (window as unknown as { __prompted?: number }).__prompted === 1);
      await page.waitForFunction(() => !!localStorage.getItem("pwa_install_dismissed_at"));

      // dismissed: not offered again, even when Chrome fires the event again
      await page.reload();
      await page.evaluate(() => {
        const e = new Event("beforeinstallprompt", { cancelable: true }) as Event & Record<string, unknown>;
        e.prompt = async () => undefined;
        e.userChoice = Promise.resolve({ outcome: "dismissed" });
        window.dispatchEvent(e);
      });
      await accountMenu(page, user).click();
      await expect(page.getByText(t("shell.account.signedInAs"))).toBeVisible();
      await expect(page.getByRole("button", { name: t("pwa.install.menu") })).toHaveCount(0);
    } finally {
      await ctx.close();
    }
  });

  test("Install the app on iPhone: the Share steps sheet; hidden in the installed app", async ({ browser }) => {
    const s = seed();
    const user = s.modules.ort_student;
    const ctx = await newContext(browser, { viewport: { width: 375, height: 812 }, userAgent: IPHONE_UA, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    try {
      await signIn(page, user);
      await page.goto(`/${L}/courses`);
      await accountMenu(page, user).click();
      await page.getByRole("button", { name: t("pwa.install.menu") }).click();
      const sheet = page.getByRole("dialog", { name: t("pwa.install.iosTitle") });
      await expect(sheet).toBeVisible();
      for (const k of ["iosStep1", "iosStep2", "iosStep3"]) await expect(sheet).toContainText(t(`pwa.install.${k}`));
      await settle(page, false);
      fs.mkdirSync(SHOTS, { recursive: true });
      await page.screenshot({ path: path.join(SHOTS, "ios-sheet-375-ru.png"), animations: "disabled", caret: "hide" });
      await sheet.getByRole("button", { name: t("pwa.install.iosDone") }).click();
      await expect(sheet).toHaveCount(0);
      await accountMenu(page, user).click();
      await expect(page.getByText(t("shell.account.signedInAs"))).toBeVisible();
      await expect(page.getByRole("button", { name: t("pwa.install.menu") })).toHaveCount(0); // dismissal remembered
    } finally {
      await ctx.close();
    }

    // opened from the home screen (navigator.standalone): never offered
    const app = await newContext(browser, { viewport: { width: 375, height: 812 }, userAgent: IPHONE_UA, isMobile: true, hasTouch: true });
    const p2 = await app.newPage();
    try {
      await p2.addInitScript(() => Object.defineProperty(navigator, "standalone", { get: () => true }));
      await signIn(p2, user);
      await p2.goto(`/${L}/courses`);
      await accountMenu(p2, user).click();
      await expect(p2.getByText(t("shell.account.signedInAs"))).toBeVisible();
      await expect(p2.getByRole("button", { name: t("pwa.install.menu") })).toHaveCount(0);
    } finally {
      await app.close();
    }
  });
});
