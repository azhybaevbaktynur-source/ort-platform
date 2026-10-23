// Phase 5 S3: course catalog and one-click open join (docs/phases/PHASE_5_DESIGN.md section 5).
import { lmsFetch } from "./client";
import type { CourseRole, EnrollmentMode, EnrollmentState, JoinOut, Lang, LocalizedText, PageOut } from "./types";

export interface CatalogEnrollmentOut {
  role: CourseRole;
  state: EnrollmentState;
}

export interface CatalogCourseOut {
  id: string;
  title: LocalizedText;
  description: LocalizedText | null;
  languages: Lang[];
  default_language: Lang;
  enrollment_mode: EnrollmentMode;
  student_count: number;
  my_enrollment: CatalogEnrollmentOut | null;
}

const enc = encodeURIComponent;

export const listCatalog = (cursor?: string | null, limit = 12) =>
  lmsFetch<PageOut<CatalogCourseOut>>("/catalog/courses", { params: { cursor, limit } });

/** Open-mode courses only; any other course answers the same 404 as a bad join code. */
export const joinOpenCourse = (courseId: string) =>
  lmsFetch<JoinOut>(`/courses/${enc(courseId)}/join`, { method: "POST" });

export const isActiveMember = (c: CatalogCourseOut) => c.my_enrollment?.state === "active";
