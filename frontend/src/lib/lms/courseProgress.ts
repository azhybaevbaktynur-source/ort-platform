/**
 * Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3.1): the one progress rule of a course, so the course header, the
 * course card and the sidebar ring never disagree: the lesson progress (`ModulesStudentOut.progress`, or the home
 * card's `progress`, which count the same requirements) when the course has modules, else tests done / published
 * tests when that is known, else nothing (no bar).
 *
 * Dependency-free (structural types only).
 */

export interface ProgressCount {
  done: number;
  total: number;
}

export interface CourseProgressInput {
  /** lesson progress of the course's modules (null / absent: no modules or not known) */
  modules?: ProgressCount | null;
  /** tests done / published tests (null / absent: not known) */
  tests?: ProgressCount | null;
}

export interface CourseProgressOut extends ProgressCount {
  /** 0..100, rounded */
  percent: number;
  source: "modules" | "tests";
}

function valid(p: ProgressCount | null | undefined): p is ProgressCount {
  return !!p && Number.isFinite(p.done) && Number.isFinite(p.total) && p.total > 0;
}

export function courseProgress(input: CourseProgressInput): CourseProgressOut | null {
  const pick = valid(input.modules) ? { p: input.modules, source: "modules" as const }
    : valid(input.tests) ? { p: input.tests, source: "tests" as const } : null;
  if (!pick) return null;
  const done = Math.max(0, Math.min(pick.p.done, pick.p.total));
  return { done, total: pick.p.total, percent: Math.round((done / pick.p.total) * 100), source: pick.source };
}
