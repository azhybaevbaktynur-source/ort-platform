/**
 * Step 3a S4 (STUDENT_IA_DESIGN §2.4): the catalog's pure rules: subject sections and the default exam family. S7 (V3)
 * removed the choose step and its helpers; the file keeps its name. Dependency-free (structural types only) so
 * `chooseCourses.check.ts` runs it with plain `tsc` + `node`.
 */

/** The only fields the rules read (`CatalogCourseOut` of the catalog). */
export interface SubjectCourse {
  id: string;
  subject?: string | null;
  default_language: string;
}

export interface SubjectSection<T> {
  /** `main` = the family's main courses (no subject), else the subject key */
  key: string;
  courses: T[];
}

/**
 * The courses by section: the main courses first, then one section per subject in `subjectOrder` (the registry's
 * order); a subject the order does not know goes last, in the list's order. Courses keep the server's order inside
 * a section. Empty sections are left out.
 */
export function subjectSections<T extends SubjectCourse>(courses: T[], subjectOrder: readonly string[]): SubjectSection<T>[] {
  const keys: string[] = ["main", ...subjectOrder];
  const out = new Map<string, T[]>(keys.map((k) => [k, []]));
  for (const c of courses) {
    const key = c.subject || "main";
    if (!out.has(key)) { out.set(key, []); keys.push(key); }
    out.get(key)!.push(c);
  }
  return keys.map((key) => ({ key, courses: out.get(key)! })).filter((s) => s.courses.length > 0);
}

/**
 * Decision N9: the family of the student's newest exam course (`mine` is newest enrolment first), else ОРТ, else the
 * first family there is; only families in `available` (those with listed courses). Null: no family at all.
 */
export function defaultFamily(available: readonly string[], mine: readonly { exam_family?: string | null }[]): string | null {
  const newest = mine.find((c) => !!c.exam_family && available.includes(c.exam_family))?.exam_family;
  if (newest) return newest;
  if (available.includes("ort")) return "ort";
  return available[0] ?? null;
}
