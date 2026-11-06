import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { sectionCounts, seed, settle, signIn, tr, type SeedUser } from "./helpers";
import { OrtExam } from "./ort-exam";

/**
 * S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md): the platform admin creates a batch of codes (F6b: tab
 * «Ваучеры»), shows one and marks it sold; a student of a platform ORT course sees the paid test locked in the library,
 * opens the Pro page (`/unlock` redirects there), redeems the code under «Есть подарочный код?» and takes the paid test
 * in the ORT player (unchanged; OrtExam asserts it). The admin then sees the pass on the user page.
 * F6b Pro (docs/phases/SUBSCRIPTION_DESIGN.md 6-7): the Pro page without a season end and prices (no season plan, no
 * price line), the admin's settings (season end, a price) then show both; "Выдать Pro" from the Pro tab -> the student's
 * pill and page say "Pro до …"; "Отменить Pro" -> Free again. Pro screens at 375 / 1440 (ru) go to $F6B_SHOTS.
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

const PRO_SHOTS = process.env.F6B_SHOTS || "/private/tmp/claude-501/f6b_shots";

/** F6b UX check: 375 and 1440 px (ru), no side scroll. */
async function proShots(page: Page, name: string) {
  fs.mkdirSync(PRO_SHOTS, { recursive: true });
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal scroll at ${width}px (${name})`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(PRO_SHOTS, `${name}-${width}-ru.png`), fullPage: true, animations: "disabled", caret: "hide" });
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
      await admin.goto(`/${L}/admin/access/vouchers`);
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

      // ---- the lock opens the Pro page; a wrong code is refused, the sold one opens everything
      await paidCard.getByRole("link", { name: t("examPrep.tests.unlock"), exact: true }).click();
      await student.waitForURL(new RegExp(`/${L}/pro$`));
      await expect(student.getByText(t("access.pro.status.free"), { exact: true })).toBeVisible();
      await expect(student.getByText(t("access.howToPay"))).toBeVisible();
      await shoot(student, "unlock-before");
      await student.getByText(t("access.pro.voucher.toggle")).click();
      const field = student.getByLabel(t("access.pro.voucher.label"));
      await field.fill("ZZZZ-ZZZZ-ZZZZ");
      await student.getByRole("button", { name: t("access.unlock.redeem") }).click();
      await expect(student.getByText(t("lms.errors.code_invalid"))).toBeVisible();
      await field.fill(code.toLowerCase().replace(/-/g, " "));
      await student.getByRole("button", { name: t("access.unlock.redeem") }).click();
      const before = (key: string) => t(key, { date: "@@" }).split("@@")[0];
      await expect(student.getByRole("status").filter({ hasText: before("access.pro.voucher.success") })).toBeVisible();
      await expect(student.getByRole("region", { name: t("access.pro.status.title") })).toContainText(before("access.pro.status.active"));
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

  test("Pro: offer without season or price, admin settings, grant -> Pro до, cancel -> Free", async ({ browser }) => {
    test.setTimeout(240_000);
    const s = seed();
    const acc = s.access!;
    const admin = await pageFor(browser, s.admin);
    const student = await pageFor(browser, acc.pro_student);
    const name = "Access Pro";
    const status = () => student.getByRole("region", { name: t("access.pro.status.title") });
    const plansCard = () => student.getByRole("region", { name: t("access.pro.plans.title") });
    const until = t("access.pill.until", { date: "@@" }).split("@@")[0];
    try {
      // ---- /unlock keeps old links working (and their query); nothing set: two month plans, no season, no price
      await student.goto(`/${L}/unlock?from=mail`);
      await student.waitForURL(new RegExp(`/${L}/pro\\?from=mail$`));
      await expect(student.getByRole("heading", { level: 1, name: t("access.pro.title") })).toBeVisible();
      await expect(status()).toContainText(t("access.pro.status.free"));
      await expect(plansCard().getByRole("radio")).toHaveCount(2);
      await expect(plansCard().getByText(t("access.plan.month_1"), { exact: true })).toBeVisible();
      await expect(plansCard().getByText(t("access.plan.month_3"), { exact: true })).toBeVisible();
      await expect(plansCard().getByText(t("access.plan.season"), { exact: true })).toHaveCount(0);
      await expect(plansCard()).not.toContainText(t("access.pro.plans.price", { price: "@@" }).replace("@@", "").trim());
      await expect(plansCard().getByText(t("access.pro.plans.priceOnRequest"), { exact: true })).toHaveCount(2);
      await expect(plansCard()).toContainText(t("access.pro.pay.chosenOnRequest", { plan: t("access.plan.month_1") }));
      await expect(plansCard()).toContainText(t("access.howToPay"));
      await proShots(student, "pro-free");
      await student.screenshot({ path: path.join(PRO_SHOTS, "fix-pro-unset-1440-ru.png"), fullPage: true, animations: "disabled", caret: "hide" });

      // ---- admin settings: a season end in 60 days and one price; only what changed is sent
      await admin.goto(`/${L}/admin/access/settings`);
      await expect(admin.getByRole("link", { name: t("access.admin.tabs.settings") })).toHaveAttribute("aria-current", "page");
      const seasonEnd = new Date(Date.now() + 60 * 86_400_000).toISOString().slice(0, 10);
      await admin.getByLabel(t("access.admin.settings.seasonEnd")).fill(seasonEnd);
      await admin.getByLabel(t("access.admin.settings.priceLabel", { plan: t("access.plan.month_1") }), { exact: false }).fill("990");
      await admin.getByRole("button", { name: t("access.admin.settings.save") }).click();
      await expect(admin.getByText(t("access.admin.settings.saved"))).toBeVisible();
      await proShots(admin, "admin-settings");

      // ---- the student now sees the season plan and the price; choosing a plan shows it in "how to pay"
      await student.goto(`/${L}/pro`);
      await expect(plansCard().getByRole("radio")).toHaveCount(3);
      await expect(plansCard().getByText(t("access.plan.season"), { exact: true })).toBeVisible();
      await expect(plansCard()).toContainText(t("access.pro.pay.chosenPrice", { plan: t("access.plan.month_1"), price: "990" }));
      await plansCard().getByText(t("access.plan.month_3"), { exact: true }).click();
      await expect(plansCard()).toContainText(t("access.pro.pay.chosenOnRequest", { plan: t("access.plan.month_3") }));

      // ---- admin: "Выдать Pro" with the person search, 1 month
      await admin.goto(`/${L}/admin/access`);
      await expect(admin.getByRole("link", { name: t("access.admin.tabs.pro") })).toHaveAttribute("aria-current", "page");
      await admin.getByRole("button", { name: t("access.admin.pro.grant") }).locator("visible=true").first().click();
      const grant = admin.getByRole("alertdialog");
      await grant.getByRole("combobox", { name: t("access.admin.pro.person") }).fill("e2e-access-pro");
      await grant.getByRole("option", { name: new RegExp(name) }).click();
      await expect(grant).toContainText(t("access.admin.pro.preview", { date: "@@" }).split("@@")[0]);
      await expect(grant).toContainText(t("access.admin.pro.grantBodyNew")); // no Pro yet: it starts now
      await admin.screenshot({ path: path.join(PRO_SHOTS, "fix-grant-dialog-1440-ru.png"), animations: "disabled", caret: "hide" });
      await grant.getByLabel(t("ui.reason.required")).fill("E2E: оплата наличными");
      await grant.getByRole("button", { name: t("access.admin.pro.grant") }).click();
      await expect(grant).toBeHidden();
      const row = admin.getByRole("row").filter({ hasText: name }).locator("visible=true")
        .or(admin.locator("li").filter({ hasText: name }).locator("visible=true"));
      await expect(row.first()).toContainText(t("access.plan.month_1"));
      await expect(row.first()).toContainText(t("access.source.admin"));
      await proShots(admin, "admin-pro");

      // ---- the student: the sidebar pill and the page say "Pro до …"
      await student.goto(`/${L}/courses/${acc.course_id}/tests`);
      await expect(student.getByRole("link", { name: new RegExp(`^${until}`) }).locator("visible=true").first()).toBeVisible();
      await student.goto(`/${L}/pro`);
      await expect(status()).toContainText(t("access.pro.status.active", { date: "@@" }).split("@@")[0]);
      await expect(status()).toContainText(t("access.pro.status.daysLeft", { count: 30 }));
      await proShots(student, "pro-active");

      // ---- admin: "Отменить Pro" on that row with a reason -> the person leaves the list (no open pass left)
      await row.first().getByRole("button", { name: new RegExp(`^${t("access.admin.pro.cancel")}`) }).click();
      const cancel = admin.getByRole("alertdialog");
      await cancel.getByRole("textbox").fill("E2E: возврат");
      await cancel.getByRole("button", { name: t("access.admin.pro.cancel") }).click();
      await expect(cancel).toBeHidden();
      await expect(admin.getByText(t("access.admin.pro.cancelled"))).toBeVisible();
      await expect(admin.getByRole("link", { name: t("access.admin.pro.openPerson", { name }) }))
        .toHaveAttribute("href", `/${L}/admin/users/${acc.pro_student.profile.id}`);
      await expect(admin.getByText(name, { exact: true }).locator("visible=true")).toHaveCount(0);

      await student.goto(`/${L}/pro`);
      await expect(status()).toContainText(t("access.pro.status.free"));
    } finally {
      // the settings are platform-wide: leave them empty for the other specs
      try {
        await admin.goto(`/${L}/admin/access/settings`);
        const clear = admin.getByRole("button", { name: t("access.admin.settings.seasonClear") });
        if (await clear.isVisible()) await clear.click();
        await admin.getByLabel(t("access.admin.settings.priceLabel", { plan: t("access.plan.month_1") }), { exact: false }).fill("");
        await admin.getByRole("button", { name: t("access.admin.settings.save") }).click();
        await settle(admin);
      } catch { /* the test already failed */ }
      await admin.context().close();
      await student.context().close();
    }
  });
});
