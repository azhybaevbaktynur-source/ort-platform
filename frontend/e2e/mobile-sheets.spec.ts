import fs from "node:fs";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * Owner feedback 2026-11-09, item 4 (docs/phases/OWNER_FEEDBACK_2026-11-09.md): on a phone the account sheet must show
 * everything and keep "Выйти" visible above the browser's bottom bar. Run by the projects `mobile-ios` (WebKit, iPhone)
 * and `mobile-android` (Chromium, Pixel 7) of playwright.config.ts. A short viewport (390x664) stands in for a page
 * whose bottom 80 px the browser bar covers: the sign-out button must lie inside it and be clickable.
 * ITEM4_SHOTS=<dir> also writes screenshots (375x667, 390x664, 412x915).
 */
const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SIZES = [{ width: 375, height: 667 }, { width: 390, height: 664 }, { width: 412, height: 915 }];
const SHORT = SIZES[1];

const accountName = (u: SeedUser): string => String(u.profile.displayName || u.name);

async function inView(page: Page, loc: Locator, what: string) {
  await expect(loc, what).toBeVisible();
  const box = await loc.boundingBox();
  expect(box, what).not.toBeNull();
  const vh = page.viewportSize()!.height;
  expect(box!.y, `${what} top`).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height, `${what} bottom ${box!.y + box!.height} within ${vh}`).toBeLessThanOrEqual(vh);
}

async function shot(page: Page, name: string) {
  const dir = process.env.ITEM4_SHOTS;
  if (!dir) return;
  fs.mkdirSync(dir, { recursive: true });
  const { width, height } = page.viewportSize()!;
  const proj = test.info().project.name.replace("mobile-", "");
  await page.screenshot({ path: path.join(dir, `${name}-${width}x${height}-${proj}-ru.png`), animations: "disabled", caret: "hide" });
}

test.describe("phone sheets keep sign out visible (ru)", () => {
  test.beforeEach(async ({}, info) => {
    test.skip(!info.project.name.startsWith("mobile-"), "phone projects only");
  });

  for (const size of SIZES) {
    test(`student: account sheet and More sheet at ${size.width}x${size.height}`, async ({ page }) => {
      const s = seed();
      const user = s.students["vis-desktop-ru"];
      await page.setViewportSize(size);
      await signIn(page, user);
      await page.goto(`/${L}/home`); // step 3a S3: the hub
      const tabBar = page.getByRole("navigation", { name: t("student.nav.tabBar") });
      await expect(tabBar).toBeVisible();
      await settle(page);
      await inView(page, tabBar, "tab bar");
      await shot(page, "student-home");

      // More (tab bar): the sheet scrolls, sign out is pinned
      await tabBar.getByRole("button", { name: t("student.nav.more") }).click();
      const more = page.getByRole("dialog", { name: t("student.nav.more") });
      await expect(more).toBeVisible();
      await inView(page, more.getByRole("button", { name: t("common.logout") }), "More: sign out");
      await shot(page, "student-more");
      await page.keyboard.press("Escape");
      await expect(more).toBeHidden();

      // account (top bar)
      await page.getByRole("button", { name: t("shell.account.menu", { name: accountName(user) }) }).click();
      const account = page.getByRole("dialog", { name: t("student.account.title") });
      await expect(account).toBeVisible();
      const logout = account.getByRole("button", { name: t("common.logout") });
      await inView(page, logout, "account: sign out");
      await inView(page, account, "account sheet");
      await shot(page, "student-account");
      await logout.click({ timeout: 5000 });
      await expect(account).toBeHidden();
    });
  }

  // step 3a S3: no exam sheet any more; the «Ещё» sheet carries the «Мои курсы» rows and «Войти по коду»
  test("student: the More sheet's course rows fit the short viewport", async ({ page }) => {
    const s = seed();
    const user = s.students["vis-desktop-ru"];
    await page.setViewportSize(SHORT);
    await signIn(page, user);
    await page.goto(`/${L}/home`);
    await settle(page);
    await page.getByRole("navigation", { name: t("student.nav.tabBar") }).getByRole("button", { name: t("student.nav.more") }).click();
    const dialog = page.getByRole("dialog", { name: t("student.nav.more") });
    await inView(page, dialog, "More sheet");
    await inView(page, dialog.locator(`a[href^="/${L}/courses/${s.course_id}"]`), "More: the course row");
    await expect(dialog.getByRole("link", { name: t("student.nav.joinByCode") })).toHaveAttribute("href", `/${L}/courses/join`);
    await shot(page, "student-more-rows");
  });

  for (const size of SIZES) {
    test(`teacher: account menu at ${size.width}x${size.height}`, async ({ page }) => {
      const user = seed().modules.teacher;
      await page.setViewportSize(size);
      await signIn(page, user);
      await page.goto(`/${L}/courses`);
      await settle(page);
      const btn = page.getByRole("button", { name: t("shell.account.menu", { name: accountName(user) }) });
      await expect(btn).toBeVisible();
      await btn.click();
      const logout = page.getByRole("button", { name: t("common.logout") });
      await inView(page, logout, "teacher: sign out");
      await shot(page, "teacher-account");
      await logout.click({ timeout: 5000 });
    });
  }
});
