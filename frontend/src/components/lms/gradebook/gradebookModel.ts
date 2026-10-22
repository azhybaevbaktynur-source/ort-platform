/**
 * Pure helpers for the staff gradebook (PHASE_4_DESIGN.md sections 3.7, 5, 6): cell state derivation,
 * value formatting, page merging, event diffs and the regrade loop. No React, no DOM: checked by
 * gradebookModel.check.ts. Relative imports only so the check compiles without the `@/` path alias.
 */
import type {
  CellOut, GbAssessmentOut, GbRowOut, GradeEventOut, Num, RegradeOut, SchemeLabelValue, SubmissionAttemptOut,
  SubmissionStaffOut,
} from "../../../lib/lms/gradingTypes";
import { fmtNum, fmtPercentile, toNum } from "../grading/schemes/params";

// ---------------------------------------------------------------------------
// cell state
// ---------------------------------------------------------------------------

/**
 * Primary state of a gradebook cell:
 * `none` = no submission and nothing due yet, `missing` = no submission after the due date,
 * `needs_review` = kept attempt has items to grade by hand, `excused`, `graded`,
 * `no_attempts` = a submission exists but every attempt was voided (no numbers to show).
 */
export type CellKind = "none" | "missing" | "needs_review" | "excused" | "graded" | "no_attempts";

export interface CellView {
  kind: CellKind;
  /** a late deduction was applied */
  late: boolean;
  /** a teacher override is in effect */
  overridden: boolean;
  /** the grade is visible to the student (released_at set) */
  released: boolean;
  /** graded or overridden but not released yet */
  unreleased: boolean;
  /** scheme display value ("187", "92.5"), empty when the scheme has none */
  value: string;
  /** scheme label key (`pass`, `fail`, band key, lookup label) or null */
  label: string | null;
  /** "18 / 30" (effective points over possible), empty when unknown */
  points: string;
  percentile: string;
  /** threshold keys that were reached (e.g. `golden_certificate`) */
  thresholds: string[];
  /** the column scheme's label map (resolves `label` to localized text), null when unknown */
  labels: Record<string, SchemeLabelValue> | null;
}

/** What `cellView` needs from a column: its due date and, optionally, its scheme's label map. */
export type CellColumn = Pick<GbAssessmentOut, "due_at"> & { scheme?: { labels?: Record<string, SchemeLabelValue> | null } | null };

/** Due date in the past (unparseable dates count as not due). */
export function isPastDue(dueAt: string | null | undefined, now: number): boolean {
  if (!dueAt) return false;
  const t = Date.parse(dueAt);
  return Number.isFinite(t) && t < now;
}

/** "a / b" with trailing zeros dropped; empty when `a` is unknown. */
export function fmtPointsOf(a: Num | null | undefined, b: Num | null | undefined): string {
  const x = fmtNum(a);
  if (!x) return "";
  const y = fmtNum(b);
  return y ? `${x} / ${y}` : x;
}

export function reachedThresholds(t: Record<string, boolean> | null | undefined): string[] {
  if (!t) return [];
  return Object.keys(t).filter((k) => t[k] === true).sort();
}

export function cellView(cell: CellOut | null | undefined, assessment: CellColumn, now: number): CellView {
  const labels = assessment.scheme?.labels ?? null;
  if (!cell) {
    return {
      kind: isPastDue(assessment.due_at, now) ? "missing" : "none",
      late: false, overridden: false, released: false, unreleased: false,
      value: "", label: null, points: "", percentile: "", thresholds: [], labels,
    };
  }
  const kind: CellKind = cell.state === "excused" ? "excused"
    : cell.state === "pending_review" ? "needs_review"
    : cell.state === "no_attempts" ? "no_attempts" : "graded";
  const released = !!cell.released_at;
  const scored = kind === "graded" || (kind === "needs_review" && cell.has_override);
  /** excused and no-attempt cells carry no numbers */
  const blank = kind === "excused" || kind === "no_attempts";
  const points = cell.effective_points !== null && cell.effective_points !== undefined
    ? fmtPointsOf(cell.effective_points, cell.points_possible)
    : fmtPointsOf(cell.raw_points, cell.points_possible);
  return {
    kind,
    late: kind !== "no_attempts" && (toNum(cell.late_deduction) ?? 0) > 0,
    overridden: kind !== "no_attempts" && !!cell.has_override,
    released,
    unreleased: scored && !released,
    value: blank ? "" : fmtNum(cell.display_value),
    label: blank ? null : cell.label || null,
    points: blank ? "" : points,
    percentile: blank ? "" : fmtPercentile(cell.percentile),
    thresholds: blank ? [] : reachedThresholds(cell.thresholds),
    labels,
  };
}

/** Keep only the CellOut fields of a submission detail (to patch the grid after a panel action). */
export function cellFromSubmission(s: SubmissionStaffOut): CellOut {
  return {
    submission_id: s.submission_id,
    state: s.state,
    kept_attempt_id: s.kept_attempt_id,
    attempts_counted: s.attempts_counted,
    raw_points: s.raw_points,
    points_possible: s.points_possible,
    late_deduction: s.late_deduction,
    override_points: s.override_points,
    has_override: s.has_override,
    effective_points: s.effective_points,
    display_value: s.display_value,
    label: s.label,
    percentile: s.percentile,
    passed: s.passed,
    thresholds: s.thresholds,
    released_at: s.released_at,
    version: s.version,
  };
}

/** Replace (or, with `null`, remove) one cell; returns the same array when the row is not loaded. */
export function patchCell(rows: GbRowOut[], enrollmentId: string, assessmentId: string, cell: CellOut | null): GbRowOut[] {
  const i = rows.findIndex((r) => r.enrollment_id === enrollmentId);
  if (i < 0) return rows;
  const cells = { ...rows[i].cells };
  if (cell) cells[assessmentId] = cell;
  else delete cells[assessmentId];
  const next = rows.slice();
  next[i] = { ...rows[i], cells };
  return next;
}

/** Append a page, replacing rows already loaded (a student can move between pages if the roster changes). */
export function mergeRows(prev: GbRowOut[], page: GbRowOut[]): GbRowOut[] {
  const seen = new Map(page.map((r) => [r.enrollment_id, r] as const));
  const kept = prev.map((r) => seen.get(r.enrollment_id) ?? r);
  const have = new Set(prev.map((r) => r.enrollment_id));
  return [...kept, ...page.filter((r) => !have.has(r.enrollment_id))];
}

/** Percent with up to two decimals and a % sign; empty when unknown. */
export function fmtPercent(v: Num | null | undefined): string {
  const s = fmtNum(v);
  return s ? `${s}%` : "";
}

// ---------------------------------------------------------------------------
// override form
// ---------------------------------------------------------------------------

export type OverrideIssue = "points_required" | "points_invalid" | "points_range" | "reason_required" | "reason_too_long";

export const REASON_MAX = 500;

/** Client-side mirror of the override rules (the server stays authoritative). */
export function checkOverride(pointsText: string, reason: string, possible: Num | null | undefined): { points: number | null; issues: OverrideIssue[] } {
  const raw = pointsText.trim().replace(",", ".");
  const issues: OverrideIssue[] = [];
  if (!raw) return { points: null, issues: ["points_required"] };
  const n = Number(raw);
  if (!Number.isFinite(n)) return { points: null, issues: ["points_invalid"] };
  const max = toNum(possible);
  if (n < 0 || (max !== null && n > max)) issues.push("points_range");
  const r = reason.trim();
  if (!r) issues.push("reason_required");
  if (r.length > REASON_MAX) issues.push("reason_too_long");
  return { points: Math.round(n * 100) / 100, issues };
}

// ---------------------------------------------------------------------------
// attempts and events
// ---------------------------------------------------------------------------

/** Teachers may void graded or needs-review attempts only (P4-20). */
export function canVoid(a: Pick<SubmissionAttemptOut, "status">): boolean {
  return a.status === "graded" || a.status === "needs_review";
}

/** Late duration rounded up to whole hours and split into days/hours (0 -> null). */
export function lateParts(seconds: number | null | undefined): { days: number; hours: number } | null {
  if (!seconds || seconds <= 0) return null;
  const h = Math.ceil(seconds / 3600);
  return { days: Math.floor(h / 24), hours: h % 24 };
}

function scalar(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number" || typeof v === "string") {
    const n = typeof v === "number" ? v : Number(v);
    return typeof v === "string" && (v.trim() === "" || !Number.isFinite(n)) ? v : fmtNum(n) || String(v);
  }
  return "";
}

/** Changed scalar fields of a grade event (`old` vs `new`), sorted by key; objects and arrays are skipped. */
export function eventChanges(e: Pick<GradeEventOut, "old" | "new">): { key: string; from: string; to: string }[] {
  const o = e.old ?? {};
  const n = e.new ?? {};
  const keys = Array.from(new Set([...Object.keys(o), ...Object.keys(n)])).sort();
  const out: { key: string; from: string; to: string }[] = [];
  for (const k of keys) {
    const a = o[k];
    const b = n[k];
    if ((a !== null && typeof a === "object") || (b !== null && typeof b === "object")) continue;
    const from = scalar(a);
    const to = scalar(b);
    if (from !== to) out.push({ key: k, from, to });
  }
  return out;
}

// ---------------------------------------------------------------------------
// regrade loop (P4-15: call again until pending is 0)
// ---------------------------------------------------------------------------

export interface RegradeProgress {
  regraded: number;
  pending: number;
  rounds: number;
}

export type RegradeEnd = "done" | "stopped" | "stalled" | "max_rounds";

/**
 * Calls `call` until `pending` is 0. Stops when `shouldStop()` is true, when a round makes no progress
 * (`regraded` 0 and `pending` not smaller: avoids an endless loop), or after `maxRounds`. Errors propagate.
 */
export async function runRegrade(
  call: () => Promise<RegradeOut>,
  onProgress: (p: RegradeProgress) => void,
  shouldStop: () => boolean,
  maxRounds = 50,
): Promise<{ end: RegradeEnd; progress: RegradeProgress }> {
  const p: RegradeProgress = { regraded: 0, pending: 0, rounds: 0 };
  let lastPending = Number.POSITIVE_INFINITY;
  while (p.rounds < maxRounds) {
    const r = await call();
    p.rounds += 1;
    p.regraded += Math.max(0, r.regraded);
    p.pending = Math.max(0, r.pending);
    onProgress({ ...p });
    if (p.pending === 0) return { end: "done", progress: p };
    if (r.regraded <= 0 && p.pending >= lastPending) return { end: "stalled", progress: p };
    lastPending = p.pending;
    if (shouldStop()) return { end: "stopped", progress: p };
  }
  return { end: "max_rounds", progress: p };
}
