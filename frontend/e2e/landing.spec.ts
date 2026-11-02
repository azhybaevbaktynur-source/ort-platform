import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { E2E_DIR, seed, settle, signIn, tr } from "./helpers";

/**
 * The public landing page and its short pages, logged out unless a test says otherwise.
 * LANDING_SCREENS=1 also writes full-page shots of the ru landing page to $E2E_DIR/landing-look/ for a look by eye.
 */

const L = "ru" as const;
const t = (key: string) => tr(L, key);
const PAGES = ["", "/for-teachers", "/about", "/help", "/contacts"];
const WIDTHS = [375, 1440, 1920];
const header = (page: Page) => page.locator("header");
const footer = (page: Page) => page.locator("footer");
const roleLink = (page: Page, key: string) => page.getByRole("main").getByRole("link", { name: t(`landing.hero.roles.${key}`), exact: true });

async function noHorizontalScroll(page: Page, label: string) {
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(scroll, `${label}: horizontal scroll`).toBeLessThanOrEqual(client);
}

test.describe("landing page", () => {
  test("the header has the only login link and one register link", async ({ page }) => {
    for (const p of PAGES) {
      await page.goto(`/${L}${p}`);
      await expect(header(page).getByRole("link", { name: t("common.login"), exact: true })).toHaveCount(1);
      await expect(header(page).getByRole("link", { name: t("common.register"), exact: true })).toHaveCount(1);
      await expect(header(page).getByRole("link", { name: t("common.login"), exact: true })).toHaveAttribute("href", `/${L}/login`);
      await expect(header(page).getByRole("link", { name: t("common.register"), exact: true })).toHaveAttribute("href", `/${L}/register`);
      // no second login anywhere on the page
      await expect(page.locator(`a[href="/${L}/login"]`)).toHaveCount(1);
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    }
    await page.goto(`/${L}`);
    await expect(page.locator(`header a[href="/${L}/register"]`)).toHaveCount(1);
  });

  test("the hero's role entries go to the right places", async ({ page }) => {
    await page.goto(`/${L}`);
    await expect(roleLink(page, "student")).toHaveAttribute("href", `/${L}/register`);
    await expect(roleLink(page, "teacher")).toHaveAttribute("href", `/${L}/for-teachers`);
    await expect(page.getByRole("main").getByRole("link", { name: /родител|parent/i })).toHaveCount(0);
    await roleLink(page, "teacher").click();
    await expect(page).toHaveURL(new RegExp(`/${L}/for-teachers$`));
    await expect(page.getByRole("heading", { level: 1, name: t("landing.forTeachers.title") })).toBeVisible();
    await expect(page.getByRole("main").getByRole("link", { name: t("landing.forTeachers.apply"), exact: true })).toHaveAttribute("href", `/${L}/for-teachers/apply`);
    await expect(page.getByRole("main").getByRole("link", { name: t("landing.forTeachers.haveAccount") })).toHaveAttribute("href", `/${L}/login?redirect=${encodeURIComponent(`/${L}/for-teachers/apply`)}`);
    await page.goto(`/${L}`);
    await roleLink(page, "student").click();
    await expect(page).toHaveURL(new RegExp(`/${L}/register$`));
  });

  test("the role sections' buttons and the final block", async ({ page }) => {
    await page.goto(`/${L}`);
    const main = page.getByRole("main");
    await expect(main.getByRole("link", { name: t("landing.students.button") })).toHaveAttribute("href", `/${L}/register`);
    await expect(main.getByRole("link", { name: t("landing.teachers.button") })).toHaveAttribute("href", `/${L}/for-teachers`);
    await expect(main.getByRole("link", { name: t("landing.final.button") })).toHaveAttribute("href", `/${L}/register`);
  });

  test("every footer link resolves to 200", async ({ page, baseURL }) => {
    await page.goto(`/${L}`);
    const hrefs = await footer(page).getByRole("link").evaluateAll((els) => els.map((e) => e.getAttribute("href")!));
    expect(hrefs.sort()).toEqual([`/${L}/about`, `/${L}/contacts`, `/${L}/for-teachers`, `/${L}/help`, `/${L}/policies/privacy`].sort());
    for (const href of hrefs) {
      expect((await page.request.get(`${baseURL}${href}`)).status(), href).toBe(200);
    }
    await page.goto(`/${L}/policies/privacy`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.goto(`/${L}/contacts`);
    await expect(page.getByRole("main")).toContainText(t("landing.contacts.body"));
  });

  test("the language switchers keep the page", async ({ page }) => {
    await page.goto(`/${L}`);
    await header(page).getByRole("combobox", { name: t("common.language") }).selectOption("en");
    await expect(page).toHaveURL(/\/en$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(tr("en", "landing.hero.title"));
    await page.goto("/en/help");
    await footer(page).getByRole("button", { name: tr("en", "landing.footer.languages.ky") }).click();
    await expect(page).toHaveURL(/\/ky\/help$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(tr("ky", "landing.help.title"));
    await expect(footer(page).getByRole("button", { name: tr("ky", "landing.footer.languages.ky") })).toHaveAttribute("aria-pressed", "true");
    await header(page).getByRole("combobox", { name: tr("ky", "common.language") }).selectOption("ru");
    await expect(page).toHaveURL(/\/ru\/help$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(t("landing.help.title"));
  });

  test("no horizontal scroll at 375, 1440 and 1920 px, in all three languages", async ({ browser }) => {
    test.setTimeout(240_000);
    for (const lang of ["ru", "ky", "en"] as const) {
      // a fresh context per language: a saved language would win over the URL
      const ctx = await browser.newContext({ locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
      const page = await ctx.newPage();
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: width === 375 ? 812 : 900 });
        for (const p of PAGES) {
          await page.goto(`/${lang}${p}`);
          await settle(page);
          await noHorizontalScroll(page, `/${lang}${p} at ${width}`);
        }
      }
      await ctx.close();
    }
  });

  test("the role entries are above the fold on a phone, and the header fits", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`/${L}`);
    for (const key of ["student", "teacher"]) {
      const box = (await roleLink(page, key).boundingBox())!;
      expect(box.y + box.height, key).toBeLessThanOrEqual(812);
    }
    const links = header(page).getByRole("link");
    for (let i = 0; i < await links.count(); i++) {
      const box = (await links.nth(i).boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(375);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }
    // Mascot's <picture> is display: contents: unwrapped in a grid, its <source> takes a cell and squeezes the text
    const why = page.getByRole("region", { name: t("landing.why.title") }).locator("li p");
    await expect(why).toHaveCount(3);
    for (let i = 0; i < 3; i++) expect((await why.nth(i).boundingBox())!.width).toBeGreaterThan(200);
    const footerLinks = footer(page).getByRole("link");
    for (let i = 0; i < await footerLinks.count(); i++) {
      expect((await footerLinks.nth(i).boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  });

  test("the mascot is decorative; the screenshots have real alt text and exist in every language", async ({ page, baseURL }) => {
    for (const p of PAGES) {
      await page.goto(`/${L}${p}`);
      const alts = await page.locator('img[src*="/mascot/"]').evaluateAll((els) => els.map((e) => e.getAttribute("alt")));
      expect(alts.length, p).toBeGreaterThan(0);
      for (const alt of alts) expect(alt, p).toBe("");
    }
    await page.goto(`/${L}`);
    const shots = page.locator('img[src^="/landing/"]');
    await expect(shots).toHaveCount(3);
    for (let i = 0; i < 3; i++) {
      const img = shots.nth(i);
      expect((await img.getAttribute("alt"))!.length).toBeGreaterThan(10);
      expect(await img.getAttribute("loading")).toBe("lazy");
      await img.scrollIntoViewIfNeeded();
      await expect.poll(() => img.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBe(1200);
    }
    for (const name of ["student-dashboard", "exam-player", "teacher-course"]) {
      for (const lang of ["en", "ky", "ru"]) {
        expect((await page.request.get(`${baseURL}/landing/${name}-${lang}.webp`)).status(), `${name}-${lang}`).toBe(200);
      }
    }
  });

  test("signed in: my courses and the name in the header, one continue button in the hero", async ({ page }) => {
    const user = seed().students["flow-ru"];
    await signIn(page, user);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`/${L}`);
    await expect(header(page).getByRole("link", { name: t("landing.myCourses") })).toHaveAttribute("href", `/${L}/courses`);
    await expect(header(page)).toContainText(user.name);
    await expect(header(page).getByRole("link", { name: t("common.login"), exact: true })).toHaveCount(0);
    await expect(header(page).getByRole("link", { name: t("common.register"), exact: true })).toHaveCount(0);
    await expect(roleLink(page, "student")).toHaveCount(0);
    await expect(roleLink(page, "teacher")).toHaveCount(0);
    await expect(page.locator("section").first().getByRole("link", { name: t("landing.hero.continue") })).toHaveAttribute("href", `/${L}/courses`);
    await noHorizontalScroll(page, "signed in at 375");
    if (process.env.LANDING_SCREENS === "1") {
      await settle(page);
      await page.screenshot({ path: path.join(E2E_DIR, "landing-look", "signed-in-ru-375-fold.png"), animations: "disabled", caret: "hide" });
    }
  });

  test("look: full-page shots of the ru landing page", async ({ browser }) => {
    test.skip(process.env.LANDING_SCREENS !== "1", "set LANDING_SCREENS=1");
    for (const width of WIDTHS) {
      const ctx = await browser.newContext({ viewport: { width, height: width === 375 ? 812 : 900 }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
      const page = await ctx.newPage();
      await page.goto(`/${L}`);
      // scroll through once so the lazy images load
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      for (let y = 0; y < height; y += 500) {
        await page.evaluate((top) => window.scrollTo(0, top), y);
        await page.waitForTimeout(80);
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await settle(page);
      await page.screenshot({ path: path.join(E2E_DIR, "landing-look", `landing-ru-${width}.png`), fullPage: true, animations: "disabled", caret: "hide" });
      await page.screenshot({ path: path.join(E2E_DIR, "landing-look", `landing-ru-${width}-fold.png`), animations: "disabled", caret: "hide" });
      for (const p of PAGES.slice(1)) {
        await page.goto(`/${L}${p}`);
        await settle(page);
        await page.screenshot({ path: path.join(E2E_DIR, "landing-look", `${p.slice(1)}-ru-${width}.png`), fullPage: true, animations: "disabled", caret: "hide" });
      }
      await ctx.close();
    }
  });
});
