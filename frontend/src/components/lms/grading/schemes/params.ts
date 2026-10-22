/**
 * Pure helpers for the scheme editor: defaults, client-side param checks (mirror of the server rules in
 * PHASE_4_DESIGN.md 3.1 / P4-22; the server stays authoritative), lookup-table CSV, preview raws.
 * No React, no DOM: checked by params.check.ts.
 */
import type {
  Band, BandsParams, CommonParams, CurveParams, CurveSegment, LookupRow, LookupTableParams, Num, PassFailParams,
  PercentParams, PointsParams, SchemeParams, SchemeSummaryOut, SchemeType, ThresholdParams,
} from "../../../../lib/lms/gradingTypes";
import type { Lang, LocalizedText } from "../../../../lib/lms/types";

/** P4-22 caps. */
export const CAPS = {
  bands: 50,
  segments: 20,
  rows: 1000,
  thresholds: 10,
  labelChars: 60,
  keyChars: 32,
  previewRaws: 1001,
} as const;

const LANGS: Lang[] = ["en", "ru", "ky"];

// ---------------------------------------------------------------------------
// numbers
// ---------------------------------------------------------------------------

/** Wire number -> JS number (null for null/empty/NaN). */
export function toNum(v: Num | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Parse a user-typed number; accepts a comma as the decimal separator. Empty or invalid -> null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(",", ".");
  if (!t || t === "-" || t === ".") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** Display a grade value: up to `decimals` decimals, trailing zeros dropped. */
export function fmtNum(v: Num | null | undefined, decimals = 2): string {
  const n = toNum(v);
  if (n === null) return "";
  const f = 10 ** decimals;
  return String(Math.round(n * f) / f);
}

/** Percentile: always one decimal (design section 6). */
export function fmtPercentile(v: Num | null | undefined): string {
  const n = toNum(v);
  return n === null ? "" : n.toFixed(1);
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const r4 = (x: number) => Math.round(x * 10000) / 10000;

// ---------------------------------------------------------------------------
// defaults
// ---------------------------------------------------------------------------

const allLangs = (s: string): LocalizedText => ({ en: s, ru: s, ky: s });

export function defaultParams(type: SchemeType): SchemeParams {
  switch (type) {
    case "points":
      return { schema: 1 } satisfies PointsParams;
    case "percent":
      return { schema: 1, rounding: { mode: "half_up", decimals: 1 } } satisfies PercentParams;
    case "bands":
      return {
        schema: 1,
        bands: [
          { key: "5", min_percent: 85, label: allLangs("5"), passed: true },
          { key: "4", min_percent: 70, label: allLangs("4"), passed: true },
          { key: "3", min_percent: 50, label: allLangs("3"), passed: true },
          { key: "2", min_percent: 0, label: allLangs("2"), passed: false },
        ],
      } satisfies BandsParams;
    case "pass_fail":
      return { schema: 1, pass_threshold_percent: 60 } satisfies PassFailParams;
    case "piecewise_curve":
      return {
        schema: 1,
        scale_min: 0,
        scale_max: 100,
        segments: [{ from_ratio: 0, to_ratio: 1, from_value: 0, to_value: 100, exponent: 1 }],
        rounding: { mode: "half_up", decimals: 0 },
      } satisfies CurveParams;
    case "lookup_table":
      return { schema: 1, rows: [{ raw_from: 0, raw_to: 0, value: 0 }] } satisfies LookupTableParams;
  }
}

/** A fresh band appended by the editor. */
export function nextBand(): Band {
  return { key: "", min_percent: 0, label: {}, passed: false };
}

/** Value of one curve segment at `ratio` (same expression order as the server). */
export function segmentValue(s: CurveSegment, ratio: number): number {
  const sub = (ratio - s.from_ratio) / (s.to_ratio - s.from_ratio);
  return s.from_value + (s.to_value - s.from_value) * sub ** s.exponent;
}

/**
 * Add a segment by splitting the last one at its midpoint; the curve is unchanged for exponent 1
 * and the chain stays contiguous from 0 to 1.
 */
export function splitLastSegment(segs: CurveSegment[], scaleMin: number | null, scaleMax: number | null): CurveSegment[] {
  const last = segs[segs.length - 1];
  if (!last) return [{ from_ratio: 0, to_ratio: 1, from_value: scaleMin ?? 0, to_value: scaleMax ?? 100, exponent: 1 }];
  if (![last.from_ratio, last.to_ratio, last.from_value, last.to_value, last.exponent].every(isNum) || !(last.to_ratio > last.from_ratio))
    return segs;
  const mid = r4((last.from_ratio + last.to_ratio) / 2);
  const midValue = r4(segmentValue(last, mid));
  return [
    ...segs.slice(0, -1),
    { ...last, to_ratio: mid, to_value: midValue },
    { from_ratio: mid, to_ratio: last.to_ratio, from_value: midValue, to_value: last.to_value, exponent: last.exponent },
  ];
}

export function nextRow(rows: LookupRow[]): LookupRow {
  const last = rows[rows.length - 1];
  const from = last && isNum(last.raw_to) ? last.raw_to + 1 : 0;
  return { raw_from: from, raw_to: from, value: last && isNum(last.value) ? last.value : 0 };
}

// ---------------------------------------------------------------------------
// clean (what is sent to the API)
// ---------------------------------------------------------------------------

function cleanLabel(v: LocalizedText | undefined): LocalizedText {
  const out: LocalizedText = {};
  for (const l of LANGS) {
    const s = (v?.[l] ?? "").trim();
    if (s) out[l] = s;
  }
  return out;
}

function cleanCommon(p: CommonParams): CommonParams {
  const out: CommonParams = { schema: 1 };
  if (p.rounding) out.rounding = { mode: p.rounding.mode, decimals: p.rounding.decimals };
  if (p.percentile) {
    const q = p.percentile;
    out.percentile = { mean: q.mean, sd: q.sd, min: q.min, max: q.max, decimals: q.decimals };
  }
  const th = (p.thresholds ?? []).map((x) => ({ key: x.key.trim(), min_value: x.min_value }));
  if (th.length) out.thresholds = th;
  if (p.zero_raw) out.zero_raw = { value: p.zero_raw.value, percentile: p.zero_raw.percentile };
  if (p.apply_to_sections) out.apply_to_sections = true;
  return out;
}

const optNum = (v: number | null | undefined) => (isNum(v) ? v : undefined);

/** Keep only the fields of `type` (switching type in the editor leaves stale fields behind). */
export function cleanParams(type: SchemeType, params: SchemeParams): SchemeParams {
  const common = cleanCommon(params);
  const any = params as unknown as Record<string, unknown>;
  switch (type) {
    case "points":
    case "percent": {
      const pt = optNum(any.pass_threshold_percent as number | null);
      return pt === undefined ? common : { ...common, pass_threshold_percent: pt };
    }
    case "pass_fail":
      return { ...common, pass_threshold_percent: any.pass_threshold_percent as number } as PassFailParams;
    case "bands":
      return {
        ...common,
        bands: ((any.bands as Band[]) ?? []).map((b) => ({
          key: b.key.trim(), min_percent: b.min_percent, label: cleanLabel(b.label), passed: !!b.passed,
        })),
      } as BandsParams;
    case "piecewise_curve":
      return {
        ...common,
        scale_min: any.scale_min as number,
        scale_max: any.scale_max as number,
        segments: ((any.segments as CurveSegment[]) ?? []).map((s) => ({
          from_ratio: s.from_ratio, to_ratio: s.to_ratio, from_value: s.from_value, to_value: s.to_value, exponent: s.exponent,
        })),
      } as CurveParams;
    case "lookup_table": {
      const out: LookupTableParams = {
        ...common,
        rows: ((any.rows as LookupRow[]) ?? []).map((r) => {
          const label = (r.label ?? "").trim();
          return label ? { raw_from: r.raw_from, raw_to: r.raw_to, value: r.value, label } : { raw_from: r.raw_from, raw_to: r.raw_to, value: r.value };
        }),
      };
      const ep = optNum(any.expected_possible as number | null);
      if (ep !== undefined) out.expected_possible = ep;
      const smin = optNum(any.scale_min as number | null);
      const smax = optNum(any.scale_max as number | null);
      if (smin !== undefined) out.scale_min = smin;
      if (smax !== undefined) out.scale_max = smax;
      return out;
    }
  }
}

const NUMERIC_KEYS = new Set([
  "scale_min", "scale_max", "from_ratio", "to_ratio", "from_value", "to_value", "exponent", "raw_from", "raw_to", "value",
  "min_percent", "pass_threshold_percent", "expected_possible", "mean", "sd", "min", "max", "decimals", "percentile",
  "min_value",
]);

/**
 * Deep copy of params from the server with Decimal strings ("0.5") turned into numbers for the known numeric
 * fields, so the editor works on plain numbers whatever the serializer emits.
 */
export function normalizeParams<T>(v: T): T {
  const walk = (x: unknown, key: string | null): unknown => {
    if (Array.isArray(x)) return x.map((y) => walk(y, null));
    if (x && typeof x === "object") {
      const out: Record<string, unknown> = {};
      for (const [k, y] of Object.entries(x as Record<string, unknown>)) out[k] = walk(y, k);
      return out;
    }
    if (typeof x === "string" && key !== null && NUMERIC_KEYS.has(key)) {
      const n = Number(x);
      return x.trim() !== "" && Number.isFinite(n) ? n : x;
    }
    return x;
  };
  return walk(v, null) as T;
}

/** Order-independent JSON for "did the params change" checks. */
export function stableStringify(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stableStringify).join(",")}]`;
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    return `{${Object.keys(o).filter((k) => o[k] !== undefined).sort().map((k) => `${JSON.stringify(k)}:${stableStringify(o[k])}`).join(",")}}`;
  }
  return JSON.stringify(v);
}

// ---------------------------------------------------------------------------
// validation
// ---------------------------------------------------------------------------

export type IssueBlock =
  | "pass" | "bands" | "segments" | "scale" | "rows" | "expected_possible" | "rounding" | "percentile" | "thresholds" | "zero_raw";

export type IssueCode =
  | "required" | "percentRange" | "decimalsRange" | "sdPositive" | "minMax" | "scaleOrder" | "tooMany" | "empty"
  | "keyRequired" | "keyTooLong" | "keyDuplicate" | "labelRequired" | "labelTooLong" | "bandsOrder" | "bandsLastZero"
  | "segmentsStart" | "segmentsEnd" | "segmentsGap" | "segmentRange" | "exponentPositive" | "rowsStart" | "rowRange"
  | "rowsOverlap" | "rowsGap" | "rowsCoverage" | "negative";

export interface ParamIssue {
  block: IssueBlock;
  /** 1-based row of a list block */
  row?: number;
  code: IssueCode;
  /** for `tooMany` */
  max?: number;
}

const pct = (v: unknown) => isNum(v) && v >= 0 && v <= 100;
const EPS = 1e-9;

function checkCommon(p: CommonParams, out: ParamIssue[]) {
  if (p.rounding) {
    const d = p.rounding.decimals;
    if (!isNum(d) || !Number.isInteger(d) || d < 0 || d > 2) out.push({ block: "rounding", code: "decimalsRange" });
  }
  if (p.percentile) {
    const q = p.percentile;
    if (!isNum(q.mean)) out.push({ block: "percentile", code: "required" });
    if (!isNum(q.sd)) out.push({ block: "percentile", code: "required" });
    else if (q.sd <= 0) out.push({ block: "percentile", code: "sdPositive" });
    if (!pct(q.min) || !pct(q.max)) out.push({ block: "percentile", code: "percentRange" });
    else if (q.min > q.max) out.push({ block: "percentile", code: "minMax" });
    if (!isNum(q.decimals) || !Number.isInteger(q.decimals) || q.decimals < 0 || q.decimals > 2)
      out.push({ block: "percentile", code: "decimalsRange" });
  }
  const th: ThresholdParams[] = p.thresholds ?? [];
  if (th.length > CAPS.thresholds) out.push({ block: "thresholds", code: "tooMany", max: CAPS.thresholds });
  const seen = new Set<string>();
  th.forEach((x, i) => {
    const k = (x.key ?? "").trim();
    if (!k) out.push({ block: "thresholds", row: i + 1, code: "keyRequired" });
    else if (k.length > CAPS.keyChars) out.push({ block: "thresholds", row: i + 1, code: "keyTooLong" });
    else if (seen.has(k)) out.push({ block: "thresholds", row: i + 1, code: "keyDuplicate" });
    seen.add(k);
    if (!isNum(x.min_value)) out.push({ block: "thresholds", row: i + 1, code: "required" });
  });
  if (p.zero_raw) {
    if (!isNum(p.zero_raw.value) || !isNum(p.zero_raw.percentile)) out.push({ block: "zero_raw", code: "required" });
    else if (!pct(p.zero_raw.percentile)) out.push({ block: "zero_raw", code: "percentRange" });
  }
}

function checkBands(bands: Band[], out: ParamIssue[]) {
  if (!bands.length) { out.push({ block: "bands", code: "empty" }); return; }
  if (bands.length > CAPS.bands) out.push({ block: "bands", code: "tooMany", max: CAPS.bands });
  const keys = new Set<string>();
  bands.forEach((b, i) => {
    const row = i + 1;
    const k = (b.key ?? "").trim();
    if (!k) out.push({ block: "bands", row, code: "keyRequired" });
    else if (k.length > CAPS.keyChars) out.push({ block: "bands", row, code: "keyTooLong" });
    else if (keys.has(k)) out.push({ block: "bands", row, code: "keyDuplicate" });
    keys.add(k);
    const labels = LANGS.map((l) => (b.label?.[l] ?? "").trim());
    if (labels.every((s) => !s)) out.push({ block: "bands", row, code: "labelRequired" });
    if (labels.some((s) => s.length > CAPS.labelChars)) out.push({ block: "bands", row, code: "labelTooLong" });
    if (!isNum(b.min_percent)) out.push({ block: "bands", row, code: "required" });
    else if (!pct(b.min_percent)) out.push({ block: "bands", row, code: "percentRange" });
    else if (i > 0 && isNum(bands[i - 1].min_percent) && !(b.min_percent < bands[i - 1].min_percent))
      out.push({ block: "bands", row, code: "bandsOrder" });
  });
  const last = bands[bands.length - 1];
  if (isNum(last.min_percent) && last.min_percent !== 0) out.push({ block: "bands", row: bands.length, code: "bandsLastZero" });
}

function checkSegments(p: CurveParams, out: ParamIssue[]) {
  if (!isNum(p.scale_min) || !isNum(p.scale_max)) out.push({ block: "scale", code: "required" });
  else if (!(p.scale_min < p.scale_max)) out.push({ block: "scale", code: "scaleOrder" });
  const segs = p.segments ?? [];
  if (!segs.length) { out.push({ block: "segments", code: "empty" }); return; }
  if (segs.length > CAPS.segments) out.push({ block: "segments", code: "tooMany", max: CAPS.segments });
  segs.forEach((s, i) => {
    const row = i + 1;
    if (![s.from_ratio, s.to_ratio, s.from_value, s.to_value, s.exponent].every(isNum)) {
      out.push({ block: "segments", row, code: "required" });
      return;
    }
    if (!(s.from_ratio >= 0 && s.from_ratio < s.to_ratio && s.to_ratio <= 1)) out.push({ block: "segments", row, code: "segmentRange" });
    if (!(s.exponent > 0)) out.push({ block: "segments", row, code: "exponentPositive" });
    if (i === 0 && Math.abs(s.from_ratio) > EPS) out.push({ block: "segments", row, code: "segmentsStart" });
    if (i > 0 && isNum(segs[i - 1].to_ratio) && Math.abs(s.from_ratio - segs[i - 1].to_ratio) > EPS)
      out.push({ block: "segments", row, code: "segmentsGap" });
  });
  const last = segs[segs.length - 1];
  if (isNum(last.to_ratio) && Math.abs(last.to_ratio - 1) > EPS) out.push({ block: "segments", row: segs.length, code: "segmentsEnd" });
}

function checkRows(p: LookupTableParams, out: ParamIssue[]) {
  const rows = p.rows ?? [];
  if (p.expected_possible !== null && p.expected_possible !== undefined) {
    if (!isNum(p.expected_possible)) out.push({ block: "expected_possible", code: "required" });
    else if (p.expected_possible < 0) out.push({ block: "expected_possible", code: "negative" });
  }
  if (isNum(p.scale_min) && isNum(p.scale_max) && !(p.scale_min < p.scale_max)) out.push({ block: "scale", code: "scaleOrder" });
  if (!rows.length) { out.push({ block: "rows", code: "empty" }); return; }
  if (rows.length > CAPS.rows) out.push({ block: "rows", code: "tooMany", max: CAPS.rows });
  rows.forEach((r, i) => {
    const row = i + 1;
    if (![r.raw_from, r.raw_to, r.value].every(isNum)) { out.push({ block: "rows", row, code: "required" }); return; }
    if (r.raw_from < 0) out.push({ block: "rows", row, code: "negative" });
    if (r.raw_from > r.raw_to) out.push({ block: "rows", row, code: "rowRange" });
    if ((r.label ?? "").trim().length > CAPS.labelChars) out.push({ block: "rows", row, code: "labelTooLong" });
    if (i === 0 && r.raw_from !== 0) out.push({ block: "rows", row, code: "rowsStart" });
    const prev = rows[i - 1];
    if (prev && isNum(prev.raw_to)) {
      if (r.raw_from <= prev.raw_to) out.push({ block: "rows", row, code: "rowsOverlap" });
      else if (r.raw_from > prev.raw_to + 1) out.push({ block: "rows", row, code: "rowsGap" });
    }
  });
  const last = rows[rows.length - 1];
  if (isNum(p.expected_possible) && isNum(last.raw_to) && last.raw_to < p.expected_possible)
    out.push({ block: "rows", row: rows.length, code: "rowsCoverage" });
}

/** Client-side check of a params object before preview/save. Empty list = looks valid. */
export function validateParams(type: SchemeType, params: SchemeParams): ParamIssue[] {
  const out: ParamIssue[] = [];
  const any = params as unknown as Record<string, unknown>;
  switch (type) {
    case "points":
    case "percent": {
      const v = any.pass_threshold_percent;
      if (v !== null && v !== undefined && !pct(v)) out.push({ block: "pass", code: "percentRange" });
      break;
    }
    case "pass_fail": {
      const v = any.pass_threshold_percent;
      if (!isNum(v)) out.push({ block: "pass", code: "required" });
      else if (!pct(v)) out.push({ block: "pass", code: "percentRange" });
      break;
    }
    case "bands":
      checkBands((any.bands as Band[]) ?? [], out);
      break;
    case "piecewise_curve":
      checkSegments(params as CurveParams, out);
      break;
    case "lookup_table":
      checkRows(params as LookupTableParams, out);
      break;
  }
  checkCommon(params, out);
  return out;
}

// ---------------------------------------------------------------------------
// lookup table CSV: raw_from,raw_to,value[,label]
// ---------------------------------------------------------------------------

export interface CsvResult {
  rows: LookupRow[];
  /** 1-based line numbers that could not be read */
  badLines: number[];
}

/** Accepts `,`, `;` or tab separators; skips blank lines and a header line that is not numeric. */
export function parseLookupCsv(text: string): CsvResult {
  const rows: LookupRow[] = [];
  const badLines: number[] = [];
  const lines = text.split(/\r?\n/);
  lines.forEach((line, i) => {
    const s = line.trim();
    if (!s) return;
    const sep = s.includes("\t") ? "\t" : s.includes(";") ? ";" : ",";
    const parts = s.split(sep).map((x) => x.trim());
    const a = parseNum(parts[0] ?? "");
    const b = parseNum(parts[1] ?? "");
    const v = parseNum(parts[2] ?? "");
    if (a === null || b === null || v === null) {
      if (i === 0 && rows.length === 0 && /[a-zа-яё]/i.test(parts[0] ?? "")) return; // header
      badLines.push(i + 1);
      return;
    }
    const label = parts.slice(3).join(sep).trim();
    rows.push(label ? { raw_from: a, raw_to: b, value: v, label } : { raw_from: a, raw_to: b, value: v });
  });
  return { rows, badLines };
}

export function lookupToCsv(rows: LookupRow[]): string {
  return rows.map((r) => [r.raw_from, r.raw_to, r.value, r.label ?? ""].join(",").replace(/,$/, "")).join("\n");
}

// ---------------------------------------------------------------------------
// preview raws
// ---------------------------------------------------------------------------

const r2 = (x: number) => Math.round(x * 100) / 100;

/**
 * Raw scores for the preview table: 0, step, 2*step, ... and always `possible` itself.
 * `step` null/<=0 means every whole point (0..N); either way the list is capped at 1,001 values
 * by widening the step.
 */
export function previewRaws(possible: number | null, step: number | null = null): number[] {
  if (possible === null || !Number.isFinite(possible) || possible <= 0) return [];
  let s = step !== null && Number.isFinite(step) && step > 0 ? step : 1;
  const maxSteps = CAPS.previewRaws - 1;
  if (possible / s > maxSteps) s = Math.ceil((possible / maxSteps) * 100) / 100;
  const out: number[] = [];
  for (let i = 0; out.length < maxSteps; i++) {
    const x = r2(i * s);
    if (x >= possible - 1e-9) break;
    out.push(x);
  }
  out.push(r2(possible));
  return out;
}

// ---------------------------------------------------------------------------
// library helpers
// ---------------------------------------------------------------------------

/** System schemes first (server order kept inside each group). */
export function sortSchemes(items: SchemeSummaryOut[]): SchemeSummaryOut[] {
  return [...items.filter((s) => s.is_system), ...items.filter((s) => !s.is_system)];
}

/** Label key of a preview/grade row -> text to show. Bands use the version's localized labels. */
export function bandLabels(params: SchemeParams): Record<string, LocalizedText> {
  const bands = (params as BandsParams).bands;
  const out: Record<string, LocalizedText> = {};
  if (Array.isArray(bands)) for (const b of bands) if (b.key) out[b.key.trim()] = b.label;
  return out;
}
