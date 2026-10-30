import fs from "node:fs";
import path from "node:path";
import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import { PNG } from "pngjs";
import ru from "../src/lib/i18n/ru.json";
import ky from "../src/lib/i18n/ky.json";
import en from "../src/lib/i18n/en.json";

// ----------------------------------------------------------------------------- seed (frontend/e2e/seed_backend.py)

export type Lang = "ru" | "ky";
export interface SeedUser {
  email: string;
  name: string;
  token: string;
  profile: Record<string, unknown> & { id: string };
}
export interface Seed {
  api: string;
  course_id: string;
  bank_id: string;
  exam: { id: string; items: number };
  staff_exam: { id: string; items: number };
  picks: Record<string, string[]>;
  /** question id -> index of the correct answer button (choices are not shuffled) */
  keys: Record<string, { type: string; correct: number; choices: number }>;
  comparison_question_id: string;
  passage_id: string;
  staff_attempt_id: string;
  admin: SeedUser;
  students: Record<string, SeedUser>;
  /** Phase 7c S5: the general course of the quiz editor walk (quiz-editor.spec.ts). */
  quiz_editor: {
    course_id: string;
    bank_id: string;
    shared_question_ids: string[];
    quiz_a: string;
    quiz_b: string;
    quiz_b_version: number;
    teacher: SeedUser;
    student: SeedUser;
  };
  /** Phase 8a S5: the general course of the modules walk (modules.spec.ts) and one extra ORT (Russian) student. */
  modules: {
    course_id: string;
    join_code: string;
    teacher: SeedUser;
    student: SeedUser;
    ort_student: SeedUser;
  };
  /** Phase 8c S4a: the general course of the navigation walk (course-nav.spec.ts), empty, three enrolled students. */
  course_nav: {
    course_id: string;
    join_code: string;
    teacher: SeedUser;
    students: Record<"sidebar" | "handin" | "phone", SeedUser>;
  };
  /** Phase 8b S3: the scrolling-player course (its published quizzes serve the Student view "Start" check). */
  scrolling: {
    course_id: string;
    long_quiz: string;
    forward_quiz: string;
    page_quiz: string;
    teacher: SeedUser;
    students: Record<string, SeedUser>;
  };
}

export const E2E_DIR = process.env.E2E_DIR || "/tmp/ort_e2e";
export const seedPath = () => path.join(E2E_DIR, "seed.json");
let cached: Seed | null = null;
export function seed(): Seed {
  if (!cached) cached = JSON.parse(fs.readFileSync(seedPath(), "utf-8")) as Seed;
  return cached;
}

/** ORT section order (AGENTS.md section 4) and the item counts the seed builds. */
export const ORT_SECTIONS = ["math_1", "math_2", "analogies", "reading", "grammar"] as const;
export const sectionCounts = () => ORT_SECTIONS.map((k) => seed().picks[k].length);

// ----------------------------------------------------------------------------- i18n (the app's own strings)

const DICTS: Record<Lang | "en", unknown> = { ru, ky, en };
/** Same lookup and `{name}` interpolation as the app (src/lib/i18n/context). */
export function tr(lang: Lang | "en", key: string, vars: Record<string, string | number> = {}): string {
  let cur: unknown = DICTS[lang];
  for (const part of key.split(".")) {
    if (cur && typeof cur === "object" && part in (cur as Record<string, unknown>)) cur = (cur as Record<string, unknown>)[part];
    else throw new Error(`e2e: missing i18n key ${lang}:${key}`);
  }
  if (typeof cur !== "string") throw new Error(`e2e: ${lang}:${key} is not a string`);
  return cur.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

// ----------------------------------------------------------------------------- session

/** Sign in without the login form: the token and cached profile the app's AuthProvider restores. */
export async function signIn(page: Page, user: SeedUser): Promise<void> {
  const p = user.profile;
  const cachedProfile = {
    uid: p.id, email: p.email, displayName: p.displayName || user.name, phone: p.phone || undefined,
    is_platform_admin: Boolean(p.is_platform_admin), teacher_status: p.teacher_status || "none", locale: p.locale || undefined,
  };
  await page.addInitScript(([token, prof]) => {
    try {
      window.localStorage.setItem("ort_token", token);
      window.localStorage.setItem("ort_dev_auth_user", prof);
    } catch { /* storage unavailable */ }
  }, [user.token, JSON.stringify(cachedProfile)] as const);
}

// ----------------------------------------------------------------------------- stable rendering

/** Network quiet, web fonts loaded, KaTeX laid out, no "loading" placeholder, pointer parked off any hover target. */
export async function settle(page: Page, network = true): Promise<void> {
  if (network) await page.waitForLoadState("networkidle");
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  });
  await page.mouse.move(0, 0);
}

// ----------------------------------------------------------------------------- screenshot baselines

/** 0.5 % of the pixels may differ (anti-aliased pixels are not counted). */
export const MAX_DIFF_RATIO = 0.005;
/** pixelmatch per-pixel colour threshold (its default). */
export const PIXEL_THRESHOLD = 0.1;
export const MASK_COLOR = "#FF00FF";
const UPDATE = process.env.UPDATE_BASELINES === "1";
/** CI: a platform without committed baselines records them (artifact) instead of failing. */
const RECORD_MISSING = process.env.ORT_BASELINE_RECORD_MISSING === "1";

/**
 * Baselines are per rendering platform (system fonts differ): macOS (the reviewed set) at the folder root,
 * other platforms in a subfolder named after `process.platform` (CI: `linux/`).
 */
export function baselineDir(): string {
  if (process.env.ORT_BASELINE_DIR) return process.env.ORT_BASELINE_DIR;
  const root = path.resolve(__dirname, "../../docs/phases/ORT_BASELINE");
  return process.platform === "darwin" ? root : path.join(root, process.platform);
}

let pixelmatchFn: null | ((a: Uint8Array, b: Uint8Array, out: Uint8Array, w: number, h: number, o: object) => number) = null;
async function pm() {
  if (!pixelmatchFn) {
    const mod = (await import("pixelmatch")) as unknown as { default: typeof pixelmatchFn };
    pixelmatchFn = mod.default;
  }
  return pixelmatchFn!;
}

export interface ShotOptions {
  /** volatile regions painted over before comparing (timer digits, dates, ids) */
  mask?: Locator[];
  /** screenshot only this element instead of the viewport */
  element?: Locator;
  fullPage?: boolean;
  /** false: do not wait for network idle (a loading state whose request is held on purpose) */
  waitNetwork?: boolean;
}

/**
 * Screenshot `<name>.png` and compare it with the committed baseline (soft assertion, so every screen of a walk is
 * checked). UPDATE_BASELINES=1 rewrites the baseline. On a mismatch the actual image and a diff land in the test
 * output and in $E2E_DIR/diffs/ (uploaded by CI).
 */
export async function expectScreen(page: Page, info: TestInfo, name: string, opts: ShotOptions = {}): Promise<void> {
  await settle(page, opts.waitNetwork !== false);
  const shotOpts = { animations: "disabled" as const, caret: "hide" as const, mask: opts.mask ?? [], maskColor: MASK_COLOR };
  const buf = opts.element ? await opts.element.screenshot(shotOpts) : await page.screenshot({ ...shotOpts, fullPage: !!opts.fullPage });
  const dir = baselineDir();
  const file = path.join(dir, `${name}.png`);
  const record = UPDATE || (RECORD_MISSING && !fs.existsSync(file));
  if (record) {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(file, buf);
    const recDir = path.join(E2E_DIR, "recorded");
    fs.mkdirSync(recDir, { recursive: true });
    fs.writeFileSync(path.join(recDir, `${name}.png`), buf);
    await info.attach(`${name} (recorded)`, { body: buf, contentType: "image/png" });
    return;
  }
  expect.soft(fs.existsSync(file), `baseline ${file} is missing (run with UPDATE_BASELINES=1)`).toBe(true);
  if (!fs.existsSync(file)) return;
  const actual = PNG.sync.read(buf);
  const expected = PNG.sync.read(fs.readFileSync(file));
  const diffDir = path.join(E2E_DIR, "diffs");
  const keep = async (diff?: PNG) => {
    fs.mkdirSync(diffDir, { recursive: true });
    fs.writeFileSync(path.join(diffDir, `${name}-actual.png`), buf);
    fs.copyFileSync(file, path.join(diffDir, `${name}-expected.png`));
    await info.attach(`${name}-actual`, { body: buf, contentType: "image/png" });
    if (diff) {
      const d = PNG.sync.write(diff);
      fs.writeFileSync(path.join(diffDir, `${name}-diff.png`), d);
      await info.attach(`${name}-diff`, { body: d, contentType: "image/png" });
    }
  };
  if (actual.width !== expected.width || actual.height !== expected.height) {
    await keep();
    expect.soft(`${actual.width}x${actual.height}`, `${name}: size differs from the baseline`).toBe(`${expected.width}x${expected.height}`);
    return;
  }
  const diff = new PNG({ width: actual.width, height: actual.height });
  const bad = (await pm())(actual.data, expected.data, diff.data, actual.width, actual.height, { threshold: PIXEL_THRESHOLD, includeAA: false });
  const ratio = bad / (actual.width * actual.height);
  if (ratio > MAX_DIFF_RATIO) await keep(diff);
  expect.soft(ratio, `${name}: ${bad} pixels (${(ratio * 100).toFixed(3)} %) differ from the baseline`).toBeLessThanOrEqual(MAX_DIFF_RATIO);
}

// ----------------------------------------------------------------------------- viewports

export const VIEWPORTS = {
  phone: { width: 375, height: 812 },
  desktop: { width: 1440, height: 900 },
} as const;
export type ViewportName = keyof typeof VIEWPORTS;
