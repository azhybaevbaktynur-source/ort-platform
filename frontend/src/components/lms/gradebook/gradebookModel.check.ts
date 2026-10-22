/**
 * Dependency-free check of the gradebook helpers.
 * Run (from repo root):
 *   cd frontend && npx tsc --outDir /tmp/agy_f3_check --module commonjs --target es2020 --skipLibCheck \
 *     src/components/lms/gradebook/gradebookModel.ts src/components/lms/gradebook/gradebookModel.check.ts && \
 *     node /tmp/agy_f3_check/components/lms/gradebook/gradebookModel.check.js
 */
import {
  cellFromSubmission, cellView, checkOverride, canVoid, eventChanges, fmtPercent, fmtPointsOf, isPastDue, lateParts,
  mergeRows, patchCell, reachedThresholds, runRegrade,
} from "./gradebookModel";
import type { CellOut, GbRowOut, RegradeOut, SubmissionStaffOut } from "../../../lib/lms/gradingTypes";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}
const eq = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

const NOW = Date.parse("2026-10-23T12:00:00Z");
const cell = (over: Partial<CellOut> = {}): CellOut => ({
  submission_id: "s1", state: "graded", kept_attempt_id: "t1", attempts_counted: 1, raw_points: "18.00",
  points_possible: "30.00", late_deduction: "0.00", override_points: null, has_override: false, effective_points: "18.00",
  display_value: "187.00", label: null, percentile: "92.30", passed: null, thresholds: { golden_certificate: false },
  released_at: "2026-10-22T10:00:00Z", version: 3, ...over,
});

async function main() {
  // isPastDue
  ok(!isPastDue(null, NOW), "no due date is never past");
  ok(isPastDue("2026-10-22T00:00:00Z", NOW), "yesterday is past");
  ok(!isPastDue("2026-10-24T00:00:00Z", NOW), "tomorrow is not past");
  ok(!isPastDue("garbage", NOW), "unparseable is not past");

  // formatting
  ok(fmtPointsOf("18.50", "30.00") === "18.5 / 30", "points drop trailing zeros");
  ok(fmtPointsOf(null, "30") === "", "unknown points -> empty");
  ok(fmtPointsOf(7, null) === "7", "no possible -> just points");
  ok(fmtPercent("87.456") === "87.46%", "percent rounds to 2 decimals");
  ok(fmtPercent(null) === "", "null percent -> empty");
  ok(eq(reachedThresholds({ b: true, a: true, c: false }), ["a", "b"]), "reached thresholds sorted");

  // cell views
  const none = cellView(undefined, { due_at: null }, NOW);
  ok(none.kind === "none" && !none.released && none.value === "", "no submission, no due date -> none");
  ok(cellView(undefined, { due_at: "2026-10-01T00:00:00Z" }, NOW).kind === "missing", "no submission after due -> missing");
  ok(cellView(undefined, { due_at: "2026-11-01T00:00:00Z" }, NOW).kind === "none", "no submission before due -> none");

  const g = cellView(cell(), { due_at: null }, NOW);
  ok(g.kind === "graded" && g.value === "187" && g.points === "18 / 30" && g.percentile === "92.3", "graded cell values");
  ok(g.released && !g.unreleased && !g.late && !g.overridden, "graded released cell flags");
  ok(eq(g.thresholds, []), "unreached threshold not listed");

  const gold = cellView(cell({ thresholds: { golden_certificate: true } }), { due_at: null }, NOW);
  ok(eq(gold.thresholds, ["golden_certificate"]), "reached threshold listed");

  const un = cellView(cell({ released_at: null }), { due_at: null }, NOW);
  ok(un.unreleased && !un.released, "graded but not released -> unreleased");

  const late = cellView(cell({ late_deduction: "1.80", effective_points: "16.20" }), { due_at: null }, NOW);
  ok(late.late && late.points === "16.2 / 30", "late deduction flag and effective points");

  const ov = cellView(cell({ has_override: true, override_points: "25", effective_points: "25.00" }), { due_at: null }, NOW);
  ok(ov.overridden && ov.points === "25 / 30", "override flag and effective points");

  const pr = cellView(cell({ state: "pending_review", display_value: null, effective_points: null, raw_points: "12", released_at: null }), { due_at: null }, NOW);
  ok(pr.kind === "needs_review" && pr.points === "12 / 30" && !pr.unreleased, "needs review: raw points, not flagged unreleased");

  const prOv = cellView(cell({ state: "pending_review", has_override: true, released_at: null }), { due_at: null }, NOW);
  ok(prOv.unreleased, "needs review with override counts as scored");

  const ex = cellView(cell({ state: "excused" }), { due_at: "2026-10-01T00:00:00Z" }, NOW);
  ok(ex.kind === "excused" && ex.value === "" && ex.points === "" && ex.label === null, "excused hides numbers");

  const na = cellView(cell({ state: "no_attempts", kept_attempt_id: null, attempts_counted: 0, raw_points: null, effective_points: null,
    display_value: null, late_deduction: "2.00", released_at: null, thresholds: { golden_certificate: true } }), { due_at: "2026-10-01T00:00:00Z" }, NOW);
  ok(na.kind === "no_attempts" && na.value === "" && na.points === "" && na.percentile === "" && na.label === null
    && na.thresholds.length === 0 && !na.late && !na.unreleased, "no attempts (all voided): own kind, no numbers, no markers");

  const top = { en: "Top", ru: "Высший" };
  const bl = cellView(cell({ display_value: null, label: "top" }), { due_at: null, scheme: { labels: { top } } }, NOW);
  ok(bl.label === "top" && eq(bl.labels, { top }), "cell carries the column scheme's label map");
  ok(cellView(cell(), { due_at: null }, NOW).labels === null, "no scheme ref -> no label map");
  ok(eq(cellView(undefined, { due_at: null, scheme: { labels: { top } } }, NOW).labels, { top }), "empty cell keeps the map");

  const pf = cellView(cell({ display_value: null, label: "pass", passed: true }), { due_at: null }, NOW);
  ok(pf.value === "" && pf.label === "pass", "pass/fail: label without value");

  // cellFromSubmission
  const sub: SubmissionStaffOut = {
    ...cell({ version: 9 }), override_reason: "x", override_by_name: "T", override_at: null, attempts: [], events: [],
  };
  const c2 = cellFromSubmission(sub);
  ok(c2.version === 9 && !("events" in c2) && !("override_reason" in c2), "cellFromSubmission keeps cell fields only");

  // patchCell / mergeRows
  const row = (id: string, cells: Record<string, CellOut> = {}): GbRowOut => ({
    enrollment_id: id, user_id: "u" + id, student_name: id, cells,
    total: { current_percent: null, final_percent: null, display_value: null, label: null, passed: null, warnings: [] },
  });
  const rows = [row("e1", { a1: cell() }), row("e2")];
  const p1 = patchCell(rows, "e2", "a1", cell({ submission_id: "s2" }));
  ok(p1 !== rows && p1[1].cells.a1.submission_id === "s2" && rows[1].cells.a1 === undefined, "patchCell adds immutably");
  const p2 = patchCell(p1, "e1", "a1", null);
  ok(p2[0].cells.a1 === undefined && p1[0].cells.a1 !== undefined, "patchCell removes immutably");
  ok(patchCell(rows, "zz", "a1", null) === rows, "patchCell on unknown row is a no-op");
  const m = mergeRows([row("e1"), row("e2")], [row("e2", { a1: cell() }), row("e3")]);
  ok(eq(m.map((r) => r.enrollment_id), ["e1", "e2", "e3"]) && !!m[1].cells.a1, "mergeRows dedupes and refreshes");

  // override check
  ok(eq(checkOverride("", "r", "30").issues, ["points_required"]), "override: points required");
  ok(eq(checkOverride("abc", "r", "30").issues, ["points_invalid"]), "override: invalid number");
  ok(eq(checkOverride("31", "r", "30").issues, ["points_range"]), "override: above possible");
  ok(eq(checkOverride("-1", "r", "30").issues, ["points_range"]), "override: negative");
  ok(eq(checkOverride("12,5", "  ", "30"), { points: 12.5, issues: ["reason_required"] }), "override: comma decimal, reason required");
  ok(eq(checkOverride("30", "ok", "30"), { points: 30, issues: [] }), "override: max allowed");
  ok(checkOverride("1", "x".repeat(501), null).issues.includes("reason_too_long"), "override: reason length");

  // attempts
  ok(canVoid({ status: "graded" }) && canVoid({ status: "needs_review" }), "graded/needs_review can be voided");
  ok(!canVoid({ status: "in_progress" }) && !canVoid({ status: "void" }), "in_progress/void cannot");
  ok(lateParts(0) === null, "not late");
  ok(eq(lateParts(60), { days: 0, hours: 1 }), "a minute late rounds up to 1 hour");
  ok(eq(lateParts(86400 * 2 + 3600 * 5), { days: 2, hours: 5 }), "2 days 5 hours");

  // events
  ok(eq(eventChanges({ old: { override_points: null, state: "graded" }, new: { override_points: "25.00", state: "graded" } }),
    [{ key: "override_points", from: "—", to: "25" }]), "event diff shows changed scalars only");
  ok(eq(eventChanges({ old: null, new: { released_at: "2026-10-22T10:00:00Z", x: { a: 1 } } }),
    [{ key: "released_at", from: "—", to: "2026-10-22T10:00:00Z" }]), "event diff skips objects, handles null old");
  ok(eq(eventChanges({ old: { excused: false }, new: { excused: true } }), [{ key: "excused", from: "false", to: "true" }]), "event diff booleans");

  // regrade loop
  const seq = (outs: RegradeOut[]) => { let i = 0; return () => Promise.resolve(outs[Math.min(i++, outs.length - 1)]); };
  const R = (regraded: number, pending: number): RegradeOut => ({ regraded, pending, scheme_version_id: null });
  const seen: number[] = [];
  const r1 = await runRegrade(seq([R(2000, 2500), R(2000, 500), R(500, 0)]), (p) => seen.push(p.pending), () => false);
  ok(r1.end === "done" && r1.progress.regraded === 4500 && r1.progress.rounds === 3 && eq(seen, [2500, 500, 0]), "regrade loops until pending 0");
  const r2 = await runRegrade(seq([R(0, 0)]), () => {}, () => false);
  ok(r2.end === "done" && r2.progress.rounds === 1, "nothing stale: one call");
  const r3 = await runRegrade(seq([R(0, 10), R(0, 10)]), () => {}, () => false);
  ok(r3.end === "stalled" && r3.progress.rounds === 2, "no progress -> stalled");
  let stop = false;
  const r4 = await runRegrade(seq([R(100, 300), R(100, 200)]), () => { stop = true; }, () => stop);
  ok(r4.end === "stopped" && r4.progress.rounds === 1, "stop after the current round");
  const r5 = await runRegrade(seq([R(1, 5), R(1, 4), R(1, 3)]), () => {}, () => false, 2);
  ok(r5.end === "max_rounds" && r5.progress.rounds === 2, "max rounds cap");
  let threw = false;
  try { await runRegrade(() => Promise.reject(new Error("rate_limited")), () => {}, () => false); } catch { threw = true; }
  ok(threw, "errors propagate");

  if (failed) { console.error(`${failed} check(s) failed`); process.exit(1); }
  console.log("all gradebook checks passed");
}

void main();
