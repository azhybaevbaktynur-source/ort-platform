// Phase 5 S3: course catalog and one-click open join (docs/phases/PHASE_5_DESIGN.md section 5).
// Phase 9 S4: search and filters, card extras, the course landing (docs/phases/PHASE_9_DESIGN.md §4.6).
import { lmsFetch } from "./client";
import type {
  ApplicationStatus, CourseRole, EnrollmentMode, EnrollmentState, JoinOut, Lang, LocalizedText, PageOut, PublicFormOut,
} from "./types";

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
  // --- Phase 9 S4 ---
  /** Root organization of the course's tree. */
  organization_id: string;
  organization_name: string;
  has_active_form: boolean;
  my_application: { id: string; status: ApplicationStatus } | null;
}

/** `GET /catalog/courses/{id}`: the same allow-list plus teachers' public names, dates and the active form. */
export interface CourseLandingOut extends CatalogCourseOut {
  teachers: string[];
  starts_at: string | null;
  ends_at: string | null;
  form: PublicFormOut | null;
}

export interface CatalogFilters {
  q?: string;
  language?: Lang | "";
  mode?: EnrollmentMode | "";
  organization_id?: string;
}

const enc = encodeURIComponent;

export const listCatalog = (cursor?: string | null, limit = 12, filters: CatalogFilters = {}) =>
  lmsFetch<PageOut<CatalogCourseOut>>("/catalog/courses", {
    params: {
      cursor, limit, q: filters.q?.trim() || undefined, language: filters.language || undefined,
      mode: filters.mode || undefined, organization_id: filters.organization_id || undefined,
    },
  });

export const getCourseLanding = (courseId: string) => lmsFetch<CourseLandingOut>(`/catalog/courses/${enc(courseId)}`);

/** Open-mode courses only; any other course answers the same 404 as a bad join code. */
export const joinOpenCourse = (courseId: string) =>
  lmsFetch<JoinOut>(`/courses/${enc(courseId)}/join`, { method: "POST" });

export const isActiveMember = (c: Pick<CatalogCourseOut, "my_enrollment">) => c.my_enrollment?.state === "active";

export const isFormMode = (mode: EnrollmentMode) => mode === "form_auto" || mode === "form_review";
