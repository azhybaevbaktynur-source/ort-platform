import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { seed, settle, signIn, tr, type SeedUser } from "./helpers";

/**
 * F7b (STUDENT_UI_FIX_PLAN 7.1): the course cover section in course settings and on the platform admin's page of a
 * platform course. Client checks (type, too small), the focus frame (keyboard), save (the course overview banner shows
 * the WebP from cover_url), remove with confirmation. Screenshots of the section only with UX_SCREENS_DIR set.
 */
const OUT = process.env.UX_SCREENS_DIR ? path.resolve(process.env.UX_SCREENS_DIR) : null;
const t = (key: string, vars: Record<string, string | number> = {}) => tr("ru", key, vars);

// ---- a tiny PNG encoder (RGB, no filter): test images without image libraries
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
/** A horizontal gradient: blue on the left, orange on the right (the crop side is visible on screenshots). */
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
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // RGB
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

async function open(browser: Browser, user: SeedUser, width: number, height = 900): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width, height }, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
  const page = await ctx.newPage();
  await signIn(page, user);
  return page;
}

/** No sideways scroll; with UX_SCREENS_DIR, a screenshot of the cover section. */
async function look(page: Page, name: string) {
  await settle(page);
  await page.waitForTimeout(200);
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, `${name} scrolls sideways`).toBeLessThanOrEqual(0);
  if (OUT) {
    fs.mkdirSync(OUT, { recursive: true });
    await page.getByTestId("course-cover-section").locator("xpath=..").screenshot({ path: path.join(OUT, `${name}.png`), animations: "disabled" });
  }
}

/** A published course with one published module (the student overview shows its banner) and one joined student. */
async function makeCourse(): Promise<{ id: string; teacher: SeedUser; student: SeedUser }> {
  const { teacher, student } = seed().quiz_editor;
  const title = { ru: "Курс с обложкой", ky: "Мукабасы бар курс", en: "Course with a cover" };
  const course = await api(teacher, "POST", "/courses", { title, languages: ["ru", "ky", "en"], default_language: "ru" });
  await api(teacher, "POST", `/courses/${course.id}/publish`, {});
  const page = await api(teacher, "POST", `/courses/${course.id}/pages`, { title: "Введение", language: "ru", body_md: "Текст урока.", published: true });
  const mod = await api(teacher, "POST", `/courses/${course.id}/modules`, { title: { ru: "Модуль 1" }, published: true });
  await api(teacher, "POST", `/courses/${course.id}/modules/${mod.id}/items`, { kind: "page", page_id: page.id, published: true });
  await api(student, "POST", "/courses/join", { code: course.join_code });
  return { id: course.id, teacher, student };
}

const section = (page: Page) => page.getByTestId("course-cover-section");

test("teacher uploads a cover with a chosen focus, the overview shows it, then removes it", async ({ browser }) => {
  const c = await makeCourse();

  for (const width of [375, 1440]) {
    const page = await open(browser, c.teacher, width);
    await page.goto(`/ru/courses/${c.id}/settings?section=cover`);
    await expect(page.getByRole("heading", { name: t("courses.cover.title") })).toBeVisible();
    await expect(section(page).getByText(t("courses.cover.default"))).toBeVisible();
    await look(page, `cover-default-${width}`);
    await page.context().close();
  }

  const page = await open(browser, c.teacher, 1440);
  await page.goto(`/ru/courses/${c.id}/settings?section=cover`);
  const file = section(page).getByTestId("cover-file");

  // client checks: wrong type, too small (nothing is sent)
  await file.setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("not an image") });
  await expect(section(page).getByText(t("courses.cover.errors.image_type_unsupported"))).toBeVisible();
  await file.setInputFiles({ name: "small.png", mimeType: "image/png", buffer: png(200, 100) });
  await expect(section(page).getByText(t("courses.cover.errors.image_too_small"))).toBeVisible();

  // a wide image: the frame moves sideways; End = the right edge
  await file.setInputFiles({ name: "wide.png", mimeType: "image/png", buffer: png(960, 300) });
  const frame = section(page).getByRole("slider", { name: t("courses.cover.focusLabel") });
  await expect(frame).toHaveAttribute("aria-valuenow", "50");
  await expect(frame).toHaveAttribute("aria-orientation", "horizontal");
  await frame.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(frame).toHaveAttribute("aria-valuenow", "45");
  await page.keyboard.press("End");
  await expect(frame).toHaveAttribute("aria-valuenow", "100");
  // FB8-5 S3: the course card beside the section previews the chosen frame
  await expect(page.getByTestId("course-preview").locator("img")).toHaveCSS("object-position", "100% 50%");
  // a click on the left part centres the frame there (clamped to the left edge)
  const area = section(page).getByTestId("cover-focus-area");
  const box = (await area.boundingBox())!;
  await page.mouse.click(box.x + 4, box.y + box.height / 2);
  await expect(frame).toHaveAttribute("aria-valuenow", "0");
  await frame.focus();
  await page.keyboard.press("End");
  await look(page, "cover-pick-1440");

  await section(page).getByRole("button", { name: t("courses.cover.save") }).click();
  await expect(section(page).getByRole("status")).toHaveText(t("courses.cover.savedMsg"));
  const saved = await api(c.teacher, "GET", `/courses/${c.id}`);
  expect(saved.cover_url).toMatch(/\.webp$/);
  const current = section(page).getByTestId("cover-current");
  await expect(current).toHaveAttribute("data-cover-url", saved.cover_url);
  const img = page.getByTestId("course-preview").locator("img"); // FB8-5 S3: the card preview shows the saved cover
  await expect(img).toHaveAttribute("src", saved.cover_url);
  // the server kept 528 x 297 (the largest 16:9 box of 960 x 300, a multiple of 16 x 9)
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => [el.naturalWidth, el.naturalHeight])).toEqual([528, 297]);
  await look(page, "cover-saved-1440");

  // the student's course overview banner shows the same WebP
  const sp = await open(browser, c.student, 375);
  await sp.goto(`/ru/courses/${c.id}`);
  const banner = sp.locator('section[aria-labelledby="course-overview-title"] img').first();
  await expect(banner).toHaveAttribute("src", saved.cover_url);
  await expect.poll(() => banner.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBe(528);
  await sp.context().close();

  // the phone picker
  const phone = await open(browser, c.teacher, 375);
  await phone.goto(`/ru/courses/${c.id}/settings?section=cover`);
  await section(phone).getByTestId("cover-file").setInputFiles({ name: "tall.png", mimeType: "image/png", buffer: png(400, 600) });
  await expect(section(phone).getByRole("slider", { name: t("courses.cover.focusLabel") })).toHaveAttribute("aria-orientation", "vertical");
  await look(phone, "cover-pick-375");
  await section(phone).getByRole("button", { name: t("lms.common.cancel") }).click();
  await expect(section(phone).getByTestId("cover-current")).toHaveAttribute("data-cover-url", saved.cover_url);
  await phone.context().close();

  // remove (confirmed): the default cover again
  await section(page).getByRole("button", { name: t("courses.cover.remove") }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByText(t("courses.cover.removeBody"))).toBeVisible();
  await dialog.getByRole("button", { name: t("courses.cover.remove") }).click();
  await expect(section(page).getByRole("status")).toHaveText(t("courses.cover.removedMsg"));
  await expect(section(page).getByText(t("courses.cover.default"))).toBeVisible();
  expect((await api(c.teacher, "GET", `/courses/${c.id}`)).cover_url).toBeNull();
  await page.context().close();
});

test("platform admin sets the cover of a platform course; other courses have no cover section there", async ({ browser }) => {
  const s = seed();
  const page = await open(browser, s.admin, 1440);
  await page.goto(`/ru/admin/courses/${s.access!.course_id}`);
  await expect(page.getByRole("heading", { name: t("courses.cover.title") })).toBeVisible();
  await section(page).getByTestId("cover-file").setInputFiles({ name: "wide.png", mimeType: "image/png", buffer: png(640, 360) });
  await expect(section(page).getByText(t("courses.cover.alreadyWide"))).toBeVisible();
  await section(page).getByRole("button", { name: t("courses.cover.save") }).click();
  await expect(section(page).getByRole("status")).toHaveText(t("courses.cover.savedMsg"));
  await expect(section(page).getByTestId("cover-current").locator("img")).toHaveAttribute("src", /\.webp$/);
  await look(page, "cover-admin-1440");
  // leave the shared ORT course as it was
  await section(page).getByRole("button", { name: t("courses.cover.remove") }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: t("courses.cover.remove") }).click();
  await expect(section(page).getByText(t("courses.cover.default"))).toBeVisible();

  await page.goto(`/ru/admin/courses/${s.quiz_editor.course_id}`);
  await expect(page.getByRole("heading", { name: t("platformAdmin.courses.roster") })).toBeVisible();
  await expect(page.getByRole("heading", { name: t("courses.cover.title") })).toHaveCount(0);
  await page.context().close();
});
