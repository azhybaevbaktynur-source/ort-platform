import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * FB8-5 S3 (STAFF_UX_AUDIT 4, 5): create a course (one main language, translations on request, the live card preview,
 * the template select only with a grant, the cover uploaded right after create) and the course settings sections
 * (`?section=` deep links, one Save per section, Danger zone for the owner only). With UX_SCREENS_DIR set, ru
 * screenshots at 375 / 1440 / 1920 of the create form and every settings section go to that folder.
 */
const OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);
const WIDTHS = [375, 1440, 1920] as const;

// ---- a tiny PNG encoder (RGB, no filter), as in course-cover.spec.ts
const CRC = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const b of buf) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}
function png(w: number, h: number): Buffer {
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y += 1) {
    const row = y * (w * 3 + 1);
    for (let x = 0; x < w; x += 1) {
      const f = x / (w - 1);
      raw[row + 1 + x * 3] = Math.round(40 + 200 * f);
      raw[row + 2 + x * 3] = Math.round(110 + 40 * f);
      raw[row + 3 + x * 3] = Math.round(220 - 180 * f);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0)),
  ]);
}

async function api(user: SeedUser, method: string, apiPath: string, body?: unknown) {
  const r = await fetch(`${seed().api}/api/v1${apiPath}`, {
    method,
    headers: { Authorization: `Bearer ${user.token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await r.text();
  expect(r.status, `${method} ${apiPath}: ${text.slice(0, 200)}`).toBeLessThan(300);
  return text ? JSON.parse(text) : null;
}

async function open(browser: Browser, user: SeedUser, width = 1440, height = 900): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width, height }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

/** No sideways scroll at 375 / 1440 / 1920; with UX_SCREENS_DIR, a full-page shot at each width (`reload`: the page is
 * opened again at each width, as a phone would, so the section tabs scroll the current one into view). */
async function shots(page: Page, name: string, reload = false) {
  const start = page.viewportSize()!;
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    if (reload) await page.reload();
    await settle(page);
    await page.waitForTimeout(150);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over, `${name} at ${width} scrolls sideways`).toBeLessThanOrEqual(0);
    if (OUT) {
      fs.mkdirSync(OUT, { recursive: true });
      await page.screenshot({ path: path.join(OUT, `${name}-ru-${width}.png`), fullPage: true, animations: "disabled", caret: "hide" });
    }
  }
  await page.setViewportSize(start);
}

const preview = (page: Page) => page.getByTestId("course-preview");

test("create: one main language, a translation on request, the live card, the cover after create", async ({ browser }) => {
  const teacher = seed().org_admin.independent; // personal organization only: no organization select
  const page = await open(browser, teacher);
  await page.goto("/ru/courses/new");
  await expect(page.getByRole("heading", { level: 1, name: t("courses.create.pageTitle") })).toBeVisible();
  // one language: the main language select, no language tabs, translations folded, no template select (no grant)
  await expect(page.getByLabel(t("courses.create.mainLanguage"))).toHaveValue("ru");
  await expect(page.getByRole("tab")).toHaveCount(0);
  const more = page.getByRole("button", { name: t("courses.create.addTranslations") });
  await expect(more).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#new-org")).toHaveCount(0);
  await expect(page.getByLabel(t("templates.field"))).toHaveCount(0);
  await shots(page, "create-empty");

  // the preview follows the title and the description
  const title = page.getByRole("textbox", { name: t("courses.create.courseTitle") });
  await title.fill("Алгебра E2E");
  await page.getByRole("textbox", { name: t("courses.create.description") }).fill("Курс для проверки формы.");
  await expect(preview(page).getByRole("heading", { name: "Алгебра E2E" })).toBeVisible();
  await expect(preview(page)).toContainText("Курс для проверки формы.");
  await expect(preview(page)).toContainText(t("courses.languages.ru"));

  // a Kyrgyz translation: tabs with words, the fallback hint
  await more.click();
  await page.getByRole("checkbox", { name: t("courses.languages.ky") }).check();
  const tabs = page.getByRole("tablist", { name: t("courses.create.courseTitle") });
  await expect(tabs.getByRole("tab", { name: `${t("courses.languages.ru")} (${t("courses.create.mainNote")})` })).toHaveAttribute("aria-selected", "true");
  await tabs.getByRole("tab", { name: `${t("courses.languages.ky")} (${t("courses.create.empty")})` }).click();
  await expect(page.getByText(t("courses.create.fallbackHint")).first()).toBeVisible();
  await page.getByRole("textbox", { name: t("courses.create.courseTitle") }).fill("Алгебра E2E (кырг.)");
  await expect(preview(page)).toContainText(`${t("courses.languages.ru")}, ${t("courses.languages.ky")}`);

  // a cover: the focus frame, the card shows the chosen side
  await page.getByTestId("cover-file").setInputFiles({ name: "wide.png", mimeType: "image/png", buffer: png(960, 300) });
  const frame = page.getByRole("slider", { name: t("courses.cover.focusLabel") });
  await frame.focus();
  await page.keyboard.press("End");
  await expect(frame).toHaveAttribute("aria-valuenow", "100");
  await expect(preview(page).locator("img")).toHaveCSS("object-position", "100% 50%");
  await page.getByRole("switch", { name: t("catalog.listing.linkAccess") }).click();
  await shots(page, "create-filled");

  await page.getByRole("button", { name: t("courses.create.submit") }).click();
  await expect(page).toHaveURL(/\/ru\/courses\/(?!new$)[^/?]+$/);
  const id = new URL(page.url()).pathname.split("/").pop()!;
  const course = await api(teacher, "GET", `/courses/${id}`);
  expect(course.languages.sort()).toEqual(["ky", "ru"]);
  expect(course.default_language).toBe("ru");
  expect(course.title).toEqual({ ru: "Алгебра E2E", ky: "Алгебра E2E (кырг.)" });
  expect(course.visibility).toBe("catalog");
  expect(course.cover_url).toMatch(/\.webp$/);
  expect(course.template ?? null).toBeNull();
  await page.context().close();
});

test("create: the template select appears only when the organization holds a grant", async ({ browser }) => {
  const s = seed();
  const teacher = s.org_admin.independent;
  const orgs = (await api(teacher, "GET", "/me/organizations?limit=100")).items as { id: string; kind: string; template_keys?: string[] }[];
  const personal = orgs.find((o) => o.kind === "personal")!;
  expect(personal.template_keys).toEqual([]);
  await api(s.admin, "PUT", `/platform/organizations/${personal.id}/templates/ort`);
  try {
    const page = await open(browser, teacher);
    await page.goto("/ru/courses/new");
    const select = page.getByLabel(t("templates.field"));
    await expect(select).toHaveValue("");
    await expect(page.getByText(t("templates.generalHint"))).toBeVisible();
    await select.selectOption("ort");
    await expect(page.getByText(t("templates.lockedHint"))).toBeVisible();
    await shots(page, "create-template");
    await page.getByRole("textbox", { name: t("courses.create.courseTitle") }).fill("ОРТ по шаблону E2E");
    await page.getByRole("button", { name: t("courses.create.submit") }).click();
    await expect(page).toHaveURL(/\/ru\/courses\/(?!new$)[^/?]+$/);
    const id = new URL(page.url()).pathname.split("/").pop()!;
    expect((await api(teacher, "GET", `/courses/${id}`)).template?.key).toBe("ort");
    await api(teacher, "DELETE", `/courses/${id}`);
    await page.context().close();
  } finally {
    await api(s.admin, "DELETE", `/platform/organizations/${personal.id}/templates/ort`);
  }
});

test("settings: sections as deep links, one Save per section, Danger zone only for the owner", async ({ browser }) => {
  const s = seed();
  const teacher = s.org_admin.independent;
  const course = await api(teacher, "POST", "/courses", { title: { ru: "Настройки E2E" }, languages: ["ru"], default_language: "ru" });
  const base = `/ru/courses/${course.id}/settings`;
  const page = await open(browser, teacher);
  await page.goto(base);
  const nav = page.getByRole("navigation", { name: t("courses.settings.sectionsLabel") });
  // fix round 2026-11-12 (1d): no Access / Pro tab for a teacher on their own course; its URL shows General
  const names = ["general", "cover", "enrollment", "grading", "danger"].map((k) => t(`courses.settings.sections.${k}`));
  await expect(nav.getByRole("link")).toHaveText(names);
  await expect(nav.getByRole("link", { name: names[0] })).toHaveAttribute("aria-current", "page");
  await expect(nav.getByRole("link", { name: t("courses.settings.sections.access") })).toHaveCount(0);

  // General: the title saves and the card follows
  await page.getByRole("textbox", { name: t("courses.create.courseTitle") }).fill("Настройки E2E: новое имя");
  await expect(preview(page).getByRole("heading", { name: "Настройки E2E: новое имя" })).toBeVisible();
  const general = page.getByTestId("settings-general");
  await general.getByRole("button", { name: t("lms.common.save") }).click();
  await expect(general.getByText(t("courses.settings.saved"))).toBeVisible();
  expect((await api(teacher, "GET", `/courses/${course.id}`)).title.ru).toBe("Настройки E2E: новое имя");
  await shots(page, "settings-general");

  // every other section by its link
  for (const key of ["cover", "enrollment", "grading", "danger"]) {
    await nav.getByRole("link", { name: t(`courses.settings.sections.${key}`) }).click();
    await expect(page).toHaveURL(new RegExp(`\\?section=${key}$`));
    await expect(nav.getByRole("link", { name: t(`courses.settings.sections.${key}`) })).toHaveAttribute("aria-current", "page");
    await shots(page, `settings-${key}`, true);
  }

  // Enrollment: the limit saves on its own
  await page.goto(`${base}?section=enrollment`);
  await page.getByLabel(t("courses.create.limit")).fill("25");
  const form = page.locator("form", { has: page.locator("#s-mode") });
  await form.getByRole("button", { name: t("lms.common.save") }).click();
  await expect(form.getByText(t("courses.settings.saved"))).toBeVisible();
  expect((await api(teacher, "GET", `/courses/${course.id}`)).enrollment_limit).toBe(25);

  // Course status, at the top of General (the old Access / Pro link lands there too): publish is the one button;
  // unpublish lives in the status menu
  await page.goto(`${base}?section=access`);
  await expect(nav.getByRole("link", { name: names[0] })).toHaveAttribute("aria-current", "page");
  const status = page.getByTestId("settings-status");
  await expect(page.getByRole("heading", { name: t("courses.settings.lifecycle") })).toBeVisible();
  await status.getByRole("button", { name: t("courses.settings.publish") }).click();
  await expect(status.getByRole("button", { name: t("courses.settings.statusMenu") })).toBeVisible();
  expect((await api(teacher, "GET", `/courses/${course.id}`)).status).toBe("published");
  await expect(page.getByText(t("courses.settings.access.platformPro"))).toHaveCount(0);
  await page.context().close();

  // the admin on the ORT course: Danger zone only if they own it (a second backend's startup bootstrap, e.g. in
  // admin-mfa-gate, can hand the ORT courses to the admin, so the rule is checked against `is_owner`, not assumed);
  // a platform course explains Pro
  const ortOwner = (await api(s.admin, "GET", `/courses/${s.course_id}`)).is_owner as boolean;
  const admin = await open(browser, s.admin);
  await admin.goto(`/ru/courses/${s.course_id}/settings?section=danger`);
  const anav = admin.getByRole("navigation", { name: t("courses.settings.sectionsLabel") });
  const shown = t(`courses.settings.sections.${ortOwner ? "danger" : "general"}`);
  await expect(anav.getByRole("link", { name: shown })).toHaveAttribute("aria-current", "page");
  await expect(anav.getByRole("link", { name: t("courses.settings.sections.danger") })).toHaveCount(ortOwner ? 1 : 0);
  await expect(anav.getByRole("link", { name: t("courses.settings.sections.access") })).toBeVisible();
  await admin.goto(`/ru/courses/${s.course_id}/settings?section=access`);
  await expect(anav.getByRole("link", { name: t("courses.settings.sections.access") })).toHaveAttribute("aria-current", "page");
  await expect(admin.getByText(t("courses.settings.access.platformPro"))).toBeVisible();
  await expect(admin.getByRole("link", { name: t("courses.settings.access.paidExamsLink") })).toHaveAttribute("href", "/ru/admin/access/exams");
  await shots(admin, "settings-access-platform", true);
  await admin.context().close();
  await api(teacher, "DELETE", `/courses/${course.id}`);
});
