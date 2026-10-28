// Phase 7b S7 (UX fix): the template spec as form state and back. Untouched values round-trip exactly: every
// field keeps the spec's own value while the form shows the same thing (seconds in the spec, minutes in the form).
import type { ExamTemplateSpec, LockScopeKey, SpecDefaults, SpecIssue, SpecParameter, SpecSection } from "@/lib/lms/examTemplateTypes";
import type { Navigation, ResultsPolicy, ScorePolicy } from "@/lib/lms/assessmentTypes";
import { cleanLocalized } from "@/lib/lms/localized";
import { LMS_LANGS, type LocalizedText } from "@/lib/lms/types";
import { DEFAULT_DISPLAY_MODE, DEFAULT_NAVIGATION } from "@/lib/lms/examTemplates";

const BIND_RE = /^sections\[(\d+)\]\.key$/;
let seq = 0;
const uid = () => `u${++seq}`;

// ---------------------------------------------------------------- section keys from titles (ru / ky -> Latin)
const TRANSLIT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "i", к: "k", л: "l", м: "m",
  н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch",
  ъ: "", ы: "y", ь: "", э: "e", ю: "iu", я: "ia", ң: "ng", ө: "o", ү: "u",
};

/** A section key (`^[a-z0-9_]{1,40}$`) from a title, or "" when the title has no usable letters. */
export function keyFromTitle(title: string): string {
  const latin = Array.from(title.toLowerCase()).map((ch) => TRANSLIT[ch] ?? ch).join("");
  return latin.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40).replace(/_+$/g, "");
}

/** The title a key is derived from: English first (already Latin), then Russian, then Kyrgyz. */
export function keySourceTitle(title: LocalizedText | null | undefined): string {
  if (!title) return "";
  for (const l of ["en", "ru", "ky"] as const) {
    const v = (title[l] ?? "").trim();
    if (v) return v;
  }
  return "";
}

// ---------------------------------------------------------------- numbers
const numText = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n));
/** Minutes shown for seconds (fractions kept, so 90 s shows 1.5). */
export const minText = (s: number | null | undefined) => (s === null || s === undefined ? "" : String(Math.round((s / 60) * 100) / 100));

/** A typed whole number, or null when empty; `NaN` when not a whole number (the server then reports it). */
function parseInt0(v: string): number | null {
  const s = v.trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isInteger(n) ? n : NaN;
}
/** Minutes typed -> seconds (null when empty). */
function minutesToSeconds(v: string): number | null {
  const s = v.trim().replace(",", ".");
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? Math.round(n * 60) : NaN;
}

const sameText = (a: LocalizedText | null | undefined, b: LocalizedText | null | undefined) =>
  JSON.stringify(cleanLocalized(a ?? {}, LMS_LANGS)) === JSON.stringify(cleanLocalized(b ?? {}, LMS_LANGS));

/** Localized text for the spec: the spec's own value when unchanged, null when empty. */
function textOut(v: LocalizedText, base: LocalizedText | null | undefined): LocalizedText | null {
  if (base !== undefined && sameText(v, base)) return base;
  const c = cleanLocalized(v, LMS_LANGS);
  return Object.keys(c).length ? c : null;
}

/** NaN cannot travel as JSON: send it as the typed text so the server reports a type error under the field. */
const jsonNum = (n: number | null, raw: string): number | string | null => (Number.isNaN(n) ? raw : n);

/** Parameter options typed one per line (commas also separate, as in 7b). */
export const splitOptions = (v: string) => v.split(/[\n,]/).map((o) => o.trim()).filter(Boolean);

// ---------------------------------------------------------------- form types
export interface SectionDraft {
  uid: string;
  base: SpecSection | null;
  key: string;
  /** Key follows the title (new sections, or a stored key equal to the derived one). */
  keyAuto: boolean;
  title: LocalizedText;
  instructions: LocalizedText;
  timeMin: string;
  minItems: string;
  maxItems: string;
  types: string[];
  allowPassages: boolean;
  passageDisplay: string;
}

export interface ParameterDraft {
  uid: string;
  base: SpecParameter | null;
  key: string;
  options: string;
  /** uid of the section whose key this parameter supplies ("" = none chosen). */
  section: string;
}

export interface DefaultsDraft {
  base: SpecDefaults;
  timeMin: string;
  attempts: string;
  unlimited: boolean;
  scorePolicy: ScorePolicy;
  resultsPolicy: ResultsPolicy;
  showCorrect: boolean;
  shuffleItems: boolean;
  shuffleChoices: boolean;
}

export interface SpecDraft {
  base: ExamTemplateSpec;
  navigation: Navigation;
  displayMode: string;
  passageDisplay: string;
  resultView: string;
  schemeId: string;
  defaults: DefaultsDraft;
  sections: SectionDraft[];
  parameters: ParameterDraft[];
  lockScope: LockScopeKey[];
}

export function newSection(types: string[]): SectionDraft {
  return {
    uid: uid(), base: null, key: "", keyAuto: true, title: {}, instructions: {}, timeMin: "", minItems: "", maxItems: "",
    types: [...types], allowPassages: false, passageDisplay: "",
  };
}

export function newParameter(): ParameterDraft {
  return { uid: uid(), base: null, key: "", options: "", section: "" };
}

function sectionDraft(s: SpecSection): SectionDraft {
  const derived = keyFromTitle(keySourceTitle(s.title));
  return {
    // auto: the stored key is the derived one, or there is neither a key nor a title yet (both stay null)
    uid: uid(), base: s, key: s.key ?? "", keyAuto: s.key ? s.key === derived : !derived,
    title: { ...(s.title ?? {}) }, instructions: { ...(s.instructions ?? {}) },
    timeMin: minText(s.time_limit_s), minItems: numText(s.min_items), maxItems: numText(s.max_items),
    types: [...(s.allowed_types ?? [])], allowPassages: !!s.allow_passages, passageDisplay: s.passage_display ?? "",
  };
}

export function draftOf(spec: ExamTemplateSpec): SpecDraft {
  const d = spec.defaults ?? {};
  const sections = (spec.sections ?? []).map(sectionDraft);
  const parameters = (spec.parameters ?? []).map((p): ParameterDraft => {
    const m = BIND_RE.exec(p.binds ?? "");
    const target = m ? sections[Number(m[1])] : undefined;
    return { uid: uid(), base: p, key: p.key, options: (p.options ?? []).join("\n"), section: target?.uid ?? "" };
  });
  return {
    base: spec,
    navigation: spec.navigation ?? DEFAULT_NAVIGATION,
    displayMode: spec.display_mode ?? DEFAULT_DISPLAY_MODE,
    passageDisplay: spec.passage_display ?? "",
    resultView: spec.result_view ?? "",
    schemeId: spec.scoring?.grading_scheme_version_id ?? "",
    defaults: {
      base: d,
      timeMin: minText(d.time_limit_s),
      attempts: d.allowed_attempts === undefined || d.allowed_attempts === -1 ? "1" : String(d.allowed_attempts),
      unlimited: d.allowed_attempts === -1,
      scorePolicy: d.score_policy ?? "highest",
      resultsPolicy: d.results_policy ?? "after_submit",
      showCorrect: !!d.show_correct_answers,
      shuffleItems: !!d.shuffle_items,
      shuffleChoices: !!d.shuffle_choices,
    },
    sections,
    parameters,
    lockScope: [...(spec.lock_scope ?? [])],
  };
}

/** Uids of the sections a parameter supplies the key for. */
export function boundSections(d: SpecDraft): Map<string, ParameterDraft> {
  const out = new Map<string, ParameterDraft>();
  for (const p of d.parameters) if (p.section) out.set(p.section, p);
  return out;
}

/** The key a section sends: "" / bound -> null; auto keys follow the title. */
export function sectionKey(s: SectionDraft, bound: boolean): string | null {
  if (bound) return null;
  const k = s.keyAuto ? keyFromTitle(keySourceTitle(s.title)) : s.key.trim();
  return k || null;
}

function sectionOut(s: SectionDraft, bound: boolean): SpecSection {
  const b = s.base;
  const key = sectionKey(s, bound);
  const time = minutesToSeconds(s.timeMin);
  const min = parseInt0(s.minItems);
  const max = parseInt0(s.maxItems);
  const keep = <T,>(v: T, baseV: T | undefined, same: boolean): T => (b && same ? (baseV as T) : v);
  return {
    key: keep(key, b?.key, (b?.key ?? null) === key),
    title: textOut(s.title, b ? b.title : undefined),
    instructions: textOut(s.instructions, b ? b.instructions : undefined),
    time_limit_s: keep(jsonNum(time, s.timeMin) as number | null, b?.time_limit_s, minText(b?.time_limit_s) === s.timeMin.trim()),
    min_items: keep(jsonNum(min, s.minItems) as number | null, b?.min_items, numText(b?.min_items) === s.minItems.trim()),
    max_items: keep(jsonNum(max, s.maxItems) as number | null, b?.max_items, numText(b?.max_items) === s.maxItems.trim()),
    allowed_types: [...s.types],
    allow_passages: s.allowPassages,
    passage_display: (s.passageDisplay || null) as SpecSection["passage_display"],
  };
}

function defaultsOut(d: DefaultsDraft): SpecDefaults {
  const b = d.base;
  const time = minutesToSeconds(d.timeMin);
  const attempts = d.unlimited ? -1 : parseInt0(d.attempts);
  return {
    ...b,
    time_limit_s: "time_limit_s" in b && minText(b.time_limit_s) === d.timeMin.trim() ? b.time_limit_s : (jsonNum(time, d.timeMin) as number | null),
    allowed_attempts: (attempts === null ? ((b.allowed_attempts ?? 0) > 0 ? b.allowed_attempts : 1) : jsonNum(attempts, d.attempts)) as number,
    score_policy: d.scorePolicy,
    results_policy: d.resultsPolicy,
    show_correct_answers: d.showCorrect,
    shuffle_items: d.shuffleItems,
    shuffle_choices: d.shuffleChoices,
  };
}

/** The spec the form describes (unknown spec keys of the base, e.g. `schema`, `importer_profile`, are kept). */
export function specOf(d: SpecDraft): ExamTemplateSpec {
  const bound = boundSections(d);
  const index = new Map(d.sections.map((s, i) => [s.uid, i]));
  const baseScheme = d.base.scoring?.grading_scheme_version_id ?? "";
  return {
    ...d.base,
    navigation: d.navigation,
    display_mode: d.displayMode as ExamTemplateSpec["display_mode"],
    passage_display: (d.passageDisplay || null) as ExamTemplateSpec["passage_display"],
    result_view: (d.resultView || null) as ExamTemplateSpec["result_view"],
    scoring: d.schemeId === baseScheme && d.base.scoring !== undefined ? d.base.scoring
      : d.schemeId ? { grading_scheme_version_id: d.schemeId } : null,
    defaults: defaultsOut(d.defaults),
    sections: d.sections.map((s) => sectionOut(s, bound.has(s.uid))),
    parameters: d.parameters.map((p): SpecParameter => {
      const options = splitOptions(p.options);
      const i = index.get(p.section);
      const binds = i === undefined ? "" : `sections[${i}].key`;
      const sameOptions = p.base && JSON.stringify(p.base.options) === JSON.stringify(options);
      return { ...(p.base ?? {}), key: p.key.trim(), kind: "choice", options: sameOptions ? p.base!.options : options, binds };
    }),
    lock_scope: [...d.lockScope],
  };
}

// --- Phase 8b S4 begin --- (PHASE_8B_DESIGN 9.2: client pre-check; autosave runs only when it finds nothing)
const KEY_RE = /^[a-z0-9_]{1,40}$/;

/**
 * Problems that keep the draft from being sent (it stays local, mirrored to sessionStorage). Same `SpecIssue` shape
 * and machine types as the server's `spec_invalid` details, so the same translated text shows under the same field.
 * Everything else (ranges, cross checks, schemes) is left to the server validator.
 */
export function precheckDraft(d: SpecDraft): SpecIssue[] {
  const out: SpecIssue[] = [];
  const push = (loc: (string | number)[], type: string) => out.push({ loc, msg: "", type });
  const decimal = (raw: string, loc: (string | number)[]) => {
    const s = raw.trim().replace(",", ".");
    if (s && !Number.isFinite(Number(s))) push(loc, "type");
  };
  const whole = (raw: string, loc: (string | number)[]) => {
    const s = raw.trim();
    if (s && !Number.isInteger(Number(s))) push(loc, "int_type");
  };
  const bound = boundSections(d);
  if (d.sections.length === 0) push(["sections"], "sections_required");
  d.sections.forEach((s, i) => {
    if (s.types.length === 0) push(["sections", i, "allowed_types"], "types_required");
    const key = sectionKey(s, bound.has(s.uid));
    if (key && !KEY_RE.test(key)) push(["sections", i, "key"], "string_pattern_mismatch");
    decimal(s.timeMin, ["sections", i, "time_limit_s"]);
    whole(s.minItems, ["sections", i, "min_items"]);
    whole(s.maxItems, ["sections", i, "max_items"]);
  });
  d.parameters.forEach((p, j) => {
    const key = p.key.trim();
    if (!key) push(["parameters", j, "key"], "missing");
    else if (!KEY_RE.test(key)) push(["parameters", j, "key"], "string_pattern_mismatch");
    const options = splitOptions(p.options);
    if (options.length === 0) push(["parameters", j, "options"], "missing");
    else if (options.some((o) => !KEY_RE.test(o))) push(["parameters", j, "options"], "string_pattern_mismatch");
    if (!p.section) push(["parameters", j, "binds"], "binds_missing_section");
  });
  decimal(d.defaults.timeMin, ["defaults", "time_limit_s"]);
  if (!d.defaults.unlimited) whole(d.defaults.attempts, ["defaults", "allowed_attempts"]);
  return out;
}
// --- Phase 8b S4 end ---
