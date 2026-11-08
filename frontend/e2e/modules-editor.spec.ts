import fs from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * F5c (docs/phases/COURSE_LESSONS_DESIGN.md §6, §7.3, §9): the teacher's module editor on the Course page.
 * - a teacher course: the module's one "+ Добавить" menu (FB8 S2: video, page, file, test, link, ...), "Видео" (dialog
 *   with the YouTube / Vimeo hint and minutes), "Ссылка" inline with minutes, the publish switch (`role="switch"`), ↑ ↓
 *   reorder by keyboard (focus stays on the pressed button), the minutes chip (set, change, clear), the drag handle
 *   visible at desktop width, and no Pro lock (the server refuses `paid` outside platform courses);
 * - a platform course (the platform admin's own course in the platform organization): the Pro lock (FB8 S2: a
 *   `LockToggle`, `aria-pressed`, tooltip) is there, asks first, turns gold and is stored as `access_tier = paid`; off
 *   again is immediate.
 * Each test builds its own course through the API, so no other spec sees it.
 * With F5C_SHOTS_DIR=<dir> the last test writes the editor at 375, 1440 and 1920 px (ru) for the UX check.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.F5C_SHOTS_DIR ? path.resolve(process.env.F5C_SHOTS_DIR) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const MOD = "Модуль F5c";
const VIDEO = "Сравнение величин";
const LINK = "Справочник";
const PAGE = "Разбор задач";

async function api(user: SeedUser, method: string, p: string, body?: unknown, ok = [200, 201, 204]) {
  const r = await fetch(`${seed().api}/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  expect(ok, `${method} ${p} -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return text ? JSON.parse(text) : null;
}

async function open(browser: Browser, user: SeedUser, viewport: { width: number; height: number } = VIEWPORTS.desktop): Promise<Page> {
  const ctx = await browser.newContext({ viewport, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

interface Item { id: string; kind: string; url: string | null; duration_s: number | null; position: number }
/** FB8 S2: the module's "+ Добавить" menu, then one entry. */
async function addVia(page: Page, card: ReturnType<Page["locator"]>, module: string, label: string) {
  await card.getByRole("button", { name: t("coursePage.add", { title: module }) }).click();
  await page.getByRole("menu").getByRole("menuitem", { name: label, exact: true }).click();
}

async function items(user: SeedUser, cid: string, mid: string): Promise<Item[]> {
  const out = await api(user, "GET", `/courses/${cid}/modules`);
  const m = out.modules.find((x: { id: string }) => x.id === mid);
  return [...m.items].sort((a: Item, b: Item) => a.position - b.position);
}

test.describe("F5c teacher module editor", () => {
  test("teacher course: add menu, a video with minutes, a link, publish switch, reorder by keyboard, minutes chip; no Pro lock", async ({ browser }) => {
    const teacher = seed().modules.teacher;
    const course = await api(teacher, "POST", "/courses", { title: { ru: "Редактор F5c" }, languages: ["ru"], default_language: "ru" });
    const cid = course.id as string;
    const mod = await api(teacher, "POST", `/courses/${cid}/modules`, { title: { ru: MOD }, published: false });
    const out = await api(teacher, "GET", `/courses/${cid}/modules`);
    expect(out.is_platform_course).toBe(false);

    const tp = await open(browser, teacher);
    await tp.goto(`/${L}/courses/${cid}`);
    const card = tp.locator(`#m-${mod.id}`);
    await expect(card).toBeVisible();
    // the empty module says what to do; one "+ Добавить" button (no row of quick-add buttons) opens the lesson kinds
    await expect(card.getByText(t("modules.editor.emptyModule"))).toBeVisible();
    const addButton = card.getByRole("button", { name: t("coursePage.add", { title: MOD }) });
    await expect(addButton).toHaveCount(1);
    await expect(addButton).toHaveText(new RegExp(t("modules.editor.addMenu")));
    await expect(card.getByRole("button", { name: t("modules.editor.addVideo"), exact: true })).toHaveCount(0);
    await addButton.click();
    const menu = tp.getByRole("menu");
    for (const label of [t("modules.editor.addVideo"), t("coursePage.addItems.page"), t("coursePage.addItems.file"), t("coursePage.addItems.quiz"),
      t("coursePage.addItems.link"), t("coursePage.addItems.assignment"), t("coursePage.addItems.header"), t("coursePage.addExisting")]) {
      await expect(menu.getByRole("menuitem", { name: label, exact: true })).toBeVisible();
    }
    await tp.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(addButton).toBeFocused();
    // never on a teacher course
    await expect(tp.getByRole("button", { name: t("modules.editor.proSwitch", { title: MOD }) })).toHaveCount(0);
    // the module's publish switch: a draft, the header says so in text too
    const modSwitch = card.getByRole("switch", { name: t("modules.editor.publishToggle", { title: MOD }), exact: true });
    await expect(modSwitch).toHaveAttribute("aria-checked", "false");
    await expect(card.getByText(t("modules.editor.draft"), { exact: true }).first()).toBeVisible();

    // ---- + Видео: the hint follows the address (client guess), minutes go in as seconds
    await addVia(tp, card, MOD, t("modules.editor.addVideo"));
    const dlg = tp.getByRole("dialog", { name: t("modules.editor.video.title") });
    const urlField = dlg.getByLabel(t("modules.editor.video.url"));
    await urlField.fill("https://example.com/watch");
    await expect(dlg.getByText(t("modules.editor.video.notDetected"))).toBeVisible();
    await urlField.fill("https://youtu.be/dQw4w9WgXcQ");
    await expect(dlg.getByText(t("modules.editor.video.detected", { provider: "YouTube" }))).toBeVisible();
    await dlg.getByLabel(t("modules.editor.video.name")).fill(VIDEO);
    await dlg.getByLabel(t("modules.editor.video.minutes")).fill("601");
    await dlg.getByRole("button", { name: t("modules.add.submit") }).click();
    await expect(dlg.getByText(t("modules.editor.durationInvalid"))).toBeVisible();
    await dlg.getByLabel(t("modules.editor.video.minutes")).fill("6");
    await dlg.getByRole("button", { name: t("modules.add.submit") }).click();
    await expect(dlg).toHaveCount(0);
    await expect(card.getByRole("button", { name: t("modules.editor.durationEdit", { title: VIDEO, value: t("modules.editor.minutes", { n: 6 }) }) })).toBeVisible();

    // ---- + Ссылка: the inline form takes minutes too
    await addVia(tp, card, MOD, t("coursePage.addItems.link"));
    const linkTitle = card.getByRole("textbox", { name: t("coursePage.inlineTitle", { kind: t("coursePage.addItems.link") }) });
    await linkTitle.fill(LINK);
    await card.getByRole("textbox", { name: t("modules.add.url") }).fill("https://example.com/handbook");
    await card.getByRole("spinbutton", { name: t("modules.editor.linkMinutes") }).fill("3");
    await linkTitle.press("Enter");
    await expect(card.getByRole("button", { name: t("modules.editor.durationEdit", { title: LINK, value: t("modules.editor.minutes", { n: 3 }) }) })).toBeVisible();
    let rows = await items(teacher, cid, mod.id);
    expect(rows.map((r) => [r.kind, r.duration_s])).toEqual([["url", 360], ["url", 180]]);
    // the header line sums the published lessons
    await expect(card.getByText(`${tr(L, "modules.editor.lessons_few", { n: 2 })} · ${t("modules.editor.minutes", { n: 9 })}`)).toBeVisible();
    // drag handles are visible at desktop width (not only on hover), one per module header and row
    await expect(card.locator("[draggable=true]")).toHaveCount(3);
    await expect(card.locator("[draggable=true]").first()).toBeVisible();

    // ---- publish switch: the module goes live, the server stores it, off again
    await modSwitch.click();
    await expect(modSwitch).toHaveAttribute("aria-checked", "true");
    await expect.poll(async () => (await api(teacher, "GET", `/courses/${cid}/modules`)).modules.find((x: { id: string }) => x.id === mod.id)?.published).toBe(true);
    await modSwitch.click();
    await expect(modSwitch).toHaveAttribute("aria-checked", "false");
    await expect.poll(async () => (await api(teacher, "GET", `/courses/${cid}/modules`)).modules.find((x: { id: string }) => x.id === mod.id)?.published).toBe(false);

    // ---- ↑ ↓ by keyboard: focus stays on the pressed button of the moved row
    const up = card.getByRole("button", { name: t("modules.editor.moveItemUp", { title: LINK }) });
    await up.focus();
    await tp.keyboard.press("Enter");
    await expect.poll(async () => (await items(teacher, cid, mod.id)).map((r) => r.duration_s)).toEqual([180, 360]);
    await expect(up).toBeFocused();
    await expect(up).toHaveAttribute("aria-disabled", "true");
    await tp.keyboard.press("Enter"); // the top row: nothing happens
    const down = card.getByRole("button", { name: t("modules.editor.moveItemDown", { title: LINK }) });
    await tp.keyboard.press("Tab");
    await expect(down).toBeFocused();
    await tp.keyboard.press("Space");
    await expect.poll(async () => (await items(teacher, cid, mod.id)).map((r) => r.duration_s)).toEqual([360, 180]);
    await expect(down).toBeFocused();

    // ---- minutes chip: change (Enter), cancel (Esc), clear (empty)
    const chip = (value: number | null) => card.getByRole("button", {
      name: value === null ? t("modules.editor.durationSet", { title: VIDEO }) : t("modules.editor.durationEdit", { title: VIDEO, value: t("modules.editor.minutes", { n: value }) }),
    });
    const field = card.getByRole("spinbutton", { name: t("modules.editor.durationField", { title: VIDEO }) });
    await chip(6).click();
    await field.fill("12");
    await field.press("Enter");
    await expect(chip(12)).toBeVisible();
    await expect(chip(12)).toBeFocused();
    await chip(12).click();
    await field.fill("40");
    await field.press("Escape");
    await expect(chip(12)).toBeVisible();
    await chip(12).click();
    await field.fill("0");
    await field.press("Enter");
    await expect(field).toHaveAttribute("aria-invalid", "true");
    await field.fill("");
    await field.press("Enter");
    await expect(chip(null)).toBeVisible();
    rows = await items(teacher, cid, mod.id);
    expect(rows.map((r) => r.duration_s)).toEqual([null, 180]);

    // tests and headers carry no minutes chip
    await addVia(tp, card, MOD, t("coursePage.addItems.quiz"));
    const quizTitle = card.getByRole("textbox", { name: t("coursePage.inlineTitle", { kind: t("coursePage.addItems.quiz") }) });
    await quizTitle.fill("Тест F5c");
    await quizTitle.press("Enter");
    await expect(card.getByRole("link", { name: "Тест F5c", exact: true })).toBeVisible();
    await expect(card.getByRole("button", { name: t("modules.editor.durationSet", { title: "Тест F5c" }) })).toHaveCount(0);
    await settle(tp);
    await tp.context().close();
  });

  test("platform course: the Pro lock asks first, turns gold and is stored; off again at once", async ({ browser }) => {
    const admin = seed().admin;
    const ort = await api(admin, "GET", `/courses/${seed().course_id}`);
    const course = await api(admin, "POST", "/courses", {
      title: { ru: "Платформа F5c" }, languages: ["ru"], default_language: "ru", organization_id: ort.organization_id,
    });
    const cid = course.id as string;
    const free = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: "Математика I" }, published: true });
    const pro = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: "Аналогии" }, published: true });
    // a free module that waits for the Pro one gets the editor's warning (§5)
    const after = await api(admin, "POST", `/courses/${cid}/modules`, { title: { ru: "Чтение" }, published: true });
    await api(admin, "PUT", `/courses/${cid}/modules/${after.id}/prerequisites`, { module_ids: [pro.id] });
    const vid = await api(admin, "POST", `/courses/${cid}/modules/${free.id}/items`, { kind: "url", url: "https://youtu.be/dQw4w9WgXcQ", title_override: { ru: VIDEO }, published: true, duration_s: 360 });
    await api(admin, "POST", `/courses/${cid}/modules/${free.id}/items`, { kind: "url", url: "https://vimeo.com/76979871", title_override: { ru: "Приёмы сравнения" }, published: true, duration_s: 480 });
    await api(admin, "POST", `/courses/${cid}/modules/${free.id}/items`, { kind: "url", url: "https://example.com/notes", title_override: { ru: PAGE }, published: true });
    await api(admin, "PUT", `/courses/${cid}/modules/${free.id}/items/${vid.id}/requirement`, { type: "view" });
    expect((await api(admin, "GET", `/courses/${cid}/modules`)).is_platform_course).toBe(true);

    const ap = await open(browser, admin);
    await ap.goto(`/${L}/courses/${cid}`);
    const card = ap.locator(`#m-${pro.id}`);
    const sw = card.getByRole("button", { name: t("modules.editor.proSwitch", { title: "Аналогии" }) });
    await expect(sw).toHaveAttribute("aria-pressed", "false");
    await expect(sw).toHaveAttribute("title", t("modules.editor.proHintOff"));
    await sw.click();
    const confirm = ap.getByRole("alertdialog", { name: t("modules.editor.proConfirmTitle") });
    await expect(confirm.getByText(t("modules.editor.proConfirmBody"))).toBeVisible();
    await confirm.getByRole("button", { name: t("modules.editor.proConfirm") }).click();
    await expect(sw).toHaveAttribute("aria-pressed", "true");
    await expect(sw).toHaveAttribute("title", t("modules.editor.proHintOn"));
    let mods = (await api(admin, "GET", `/courses/${cid}/modules`)).modules as { id: string; access_tier: string }[];
    expect(mods.find((m) => m.id === pro.id)?.access_tier).toBe("paid");
    await expect(ap.locator(`#m-${after.id}`).getByText(t("modules.editor.proPrereqWarning"))).toBeVisible();
    await expect(ap.locator(`#m-${free.id}`).getByText(t("modules.editor.proPrereqWarning"))).toHaveCount(0);

    if (SHOTS) {
      await settle(ap);
      await ap.screenshot({ path: path.join(SHOTS, "editor-1440-ru.png"), fullPage: true });
      const phone = await open(browser, admin, { width: 375, height: 812 });
      await phone.goto(`/${L}/courses/${cid}`);
      await expect(phone.locator(`#m-${pro.id}`)).toBeVisible();
      await settle(phone);
      await phone.screenshot({ path: path.join(SHOTS, "editor-375-ru.png"), fullPage: true });
      await phone.getByRole("button", { name: t("coursePage.add", { title: "Аналогии" }) }).click();
      await phone.screenshot({ path: path.join(SHOTS, "editor-375-ru-add.png") });
      await phone.context().close();
      // FB8 S2: the wide desktop and the open "+ Добавить" menu
      const wide = await open(browser, admin, { width: 1920, height: 1080 });
      await wide.goto(`/${L}/courses/${cid}`);
      await expect(wide.locator(`#m-${pro.id}`)).toBeVisible();
      await settle(wide);
      await wide.screenshot({ path: path.join(SHOTS, "editor-1920-ru.png"), fullPage: true });
      await wide.context().close();
      await ap.locator(`#m-${free.id}`).getByRole("button", { name: t("coursePage.add", { title: "Математика I" }) }).click();
      await ap.screenshot({ path: path.join(SHOTS, "editor-1440-ru-add.png") });
      await ap.keyboard.press("Escape");
      await addVia(ap, ap.locator(`#m-${free.id}`), "Математика I", t("modules.editor.addVideo"));
      await ap.getByRole("dialog").getByLabel(t("modules.editor.video.url")).fill("https://youtu.be/dQw4w9WgXcQ");
      await ap.screenshot({ path: path.join(SHOTS, "editor-1440-ru-video.png") });
      await ap.keyboard.press("Escape");
    }

    // off: no question, back to open for everyone
    await sw.click();
    await expect(sw).toHaveAttribute("aria-pressed", "false");
    mods = (await api(admin, "GET", `/courses/${cid}/modules`)).modules;
    expect(mods.find((m) => m.id === pro.id)?.access_tier).toBe("free");
    await settle(ap);
    await ap.context().close();
  });
});
