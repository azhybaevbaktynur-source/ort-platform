import { expect, test } from "@playwright/test";
import { seed, signIn, tr, VIEWPORTS } from "./helpers";

/**
 * Fix round 2026-11-12 1c: a newly approved teacher lands on the Teaching view and sees "your application was approved"
 * once, without a link to the page it is on; "×" closes it for good (stored on the server), so neither a reload nor
 * another navigation (cached `me`) brings it back.
 */
const t = (key: string) => tr("ru", key);

test("the approved line has no link, closes, and stays closed", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.phone);
  const teacher = seed().teacher_notice;
  await signIn(page, teacher);
  await page.goto("/ru/courses");
  await expect(page).toHaveURL(/\/ru\/courses(\?view=teaching)?$/);

  const line = page.getByRole("status").filter({ hasText: t("home.teacherApplication.approved") });
  await expect(line).toHaveCount(1);
  await expect(line.getByRole("link")).toHaveCount(0);
  const close = line.getByRole("button", { name: t("home.teacherApplication.dismiss") });
  await expect(close).toBeVisible();

  const stored = page.waitForResponse((r) => r.url().endsWith("/me/teacher-application/dismiss") && r.status() === 204);
  await close.click();
  await expect(line).toHaveCount(0); // optimistic
  await stored;

  await page.reload();
  await expect(page.getByText(t("courses.list.emptyTeaching"))).toBeVisible();
  await expect(page.getByText(t("home.teacherApplication.approved"))).toHaveCount(0);

  await page.goto("/ru/grading-schemes");
  await page.goto("/ru/courses");
  await expect(page).toHaveURL(/\/ru\/courses(\?view=teaching)?$/);
  await expect(page.getByText(t("courses.list.emptyTeaching"))).toBeVisible();
  await expect(page.getByText(t("home.teacherApplication.approved"))).toHaveCount(0);
});
