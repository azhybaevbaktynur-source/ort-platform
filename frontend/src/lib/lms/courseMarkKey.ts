/**
 * Step 3a S9 (STUDENT_IA_DESIGN §0.4, V11): which mark a course shows, as a plain key (dependency-free, so
 * `courseIcon.check.ts` runs under node; `courseIcon.tsx` maps the key to its lucide icon). A subject course shows its
 * subject; a course without a subject shows its exam family's mark (ORT main → the golden certificate `award`, НЦТ
 * main → `clipboard-check`); a course without a family (a teacher's course) the book. Unknown values (a newer backend
 * registry) fall back the same way. The brand's graduation cap is never a course mark.
 */

export type CourseMarkKey =
  | "sigma" | "atom" | "flask-conical" | "dna" | "landmark" | "globe" | "languages" | "book-text"
  | "award" | "clipboard-check" | "book-open";

/** The registry's ten subjects (backend `exam_families.SUBJECTS`) onto the owner's classes. */
export const SUBJECT_MARK: Readonly<Record<string, CourseMarkKey>> = {
  math: "sigma",
  physics: "atom",
  chemistry: "flask-conical",
  biology: "dna",
  history: "landmark",
  geography: "globe",
  kyrgyz: "languages",
  russian: "languages",
  english: "languages",
  literature: "book-text",
};

/** A family's main course (no subject). */
export const FAMILY_MARK: Readonly<Record<string, CourseMarkKey>> = {
  ort: "award",
  nct: "clipboard-check",
};

export const DEFAULT_MARK: CourseMarkKey = "book-open";

export interface CourseMarkInput {
  exam_family?: string | null;
  subject?: string | null;
}

export function courseMarkKey(c: CourseMarkInput | null | undefined): CourseMarkKey {
  const subject = c?.subject ? SUBJECT_MARK[c.subject] : undefined;
  if (subject) return subject;
  const family = c?.exam_family ? FAMILY_MARK[c.exam_family] : undefined;
  return family ?? DEFAULT_MARK;
}
