import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { sectionCounts, seed, settle, signIn, tr, type SeedUser } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md): the platform admin creates a batch of codes, shows one and
 * marks it sold; a student of a platform ORT course sees the paid test locked in the library, opens the unlock page,
 * redeems the code and takes the paid test in the ORT player (unchanged; OrtExam asserts it). The admin then sees the
 * pass on the user page.
 *
 * Data: `seed.access` (a private platform ORT course with a free and a paid exam, a student without a pass).
 * Screens at 375 / 1440 / 1920 (ru) go to $S3_SHOTS (default /tmp/s3_shots).
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.S3_SHOTS || "/tmp/s3_shots";
const WIDTHS = [375, 1440, 1920] as const;
const CODE = /[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}/;

async function shoot(page: Page, name: string) {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal scroll at ${width}px (${name})`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function pageFor(browser: Browser, user: SeedUser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

test.describe("free and paid exams (ru)", () => {
  test.describe.configure({ mode: "serial" });

  test("admin batch -> locked test -> unlock with a code -> paid ORT test -> pass on the user page", async ({ browser }) => {
    test.setTimeout(300_000);
    const s = seed();
    const acc = s.access!;
    const admin = await pageFor(browser, s.admin);
    const student = await pageFor(browser, acc.student);
    try {
      // ---- admin: a new batch of three 30-day codes
      await admin.goto(`/${L}/admin/access`);
      await expect(admin.getByRole("heading", { name: t("access.admin.title"), level: 1 })).toBeVisible();
      await admin.getByRole("button", { name: t("access.admin.batches.create") }).click();
      const dialog = admin.getByRole("dialog");
      await dialog.getByLabel(t("access.admin.batches.label")).fill("Ноябрь E2E, 30 дней");
      await dialog.getByLabel(t("access.admin.batches.count")).fill("3");
      await dialog.getByLabel(t("access.admin.batches.note"), { exact: false }).fill("500 сом");
      await dialog.getByRole("button", { name: t("access.admin.batches.submit") }).click();
      await expect(dialog).toBeHidden();
      const row = admin.getByRole("link", { name: "Ноябрь E2E, 30 дней" });
      await expect(row).toBeVisible();
      await expect(admin.getByText(t("access.admin.batches.counts", { unused: 3, given: 0, redeemed: 0 })).locator("visible=true").first()).toBeVisible();
      await shoot(admin, "admin-batches");

      // ---- the batch: show one code (audited), mark it sold
      await row.click();
      await admin.waitForURL(/\/admin\/access\/batches\/[0-9a-f-]{36}$/);
      await expect(admin.getByText(t("access.admin.codes.showHint"))).toBeVisible();
      await admin.getByRole("button", { name: new RegExp(`^${t("access.admin.codes.show")}`) }).first().click();
      const codeCell = admin.getByText(CODE).locator("visible=true").first();
      await expect(codeCell).toBeVisible();
      const code = (await codeCell.innerText()).match(CODE)![0];
      await admin.getByRole("button", { name: t("access.admin.codes.markGiven") }).first().click();
      const given = admin.getByRole("dialog");
      await given.getByLabel(t("access.admin.codes.givenNote"), { exact: false }).fill("Айбек, мама");
      await given.getByRole("button", { name: t("access.admin.codes.givenSave") }).click();
      await expect(given).toBeHidden();
      await expect(admin.getByText("Айбек, мама").locator("visible=true").first()).toBeVisible();
      await shoot(admin, "admin-codes");

      // ---- paid exams: the platform's tests with their switches
      await admin.goto(`/${L}/admin/access/exams`);
      await expect(admin.getByRole("switch", { name: t("access.admin.exams.paidToggle", { title: "ОРТ S3 платный" }) })).toBeChecked();
      await expect(admin.getByRole("switch", { name: t("access.admin.exams.paidToggle", { title: "ОРТ S3 бесплатный" }) })).not.toBeChecked();
      await shoot(admin, "admin-exams");

      // ---- student: the paid test is locked on the Тесты page (U4: the course page redirects there), the free one is not
      await student.goto(`/${L}/courses/${acc.course_id}`);
      await student.waitForURL(new RegExp(`/${L}/courses/${acc.course_id}/tests$`));
      const library = student.getByRole("region", { name: t("examPrep.library.title") });
      const paidCard = library.locator("li").filter({ has: student.getByRole("heading", { name: "ОРТ S3 платный", exact: true }) });
      const freeCard = library.locator("li").filter({ has: student.getByRole("heading", { name: "ОРТ S3 бесплатный", exact: true }) });
      await expect(paidCard).toContainText(t("access.paid"));
      // U9 (review 8): "Платный" and the gold pill are the lock signals; no "Нужен доступ", no "Не начат" chip
      await expect(paidCard.getByText(t("access.lockedLabel"))).toHaveCount(0);
      await expect(paidCard).not.toContainText(t("examPrep.library.status.not_started"));
      await expect(freeCard).not.toContainText(t("access.paid"));
      await expect(freeCard.getByRole("link", { name: t("examPrep.tests.start"), exact: true })).toBeVisible();
      await shoot(student, "library-locks");

      // ---- the lock opens the unlock page; a wrong code is refused, the sold one opens everything
      await paidCard.getByRole("link", { name: t("examPrep.tests.unlock"), exact: true }).click();
      await student.waitForURL(new RegExp(`/${L}/unlock$`));
      await expect(student.getByText(t("access.unlock.statusNone"))).toBeVisible();
      await expect(student.getByText(t("access.howToPay"))).toBeVisible();
      await shoot(student, "unlock-before");
      const field = student.getByLabel(t("access.unlock.codeLabel"));
      await field.fill("ZZZZ-ZZZZ-ZZZZ");
      await student.getByRole("button", { name: t("access.unlock.redeem") }).click();
      await expect(student.getByText(t("lms.errors.code_invalid"))).toBeVisible();
      await field.fill(code.toLowerCase().replace(/-/g, " "));
      await student.getByRole("button", { name: t("access.unlock.redeem") }).click();
      const before = (key: string) => t(key, { date: "@@" }).split("@@")[0];
      await expect(student.getByRole("status").filter({ hasText: before("access.unlock.success") })).toBeVisible();
      await expect(student.getByText(before("access.unlock.statusActive"), { exact: false }).first()).toBeVisible();
      await shoot(student, "unlock-after");

      // ---- the paid test opens in the lobby and runs in the ORT player
      await student.goto(`/${L}/courses/${acc.course_id}/tests`);
      await expect(paidCard).not.toContainText(t("access.paid"));
      await expect(paidCard.getByRole("link", { name: t("examPrep.tests.unlock") })).toHaveCount(0);
      await shoot(student, "library-unlocked");
      await paidCard.getByRole("link", { name: t("examPrep.tests.start"), exact: true }).click();
      await student.waitForURL(new RegExp(`/courses/${acc.course_id}/assessments/${acc.paid_exam.id}$`));
      const exam = new OrtExam(student, L);
      await exam.assertLobby();
      await exam.start();
      const counts = sectionCounts();
      expect(acc.counts).toEqual(counts);
      for (const pos of [1, 2, 3, 4]) await exam.skipSection(pos);
      await exam.openSubmit({ unanswered: counts[4], flagged: 0 });
      await exam.confirmSubmit();
      await exam.assertResult(0, counts.reduce((a, b) => a + b, 0));

      // ---- admin: the pass and the used code on the student's page
      await admin.goto(`/${L}/admin/users/${acc.student.profile.id}`);
      const section = admin.getByRole("heading", { name: t("access.admin.user.title") });
      await expect(section).toBeVisible();
      await expect(admin.getByText(t("access.admin.user.statusActive"), { exact: true }).locator("visible=true").first()).toBeVisible();
      await expect(admin.getByText(t("access.admin.user.source.code", { last4: code.slice(-4) }))).toBeVisible();
      await shoot(admin, "user-passes");
    } finally {
      await admin.context().close();
      await student.context().close();
    }
  });
});
