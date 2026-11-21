import { execFileSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { api, E2E_DIR, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";

/**
 * Lesson videos (docs/phases/LESSON_VIDEOS.md), integration walk in ru. An approved teacher builds a course through the
 * API: module 1 = two `video` items of one uploaded MP4 (fixtures/lesson-video.mp4: 20 s, 320×180, H.264, no audio,
 * faststart, 65 KB) with WebVTT captions, module 2 = a page. The student: the lesson shows <video> with the dev stream
 * address, plays (muted), the speed menu sets playbackRate 1.5, the captions track is there; a pause at 8 s is
 * remembered and restored after a reload; a seek to 95 % sends the view fact (done on the lesson and in the syllabus);
 * «Просмотрено» on the second item marks it done. Access: an outsider gets 404 on /play; a Pro module of a platform
 * course gives 403 `item_locked` to a student without Pro; the dev stream refuses a tampered and an expired token (403)
 * and answers a Range request with 206. Staff: the outline shows the video row with its duration; «Добавить» → «Видео»
 * uploads the same file with a progress bar (dedup: the same video, 200) and adds a row.
 *
 * Playback needs H.264 in the browser (installed Chrome locally); a browser without it (open-source Chromium) skips the
 * playback steps only.
 *
 * LV_SHOTS=1: the student lesson with the player at 375 / 1440 / 1920 px and the staff upload dialog at 1440 (ru) as
 * WebP (e2e/shots_webp.py, system python3 with Pillow) into docs/phases/LESSON_VIDEOS_screens/. Not baselines.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.LV_SHOTS === "1";
const PNG_DIR = path.join(E2E_DIR, "lesson-video-shots");
const OUT_DIR = path.resolve(__dirname, "../../docs/phases/LESSON_VIDEOS_screens");
const WIDTHS = [375, 1440, 1920] as const;
const MP4 = path.join(__dirname, "fixtures/lesson-video.mp4");
const VTT = path.join(__dirname, "fixtures/lesson-video.vtt");

const COURSE = "Дроби: видеоуроки E2E";
const M1 = "Сравнение дробей";
const M2 = "Разбор после видео";
const V1 = "Видеоурок: общий знаменатель";
const V2 = "Видеоурок: повторение";
const P2 = "Конспект урока";
const PRO_COURSE = "Pro видеокурс E2E";

interface PlayOut { url: string; expires_at: string; duration_s: number; width: number; height: number; captions_url: string | null }

/** `fetch` against the scratch API as `user` (raw response, any status). */
async function raw(user: SeedUser | null, method: string, p: string, init: { body?: BodyInit; headers?: Record<string, string> } = {}) {
  const url = p.startsWith("http") ? p : p.startsWith("/api/v1/") ? `${seed().api}${p}` : `${seed().api}/api/v1${p}`;
  return fetch(url, {
    method, body: init.body,
    headers: { ...(user ? { Authorization: `Bearer ${user.token}` } : {}), ...(init.headers ?? {}) },
  });
}

/** Upload the fixture MP4 (multipart) into `cid`. */
async function uploadVideo(user: SeedUser, cid: string, title: string) {
  const form = new FormData();
  form.append("file", new Blob([new Uint8Array(fs.readFileSync(MP4))], { type: "video/mp4" }), "lesson-video.mp4");
  form.append("title", title);
  const r = await raw(user, "POST", `/courses/${cid}/videos`, { body: form });
  const text = await r.text();
  expect([200, 201], `upload -> ${r.status} ${text.slice(0, 300)}`).toContain(r.status);
  return { status: r.status, video: JSON.parse(text) as { id: string; duration_s: number; width: number; height: number; has_captions: boolean } };
}

/** The dev stream's token for `videoId` expiring at `exp` (the scratch server's throwaway key; stream.py). */
function streamToken(videoId: string, exp: number): string {
  const secret = fs.readFileSync(path.join(E2E_DIR, "cwd/secret_key"), "utf-8");
  const key = crypto.createHmac("sha256", secret).update("lms-video-stream-v1").digest();
  const sig = crypto.createHmac("sha256", key).update(`${videoId}|${exp}`).digest("base64url");
  return `${exp}.${sig}`;
}

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  await page.screenshot({ path: path.join(PNG_DIR, `${name}.png`), animations: "disabled", caret: "hide" });
}

/** At 375 / 1440 / 1920: no page scroll sideways; with LV_SHOTS a PNG of the viewport with `focus` in its middle. */
async function widths(page: Page, name: string, focus: Locator) {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page, false);
    await noHorizontalScroll(page);
    await focus.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await settle(page, false);
    await shot(page, `${name}-${width}-ru`);
  }
  await page.setViewportSize(VIEWPORTS.desktop);
  await settle(page, false);
}

const videoEl = (page: Page) => page.locator("video");
const currentTime = (page: Page) => videoEl(page).evaluate((v: HTMLVideoElement) => v.currentTime);

test.describe("lesson videos (ru)", () => {
  test("player: stream, speed, captions, position memory, done at 95 %, Просмотрено; access; staff upload", async ({ page, browser }) => {
    test.setTimeout(300_000);
    if (SHOTS) { fs.rmSync(PNG_DIR, { recursive: true, force: true }); fs.mkdirSync(PNG_DIR, { recursive: true }); }
    const s = seed();
    const { teacher, student, outsider } = s.lesson_video;

    // ---- the course: module 1 = two video items of one MP4 with captions, module 2 = a page
    const c = await api(teacher, "POST", "/courses", { title: { ru: COURSE }, languages: ["ru"], default_language: "ru" });
    const cid = c.id as string;
    await api(teacher, "POST", `/courses/${cid}/publish`, {});
    await api(student, "POST", "/courses/join", { code: c.join_code });
    const { status: firstStatus, video } = await uploadVideo(teacher, cid, V1);
    expect(firstStatus).toBe(201);
    expect(video).toMatchObject({ duration_s: 20, width: 320, height: 180, has_captions: false });
    const cap = await raw(teacher, "PUT", `/courses/${cid}/videos/${video.id}/captions`, {
      body: fs.readFileSync(VTT), headers: { "Content-Type": "text/vtt" },
    });
    expect(cap.status, await cap.clone().text()).toBe(200);
    expect((await cap.json()).has_captions).toBe(true);

    const m1 = (await api(teacher, "POST", `/courses/${cid}/modules`, { title: { ru: M1 }, published: true })).id as string;
    const v1 = (await api(teacher, "POST", `/courses/${cid}/modules/${m1}/items`, { kind: "video", video_id: video.id, title_override: { ru: V1 }, published: true })).id as string;
    const v2 = (await api(teacher, "POST", `/courses/${cid}/modules/${m1}/items`, { kind: "video", video_id: video.id, title_override: { ru: V2 }, published: true })).id as string;
    const m2 = (await api(teacher, "POST", `/courses/${cid}/modules`, { title: { ru: M2 }, published: true })).id as string;
    const pg = await api(teacher, "POST", `/courses/${cid}/pages`, { title: P2, language: "ru", body_md: "Итоги видеоурока.", published: true });
    await api(teacher, "POST", `/courses/${cid}/modules/${m2}/items`, { kind: "page", page_id: pg.id, published: true });

    const itemOut = async (itemId: string) => {
      const out = await api(student, "GET", `/courses/${cid}/modules`);
      for (const m of out.modules as { items: { id: string; done?: boolean; video_file?: unknown }[] }[]) {
        const it = m.items.find((x) => x.id === itemId);
        if (it) return it;
      }
      throw new Error(`item ${itemId} not in the outline`);
    };
    expect((await itemOut(v1)).video_file).toMatchObject({ duration_s: 20, has_captions: true });

    // ---- access: /play for the student, 404 for an outsider; the dev stream checks only its token
    const playPath = `/courses/${cid}/modules/${m1}/items/${v1}/play`;
    const play = (await api(student, "GET", playPath)) as PlayOut;
    expect(play.url).toMatch(new RegExp(`^/api/v1/courses/${cid}/videos/${video.id}/stream\\?token=`));
    expect(play.captions_url).toBe(`/api/v1/courses/${cid}/modules/${m1}/items/${v1}/captions.vtt`);
    expect((await raw(outsider, "GET", playPath)).status, "an outsider never learns the item exists").toBe(404);
    const vtt = await raw(student, "GET", play.captions_url!);
    expect(vtt.status).toBe(200);
    expect(vtt.headers.get("content-type")).toContain("text/vtt");
    expect(await vtt.text()).toContain("WEBVTT");

    const streamBase = `${s.api}${play.url.split("?")[0]}`;
    const token = new URL(play.url, s.api).searchParams.get("token")!;
    const ranged = await raw(null, "GET", `${streamBase}?token=${encodeURIComponent(token)}`, { headers: { Range: "bytes=0-99" } });
    expect(ranged.status, "a Range request is answered in part").toBe(206);
    expect(ranged.headers.get("content-range")).toBe(`bytes 0-99/${fs.statSync(MP4).size}`);
    expect((await ranged.arrayBuffer()).byteLength).toBe(100);
    const last = token.slice(-1);
    const tampered = `${token.slice(0, -1)}${last === "A" ? "B" : "A"}`;
    const bad = await raw(null, "GET", `${streamBase}?token=${encodeURIComponent(tampered)}`, { headers: { Range: "bytes=0-99" } });
    expect(bad.status, "a tampered token is refused").toBe(403);
    expect((await bad.json()).error.code).toBe("video_token_invalid");
    const expiredToken = streamToken(video.id, Math.floor(Date.now() / 1000) - 60);
    const fresh = streamToken(video.id, Math.floor(Date.now() / 1000) + 600);
    expect((await raw(null, "GET", `${streamBase}?token=${fresh}`, { headers: { Range: "bytes=0-9" } })).status,
      "the token recipe matches the server's (control)").toBe(206);
    const expired = await raw(null, "GET", `${streamBase}?token=${expiredToken}`, { headers: { Range: "bytes=0-9" } });
    expect(expired.status, "an expired token is refused").toBe(403);
    expect((await expired.json()).error.code).toBe("video_token_invalid");

    // ---- Pro: a paid module of a platform course is 403 item_locked for a student without Pro
    const ort = await api(s.admin, "GET", `/courses/${s.course_id}`);
    const pc = await api(s.admin, "POST", "/courses", {
      title: { ru: PRO_COURSE }, languages: ["ru"], default_language: "ru", organization_id: ort.organization_id,
    });
    await api(s.admin, "POST", `/courses/${pc.id}/publish`, {});
    await api(student, "POST", "/courses/join", { code: pc.join_code });
    const free = (await api(s.admin, "POST", `/courses/${pc.id}/modules`, { title: { ru: "Бесплатно" }, published: true })).id as string;
    const fpg = await api(s.admin, "POST", `/courses/${pc.id}/pages`, { title: "Вступление", language: "ru", body_md: "Начало.", published: true });
    await api(s.admin, "POST", `/courses/${pc.id}/modules/${free}/items`, { kind: "page", page_id: fpg.id, published: true });
    const paid = (await api(s.admin, "POST", `/courses/${pc.id}/modules`, { title: { ru: "Pro" }, published: true, access_tier: "paid" })).id as string;
    const pv = (await uploadVideo(s.admin, pc.id, "Pro видео")).video;
    const pi = (await api(s.admin, "POST", `/courses/${pc.id}/modules/${paid}/items`, { kind: "video", video_id: pv.id, published: true })).id as string;
    const locked = await raw(student, "GET", `/courses/${pc.id}/modules/${paid}/items/${pi}/play`);
    expect(locked.status, "no Pro, no address").toBe(403);
    expect((await locked.json()).error.code).toBe("item_locked");
    expect((await raw(student, "GET", `/courses/${pc.id}/modules/${paid}/items/${pi}/captions.vtt`)).status).toBe(403);
    expect((await api(s.admin, "GET", `/courses/${pc.id}/modules/${paid}/items/${pi}/play`)).url, "staff play it").toBeTruthy();

    // ---- the student's lesson: <video> with the dev stream, captions track, speed menu
    await signIn(page, student);
    await page.setViewportSize(VIEWPORTS.desktop);
    const base = `/${L}/courses/${cid}`;
    const lessonUrl = `${base}/modules/${m1}/items/${v1}`;
    await page.goto(lessonUrl);
    await expect(page.getByRole("heading", { level: 1, name: V1 })).toBeVisible();
    const v = videoEl(page);
    await expect(v).toHaveCount(1);
    await expect(v).toHaveAttribute("src", new RegExp(`^http://127\\.0\\.0\\.1:\\d+/api/v1/courses/${cid}/videos/${video.id}/stream\\?token=`));
    await expect(v).toHaveAttribute("controlslist", "nodownload");
    await expect(v.locator("track[kind=subtitles]")).toHaveCount(1);
    await expect.poll(() => v.evaluate((el: HTMLVideoElement) => el.textTracks.length)).toBe(1);
    const speed = page.getByLabel(t("modules.lesson.video.speed"));
    await expect(speed).toBeVisible();
    await expect(page.getByText(t("modules.lesson.video.captionsHint"))).toBeVisible();

    const h264 = await page.evaluate(() => document.createElement("video").canPlayType('video/mp4; codecs="avc1.42E01E"'));
    test.info().annotations.push({ type: "h264", description: h264 || "not supported: playback steps skipped" });
    if (h264) {
      await expect.poll(() => v.evaluate((el: HTMLVideoElement) => el.readyState), { message: "metadata in" }).toBeGreaterThanOrEqual(1);
      expect(await v.evaluate((el: HTMLVideoElement) => Math.round(el.duration))).toBe(20);
      // ---- plays (muted)
      await v.evaluate((el: HTMLVideoElement) => { el.muted = true; return el.play(); });
      await expect.poll(() => currentTime(page), { message: "playback advances" }).toBeGreaterThan(0);
      // ---- the speed menu
      await speed.selectOption("1.5");
      await expect.poll(() => v.evaluate((el: HTMLVideoElement) => el.playbackRate)).toBe(1.5);
      // ---- pause at ~8 s: remembered, restored after a reload (not 0)
      await v.evaluate((el: HTMLVideoElement) => { el.currentTime = 8; });
      await expect.poll(() => currentTime(page)).toBeGreaterThan(8.2);
      await v.evaluate((el: HTMLVideoElement) => el.pause());
      const saved = await page.evaluate((k) => window.localStorage.getItem(k), `ort_video_pos:${v1}`);
      expect(Number(saved), "the position is remembered").toBeGreaterThanOrEqual(8);
      expect((await itemOut(v1)).done, "8 s of 20 is not watched").toBeFalsy();
      await widths(page, "student-lesson-video", v);

      await page.reload();
      await expect.poll(() => v.evaluate((el: HTMLVideoElement) => el.readyState)).toBeGreaterThanOrEqual(1);
      await expect.poll(() => currentTime(page), { message: "the position is restored" }).toBeGreaterThanOrEqual(8);
      expect(await v.evaluate((el: HTMLVideoElement) => el.playbackRate), "the rate is remembered").toBe(1.5);

      // ---- seek to 95 % while playing: the view fact, done on the lesson and in the syllabus
      await v.evaluate((el: HTMLVideoElement) => { el.muted = true; return el.play(); });
      await v.evaluate((el: HTMLVideoElement) => { el.currentTime = el.duration * 0.95; });
      await expect.poll(async () => (await itemOut(v1)).done, { message: "done after 90 %" }).toBe(true);
      await expect(page.locator("p").filter({ hasText: t("modules.lesson.done") })).toBeVisible();
    } else {
      await widths(page, "student-lesson-video", v);
      await api(student, "POST", `/courses/${cid}/modules/${m1}/items/${v1}/view`, {}); // the 90 % fact by hand
    }
    await page.goto(`${base}/lessons`);
    const sec1 = page.locator(`#module-${m1}`);
    const toggle = sec1.getByRole("button", { name: M1, exact: true });
    await expect(toggle).toBeVisible();
    if ((await toggle.getAttribute("aria-expanded")) === "false") await toggle.click();
    await expect(sec1.getByRole("link", { name: new RegExp(V1) })).toContainText(t("modules.syllabus.status.done"));
    await expect(sec1.getByRole("link", { name: new RegExp(V2) })).not.toContainText(t("modules.syllabus.status.done"));

    // ---- «Просмотрено» on the second video
    await page.goto(`${base}/modules/${m1}/items/${v2}`);
    await expect(page.getByRole("heading", { level: 1, name: V2 })).toBeVisible();
    await page.getByRole("button", { name: t("modules.lesson.video.watched") }).click();
    await expect(page.locator("p").filter({ hasText: t("modules.lesson.done") })).toBeVisible();
    expect((await itemOut(v2)).done).toBe(true);

    // ---- staff: the outline row with its duration; «Добавить» → «Видео» uploads the same file (dedup) with progress
    const ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: "ru-RU", timezoneId: "UTC", colorScheme: "light" });
    const tp = await ctx.newPage();
    await signIn(tp, teacher);
    await tp.goto(base);
    const card = tp.locator(`#m-${m1}`);
    await expect(card).toBeVisible();
    const row1 = card.getByRole("button", { name: new RegExp(`^${V1}`) });
    await expect(row1).toBeVisible();
    await expect(card.getByText(t("modules.editor.minutes", { n: 1 })).first()).toBeVisible();
    await card.getByRole("button", { name: t("coursePage.add", { title: M1 }) }).click();
    await tp.getByRole("menu").getByRole("menuitem", { name: t("modules.editor.addVideo"), exact: true }).click();
    const dlg = tp.getByRole("dialog", { name: t("modules.editor.video.title") });
    await expect(dlg).toBeVisible();
    await expect(dlg.getByRole("radio", { name: t("modules.editor.video.sourceFile") })).toBeChecked();
    await dlg.getByLabel(t("modules.editor.video.file")).setInputFiles(MP4);
    await expect(dlg.getByText("lesson-video.mp4")).toBeVisible();
    const V3 = "Видео из диалога";
    await dlg.getByLabel(t("modules.editor.video.name")).fill(V3);
    await settle(tp, false);
    await shot(tp, "staff-upload-dialog-1440-ru");
    // hold the upload response for a moment so the progress bar can be seen
    await tp.route(`**/api/v1/courses/${cid}/videos`, async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await new Promise((r) => setTimeout(r, 2500));
      await route.continue();
    });
    const upload = tp.waitForResponse((r) => r.url().endsWith(`/courses/${cid}/videos`) && r.request().method() === "POST");
    await dlg.getByRole("button", { name: t("modules.editor.video.upload") }).click();
    const bar = dlg.getByRole("progressbar", { name: t("modules.editor.video.uploadingLabel") });
    await expect(bar).toBeVisible();
    // (an intercepted request reports no upload progress to the page, so the shot shows 0 %)
    await shot(tp, "staff-upload-progress-1440-ru");
    const res = await upload;
    expect(res.status(), "the same file again: the existing video").toBe(200);
    expect((await res.json()).id).toBe(video.id);
    await expect(dlg).toHaveCount(0);
    // a third video row (dedup: the item shows the existing video's name; the name typed in the dialog is not kept)
    await expect(card.getByRole("button", { name: new RegExp(`, ${t("modules.editor.videoPreview")}$`) })).toHaveCount(3);
    const items = (await api(teacher, "GET", `/courses/${cid}/modules`)).modules.find((m: { id: string }) => m.id === m1).items as
      { kind: string; video_id?: string | null; title?: unknown }[];
    expect(items.filter((i) => i.kind === "video")).toHaveLength(3);
    const list = await api(teacher, "GET", `/courses/${cid}/videos`);
    expect(list.items.map((x: { id: string }) => x.id)).toEqual([video.id]);
    await ctx.close();

    if (SHOTS) {
      const log = execFileSync("python3", [path.resolve(__dirname, "shots_webp.py"), PNG_DIR, OUT_DIR], { encoding: "utf-8" });
      console.log(log);
    }
  });
});
