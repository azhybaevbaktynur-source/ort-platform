import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * SUBSCRIPTION_DESIGN section 12 (P2b): Pro includes lesson courses. The platform admin adds a free module and a Pro
 * module to the seeded ORT course (a platform course). The student without a pass sees the Pro badge on the locked
 * module and the unlock bar ("Откройте уроки Pro") at the top of the syllabus and on a locked lesson; after the admin
 * grants Pro the bar and the badge are gone; the admin (staff) never sees the bar; /pro lists "курсы с уроками".
 * With P2B_SHOTS=<dir>: syllabus (bar), locked lesson, /pro at 375 / 1440 in ru.
 */
const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.P2B_SHOTS ? path.resolve(process.env.P2B_SHOTS) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const FREE_M = "Бесплатный модуль P2B";
const PRO_M = "Pro модуль P2B";
const PRO_L = "Урок Pro P2B";

async function shoot(page: Page, name: string) {
  if (!SHOTS) return;
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page, true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

test.describe("Pro includes lesson courses (ru)", () => {
  test("badge and unlock bar for a free student; none for Pro and staff; /pro lists courses", async ({ browser }) => {
    test.setTimeout(240_000);
    const s = seed();
    const cid = s.course_id;
    const base = `/${L}/courses/${cid}`;
    const admin = s.admin;
    const student: SeedUser = s.modules.ort_student;
    const created: string[] = [];
    let passId: string | null = null;
    const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const adminCtx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const bar = (p: Page) => p.getByRole("region", { name: t("access.courseBar.title") });
    try {
      const m1 = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: FREE_M }, published: true });
      created.push(m1.id);
      await api(admin, "POST", `/courses/${cid}/modules/${m1.id}/items`, {
        kind: "url", url: "https://example.org/p2b", title_override: { ru: "Бесплатный урок P2B" }, published: true });
      const m2 = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: PRO_M }, published: true, access_tier: "paid" });
      created.push(m2.id);
      const lesson = await api(admin, "POST", `/courses/${cid}/modules/${m2.id}/items`, {
        kind: "url", url: "https://example.org/p2b-pro", title_override: { ru: PRO_L }, published: true });

      // ---- free student: the Pro badge on the module, the bar on top of the syllabus and on the locked lesson
      const page = await ctx.newPage();
      await signIn(page, student);
      await page.goto(`${base}/modules`);
      await expect(bar(page)).toBeVisible();
      await expect(bar(page).getByRole("link", { name: t("access.courseBar.action") })).toHaveAttribute("href", `/${L}/pro`);
      await expect(page.locator(`section[id^="module-"]`).filter({ hasText: PRO_M }).getByText(t("modules.overview.pro"), { exact: true })).toBeVisible();
      await expect(page.locator(`section[id^="module-"]`).filter({ hasText: FREE_M }).getByText(t("modules.overview.pro"), { exact: true })).toHaveCount(0);
      await shoot(page, "syllabus-bar");
      await page.goto(`${base}/modules/${m2.id}/items/${lesson.id}`);
      await expect(page.getByText(t("modules.overview.proLockTitle"))).toBeVisible();
      await expect(bar(page)).toBeVisible();
      await shoot(page, "lesson-locked");

      // ---- /pro lists the lesson courses and the analytics in "Everything in Free"
      await page.goto(`/${L}/pro`);
      await expect(page.getByText(t("access.pro.compare.courses"))).toBeVisible();
      await expect(page.getByText(t("access.pro.compare.everythingFree"))).toBeVisible();
      await shoot(page, "pro-offer");

      // ---- staff: never the bar
      const ap = await adminCtx.newPage();
      await signIn(ap, admin);
      await ap.goto(`${base}/modules`);
      await expect(ap.getByRole("heading", { level: 1 }).first()).toBeVisible();
      await settle(ap, true);
      await expect(bar(ap)).toHaveCount(0);

      // ---- Pro student: neither badge nor bar
      const grant = await api(admin, "POST", `/platform/users/${student.profile.id}/access/grant`, { plan: "month_1", reason: "E2E P2B" });
      passId = grant.passes[0].id;
      await page.goto(`${base}/modules`);
      await expect(page.locator(`section[id^="module-"]`).filter({ hasText: PRO_M })).toBeVisible();
      await expect(bar(page)).toHaveCount(0);
      await expect(page.getByText(t("modules.overview.pro"), { exact: true })).toHaveCount(0);
    } finally {
      if (passId) await api(admin, "POST", `/platform/access/passes/${passId}/revoke`, { reason: "E2E P2B cleanup" }).catch(() => undefined);
      for (const id of created.reverse()) await api(admin, "DELETE", `/courses/${cid}/modules/${id}`).catch(() => undefined);
      await ctx.close();
      await adminCtx.close();
    }
  });
});
