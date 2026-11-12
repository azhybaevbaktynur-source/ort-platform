/**
 * Step 3a S3 (STUDENT_IA_DESIGN §2.2, §2.3, §6.5): the groups of the hub and of «Мои курсы»: ОРТ, НЦТ, Другие курсы
 * (fixed order, empty groups left out). A course's group is its `exam_family` (S1; the backfill copies the exam's family
 * onto an attached lesson course); a lesson course without one sits in its exam's group when the exam is in the same
 * list. Mirrors the backend registry keys (`courses/exam_families.py`). Dependency-free.
 */

export type CourseGroupKey = "ort" | "nct" | "other";
export const GROUP_ORDER: readonly CourseGroupKey[] = ["ort", "nct", "other"];
/** Cards per group on the hub (decision N10); `/courses` shows them all. */
export const HUB_GROUP_MAX = 4;

export interface GroupableCourse {
  id: string;
  exam_family?: string | null;
  exam_course_id?: string | null;
}

const asGroup = (family: string | null | undefined): CourseGroupKey | null =>
  family === "ort" || family === "nct" ? family : null;

export interface CourseGroup<T> {
  key: CourseGroupKey;
  courses: T[];
}

/** Course id -> its group, for every course of the list (the sidebar rows' icon). */
export function courseGroups(courses: GroupableCourse[]): Map<string, CourseGroupKey> {
  const byId = new Map(courses.map((c) => [c.id, c]));
  const groupOf = (c: GroupableCourse): CourseGroupKey => {
    const own = asGroup(c.exam_family);
    if (own) return own;
    const exam = c.exam_course_id ? byId.get(c.exam_course_id) : undefined;
    return (exam && asGroup(exam.exam_family)) || "other";
  };
  return new Map(courses.map((c) => [c.id, groupOf(c)]));
}

/** The courses by group, in `GROUP_ORDER`, each in the list's order; groups without a course are left out. */
export function groupCourses<T extends GroupableCourse>(courses: T[]): CourseGroup<T>[] {
  const groups = courseGroups(courses);
  const out = new Map<CourseGroupKey, T[]>(GROUP_ORDER.map((k) => [k, []]));
  for (const c of courses) out.get(groups.get(c.id) ?? "other")!.push(c);
  return GROUP_ORDER.map((key) => ({ key, courses: out.get(key)! })).filter((g) => g.courses.length > 0);
}
