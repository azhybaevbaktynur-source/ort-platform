/**
 * Step 3a S3/S4 (STUDENT_IA_DESIGN §2.4, §4): where «Выбрать курсы» / «Добавить курс» / «Подобрать курсы» and
 * «Продолжить» with no course lead (the choose step), and the step's and the catalog's pure rules: subject sections,
 * the pre-checked main course, the default exam family. Dependency-free (structural types only) so
 * `chooseCourses.check.ts` runs it with plain `tsc` + `node`.
 */
export function chooseCoursesHref(lang: string): string {
  return `/${lang}/courses/choose`;
}

/** The only fields the rules read (`ExamCourseOut` of `GET /catalog/exams`, `CatalogCourseOut` of the catalog). */
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

/** The main course language for a UI language: ky -> ky, everything else (ru, en) -> ru (§4). */
export const mainLanguageFor = (uiLang: string) => (uiLang === "ky" ? "ky" : "ru");

/**
 * The step's pre-checked courses of one family: the first main course in the UI language's main language that the
 * student is not in yet (none when there is no such course). Courses the student is in are shown checked and
 * disabled, never counted as chosen.
 */
export function defaultChecked<T extends SubjectCourse & { enrolled: boolean }>(courses: T[], uiLang: string): string[] {
  const want = mainLanguageFor(uiLang);
  const main = courses.find((c) => !c.subject && c.default_language === want);
  return main && !main.enrolled ? [main.id] : [];
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

/** The ids a press of «Записаться» sends: the checked ones the student is not in yet, in the page's order. */
export function idsToJoin<T extends { id: string; enrolled: boolean }>(courses: T[], checked: ReadonlySet<string>): string[] {
  return courses.filter((c) => !c.enrolled && checked.has(c.id)).map((c) => c.id);
}

/** `joined` ids a refused `POST /catalog/choose` still carries (422 `course_not_choosable`: the ones joined before). */
export function joinedOfRefusal(details: unknown): string[] {
  if (!Array.isArray(details)) return [];
  const row = details.find((d) => !!d && typeof d === "object" && (d as { msg?: unknown }).msg === "joined") as { joined?: unknown } | undefined;
  return Array.isArray(row?.joined) ? row!.joined.filter((x): x is string => typeof x === "string") : [];
}
