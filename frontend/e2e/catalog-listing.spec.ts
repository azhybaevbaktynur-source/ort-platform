import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { api, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Step 3b S2 (CATALOG_AND_TEACHERS_DESIGN 2.3–2.6): the teacher's «Каталог платформы» block and Admin → Каталог.
 * An incomplete course says what is missing; the teacher requests, withdraws and requests again; the admin sees the
 * requests on the overview and in Admin → Каталог, approves one and declines the other with a note (the dialog asks
 * for it); the student finds the approved course in the catalog and never sees the note; the teacher sees the note on
 * the declined course, no button on the blocked one, and takes the listed one out of the catalog again.
 *
 * Data: `seed_backend.py` `seed_catalog_listing` (an independent teacher's four courses, one already blocked).
 * Screens for the UX check (ru; 375, 1440, 1920 px) go to `$CATALOG_SCREENS_DIR` only when it is set.
 */

const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const data = () => seed().catalog_listing;
const READY = "Геометрия для всех E2E";
const DECLINED = "Химия с нуля E2E";
const NOTE = "Добавьте хотя бы один тест и расскажите в описании, для какого класса курс";
const SCREENS = process.env.CATALOG_SCREENS_DIR ? path.resolve(process.env.CATALOG_SCREENS_DIR) : null;
const WIDE = { width: 1920, height: 1080 };

/** ru screens at 375 / 1440 / 1920 (full page; `viewport`: only the visible part, for dialogs). */
async function screens(page: Page, name: string, { viewport = false } = {}) {
  if (!SCREENS) return;
  fs.mkdirSync(SCREENS, { recursive: true });
  for (const [vp, size] of [["375", VIEWPORTS.phone], ["1440", VIEWPORTS.desktop], ["1920", WIDE]] as const) {
    await page.setViewportSize(size);
    await settle(page);
    await page.evaluate(() => document.querySelectorAll<HTMLElement>('div[aria-live="polite"].fixed').forEach((e) => { e.style.visibility = "hidden"; }));
    await page.screenshot({ path: path.join(SCREENS, `${name}-${vp}.png`), fullPage: !viewport, animations: "disabled", caret: "hide" });
    await page.evaluate(() => document.querySelectorAll<HTMLElement>('div[aria-live="polite"].fixed').forEach((e) => { e.style.visibility = ""; }));
  }
  await page.setViewportSize(VIEWPORTS.desktop);
}

async function as(browser: Browser, user: SeedUser): Promise<Page> {
  const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

async function openSettings(page: Page, courseId: string): Promise<Locator> {
  await page.goto(`/ru/courses/${courseId}/settings?section=enrollment`);
  const block = page.getByTestId("catalog-listing");
  await expect(block).toBeVisible();
  return block;
}

const button = (scope: Locator, key: string) => scope.getByRole("button", { name: t(key), exact: true });

test.describe.configure({ mode: "serial" });

test("an incomplete course: the block says what is missing and cannot be sent", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  const block = await openSettings(page, data().incomplete_id);
  await expect(block).toHaveAttribute("data-state", "off");
  await expect(block.getByRole("heading", { name: t("catalog.listing.title") })).toBeVisible();
  const missing = block.getByTestId("listing-missing");
  for (const k of ["link_access", "description", "cover_or_content"]) {
    await expect(missing.getByText(t(`catalog.listing.incomplete.${k}`))).toBeVisible();
  }
  await expect(missing.getByText(t("catalog.listing.incomplete.published"))).toHaveCount(0);
  await expect(button(block, "catalog.listing.request")).toBeDisabled();
  // the server says the same (422 listing_incomplete with the list)
  const r = await fetch(`${seed().api}/api/v1/courses/${data().incomplete_id}/listing/request`, {
    method: "POST", headers: { Authorization: `Bearer ${data().teacher.token}` },
  });
  expect(r.status).toBe(422);
  const body = await r.json();
  expect(body.error.code).toBe("listing_incomplete");
  // the link-access switch carries the new wording
  await expect(page.getByRole("switch", { name: t("catalog.listing.linkAccess") })).toBeVisible();
  await screens(page, "settings-off-incomplete");
  await page.context().close();
});

test("the teacher requests, withdraws and requests again", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  const block = await openSettings(page, data().ready_id);
  await expect(block).toHaveAttribute("data-state", "off");
  await expect(block.getByTestId("listing-missing")).toHaveCount(0);
  await button(block, "catalog.listing.request").click();
  await expect(block).toHaveAttribute("data-state", "pending");
  await button(block, "catalog.listing.withdraw").click();
  await expect(block).toHaveAttribute("data-state", "off");
  await button(block, "catalog.listing.request").click();
  await expect(block).toHaveAttribute("data-state", "pending");
  await expect(block.getByText(t("catalog.listing.states.pending"), { exact: true })).toBeVisible();
  await screens(page, "settings-pending");
  await page.context().close();
  // the second course goes to the queue through the API (the walk declines it)
  const asked = await api(data().teacher, "POST", `/courses/${data().declined_id}/listing/request`);
  expect(asked.listing.state).toBe("pending");
});

test("the admin: the overview row, Admin → Каталог, approve one, decline the other with a note", async ({ browser }) => {
  const page = await as(browser, seed().admin);
  await page.goto("/ru/admin");
  const row = page.getByTestId("needs-attention").locator('[data-attention="catalogPending"]').getByRole("link");
  await expect(row).toContainText(t("platformAdmin.overview.attention.catalogPending"));
  await expect(row).toContainText("2");
  await screens(page, "overview-attention");
  await row.click();
  await expect(page).toHaveURL(/\/ru\/admin\/catalog$/);
  await expect(page.getByRole("heading", { level: 1, name: t("platformAdmin.catalog.title") })).toBeVisible();
  const ready = page.locator("tr", { hasText: READY });
  const declined = page.locator("tr", { hasText: DECLINED });
  await expect(ready).toBeVisible();
  await expect(declined).toBeVisible();
  await expect(ready.getByRole("link", { name: "Асель Каталогова" })).toBeVisible();
  await expect(ready.getByText(t("platformAdmin.catalog.independent"))).toBeVisible();
  await expect(ready.getByRole("link", { name: t("platformAdmin.catalog.open") })).toHaveAttribute("href", `/ru/courses/catalog/${data().ready_id}`);
  await screens(page, "admin-pending");

  await ready.getByRole("button", { name: t("platformAdmin.catalog.approve") }).click();
  await expect(ready).toHaveCount(0);

  await declined.getByRole("button", { name: t("platformAdmin.catalog.more", { course: DECLINED }) }).click();
  await page.getByRole("menuitem", { name: t("platformAdmin.catalog.decline") }).click();
  const dialog = page.locator("dialog[open]");
  await expect(dialog.getByRole("heading", { name: t("platformAdmin.catalog.declineTitle") })).toBeVisible();
  await dialog.getByRole("button", { name: t("platformAdmin.catalog.decline") }).click();
  await expect(dialog.getByText(t("ui.reason.missing"))).toBeVisible(); // the note is required
  await dialog.getByRole("textbox", { name: new RegExp(t("platformAdmin.catalog.declineNote")) }).fill(NOTE);
  await screens(page, "admin-decline-dialog", { viewport: true });
  await dialog.getByRole("button", { name: t("platformAdmin.catalog.decline") }).click();
  await expect(dialog).toHaveCount(0);
  await expect(declined).toHaveCount(0);
  await expect(page.getByText(t("platformAdmin.catalog.empty.pending"))).toBeVisible();

  await page.getByRole("tab", { name: t("platformAdmin.catalog.tabs.listed") }).click();
  await expect(page.locator("tr", { hasText: READY })).toBeVisible();
  await page.getByRole("tab", { name: t("platformAdmin.catalog.tabs.declined") }).click();
  await expect(page.locator("tr", { hasText: DECLINED }).getByText(NOTE)).toBeVisible();
  await page.getByRole("tab", { name: t("platformAdmin.catalog.tabs.blocked") }).click();
  await expect(page).toHaveURL(/\/ru\/admin\/catalog\?state=blocked$/);
  const blocked = page.locator("tr", { hasText: "Снятый курс E2E" });
  await expect(blocked.getByRole("button", { name: t("platformAdmin.catalog.relist") })).toBeVisible();
  await expect(blocked.getByRole("link", { name: t("platformAdmin.catalog.open") })).toHaveCount(0); // its landing is closed
  await page.context().close();
});

test("the student finds the approved course in the catalog; the decline note never reaches them", async ({ browser }) => {
  const student = data().student;
  const page = await as(browser, student);
  await page.goto("/ru/courses/catalog?exam=other");
  await expect(page.locator("main").getByRole("link", { name: READY })).toBeVisible();
  await expect(page.locator("main").getByRole("link", { name: DECLINED })).toHaveCount(0);
  await expect(page.locator("main").getByRole("link", { name: "Снятый курс E2E" })).toHaveCount(0);
  await page.context().close();
  const list = await api(student, "GET", "/catalog/courses?q=E2E&limit=50");
  const ids = list.items.map((c: { id: string }) => c.id);
  expect(ids).toContain(data().ready_id);
  expect(ids).not.toContain(data().declined_id);
  // the declined course still opens by link (link access), without the note
  const landing = await fetch(`${seed().api}/api/v1/catalog/courses/${data().declined_id}`, { headers: { Authorization: `Bearer ${student.token}` } });
  expect(landing.status).toBe(200);
  expect(await landing.text()).not.toContain(NOTE.slice(0, 20));
  // the blocked course's landing is closed
  await api(student, "GET", `/catalog/courses/${data().blocked_id}`, undefined, [404]);
});

test("the teacher sees the note, the listed state, and no button on a blocked course", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  let block = await openSettings(page, data().declined_id);
  await expect(block).toHaveAttribute("data-state", "declined");
  await expect(block.getByText(t("catalog.listing.noteLabel"))).toBeVisible();
  await expect(block.getByText(NOTE)).toBeVisible();
  await expect(button(block, "catalog.listing.resend")).toBeEnabled();
  await screens(page, "settings-declined");

  block = await openSettings(page, data().ready_id);
  await expect(block).toHaveAttribute("data-state", "listed");
  await expect(button(block, "catalog.listing.remove")).toBeVisible();
  await expect(block.getByRole("link", { name: t("catalog.listing.openLanding") })).toHaveAttribute("href", `/ru/courses/catalog/${data().ready_id}`);
  await screens(page, "settings-listed");

  block = await openSettings(page, data().blocked_id);
  await expect(block).toHaveAttribute("data-state", "blocked");
  await expect(block.getByText(t("catalog.listing.states.blocked"), { exact: true })).toBeVisible();
  await expect(block.getByRole("button")).toHaveCount(0);
  await expect(block.getByRole("link", { name: t("catalog.listing.openLanding") })).toHaveCount(0);
  await screens(page, "settings-blocked");
  await page.context().close();
});

test("the teacher takes the listed course out of the catalog (confirmed)", async ({ browser }) => {
  const page = await as(browser, data().teacher);
  const block = await openSettings(page, data().ready_id);
  await button(block, "catalog.listing.remove").click();
  const dialog = page.locator("dialog[open]");
  await expect(dialog.getByText(t("catalog.listing.removeBody"))).toBeVisible();
  await dialog.getByRole("button", { name: t("catalog.listing.remove") }).click();
  await expect(block).toHaveAttribute("data-state", "off");
  await page.context().close();
  const list = await api(data().student, "GET", "/catalog/courses?q=E2E&limit=50");
  expect(list.items.map((c: { id: string }) => c.id)).not.toContain(data().ready_id);
});
