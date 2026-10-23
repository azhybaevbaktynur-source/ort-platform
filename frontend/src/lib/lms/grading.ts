/** Phase 4 grading API client (docs/phases/PHASE_4_DESIGN.md section 5). Types in gradingTypes.ts. */
import { lmsFetch } from "./client";
import type { PageOut } from "./types";
import type {
  CategoryIn, CategoryOut, CourseGradingIn, CourseGradingOut, ExcuseIn, GradebookPageOut, GradebookQuery,
  MyGradesOut, OverrideIn, RegradeOut, ReleaseIn, ReleaseOut, SchemeCreateIn, SchemeOut, SchemeParams,
  SchemePreviewIn, SchemePreviewOut, SchemeSummaryOut, SchemeVersionOut, SubmissionStaffOut, UnreleaseOut,
} from "./gradingTypes";
import type { LocalizedText } from "./types";

const e = encodeURIComponent;

// ---- Scheme library ----
const S = "/grading-schemes";
const scheme = (id: string) => `${S}/${e(id)}`;

export const listSchemes = (opts: { cursor?: string | null; limit?: number; include_system?: boolean } = {}) =>
  lmsFetch<PageOut<SchemeSummaryOut>>(S, { params: { cursor: opts.cursor, limit: opts.limit, include_system: opts.include_system } });
export const createScheme = (body: SchemeCreateIn) => lmsFetch<SchemeOut>(S, { method: "POST", body });
export const getScheme = (id: string) => lmsFetch<SchemeOut>(scheme(id));
export const updateSchemeTitle = (id: string, title: LocalizedText) =>
  lmsFetch<SchemeOut>(scheme(id), { method: "PATCH", body: { title } });
export const deleteScheme = (id: string) => lmsFetch<void>(scheme(id), { method: "DELETE" });
export const restoreScheme = (id: string) => lmsFetch<SchemeOut>(`${scheme(id)}/restore`, { method: "POST" });
export const addSchemeVersion = (id: string, params: SchemeParams) =>
  lmsFetch<SchemeVersionOut>(`${scheme(id)}/versions`, { method: "POST", body: { params } });
export const previewScheme = (body: SchemePreviewIn, signal?: AbortSignal) =>
  lmsFetch<SchemePreviewOut>(`${S}/preview`, { method: "POST", body, signal });

// ---- Course grading settings and categories ----
const course = (c: string) => `/courses/${e(c)}`;

export const getCourseGrading = (courseId: string) => lmsFetch<CourseGradingOut>(`${course(courseId)}/grading`);
export const updateCourseGrading = (courseId: string, body: CourseGradingIn) =>
  lmsFetch<CourseGradingOut>(`${course(courseId)}/grading`, { method: "PUT", body });
export const createCategory = (courseId: string, body: CategoryIn) =>
  lmsFetch<CategoryOut>(`${course(courseId)}/grade-categories`, { method: "POST", body });
export const updateCategory = (courseId: string, categoryId: string, body: CategoryIn) =>
  lmsFetch<CategoryOut>(`${course(courseId)}/grade-categories/${e(categoryId)}`, { method: "PATCH", body });
export const deleteCategory = (courseId: string, categoryId: string) =>
  lmsFetch<void>(`${course(courseId)}/grade-categories/${e(categoryId)}`, { method: "DELETE" });
export const reorderCategories = (courseId: string, categoryIds: string[]) =>
  lmsFetch<CategoryOut[]>(`${course(courseId)}/grade-categories/order`, { method: "PUT", body: { category_ids: categoryIds } });

// ---- Gradebook and submissions (staff) ----
export const getGradebook = (courseId: string, q: GradebookQuery = {}) =>
  lmsFetch<GradebookPageOut>(`${course(courseId)}/gradebook`, {
    params: {
      cursor: q.cursor,
      limit: q.limit,
      assessment_ids: q.assessment_ids && q.assessment_ids.length ? q.assessment_ids.join(",") : undefined,
    },
  });
export const getSubmission = (courseId: string, submissionId: string) =>
  lmsFetch<SubmissionStaffOut>(`${course(courseId)}/submissions/${e(submissionId)}`);
export const overrideSubmission = (courseId: string, submissionId: string, body: OverrideIn) =>
  lmsFetch<SubmissionStaffOut>(`${course(courseId)}/submissions/${e(submissionId)}/override`, { method: "PUT", body });
export const excuseSubmission = (courseId: string, submissionId: string, body: ExcuseIn) =>
  lmsFetch<SubmissionStaffOut>(`${course(courseId)}/submissions/${e(submissionId)}/excuse`, { method: "PUT", body });

const grades = (c: string, a: string) => `${course(c)}/assessments/${e(a)}/grades`;
export const releaseGrades = (courseId: string, assessmentId: string, body: ReleaseIn = {}) =>
  lmsFetch<ReleaseOut>(`${grades(courseId, assessmentId)}/release`, { method: "POST", body });
export const unreleaseGrades = (courseId: string, assessmentId: string, body: ReleaseIn = {}) =>
  lmsFetch<UnreleaseOut>(`${grades(courseId, assessmentId)}/unrelease`, { method: "POST", body });
export const regradeAssessment = (courseId: string, assessmentId: string) =>
  lmsFetch<RegradeOut>(`${grades(courseId, assessmentId)}/regrade`, { method: "POST" });

// ---- Student ----
export const getMyGrades = (courseId: string) => lmsFetch<MyGradesOut>(`${course(courseId)}/grades/mine`);
