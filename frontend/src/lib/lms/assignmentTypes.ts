// Phase 7a S5: TypeScript mirrors of the assignments API (docs/phases/PHASE_7A_DESIGN.md sections 2 and 4).
// snake_case as on the wire. Decimal columns may arrive as strings (`Num`). Fields marked "assumed" are not spelled
// out in the design's section 4 and are read defensively (optional) so a backend without them still renders.
import type { AssessmentPreset, AssessmentStatus } from "./assessmentTypes";
import type { CellOut, GradeRelease, Num, SchemeLabelValue, SchemeType, SchemeVersionRef, SubmissionStaffOut } from "./gradingTypes";
import type { Lang, LocalizedText } from "./types";

export type AssignmentKind = "none" | "text" | "file" | "quiz";
export const ASSIGNMENT_KINDS: AssignmentKind[] = ["text", "file", "none", "quiz"];

/** A student's own status on an assignment (section 4.1). */
export type AssignmentStudentStatus = "not_started" | "in_progress" | "submitted" | "graded" | "missing" | "excused";

/** Hand-in limits shown on the submit page (section 3.5; the server stays authoritative). */
export const HAND_IN_TEXT_MAX = 20000;
export const HAND_IN_PDF_MAX_BYTES = 10 * 1024 * 1024;
export const HAND_IN_IMAGE_MAX_BYTES = 2 * 1024 * 1024;
export const HAND_IN_MIME = ["application/pdf", "image/jpeg", "image/png", "image/webp"] as const;
export const HAND_IN_ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp";
export const FEEDBACK_TEXT_MAX = 10000;
export const RUBRIC_MAX_CRITERIA = 30;

/** Counts on staff payloads (section 4.1: submitted / graded / released / stale). */
export interface AssignmentCounts {
  submitted: number;
  graded: number;
  released: number;
  stale: number;
}

/** Brief of the linked assessment on a quiz assignment (staff). Assumed fields beyond `id`. */
export interface AssignmentAssessmentBrief {
  id: string;
  preset?: AssessmentPreset;
  status?: AssessmentStatus;
  item_count?: number;
  has_access_code?: boolean;
}

export interface RubricCriterionOut {
  id: string;
  position: number;
  title: LocalizedText;
  description: LocalizedText | null;
  points: Num;
}

export interface RubricCriterionIn {
  id?: string;
  title: LocalizedText;
  description?: LocalizedText | null;
  points: number;
}

export interface AssignmentStaffSummaryOut {
  id: string;
  course_id: string;
  kind: AssignmentKind;
  assessment_id: string | null;
  title: LocalizedText;
  points_possible: Num | null;
  due_at: string | null;
  available_from: string | null;
  available_until: string | null;
  category_id: string | null;
  grading_scheme_version_id: string | null;
  grade_release: GradeRelease;
  omit_from_total: boolean;
  published: boolean;
  published_at: string | null;
  position: number;
  deleted_at: string | null;
  /** assumed on the summary (the table shows submitted / graded counts) */
  counts?: AssignmentCounts | null;
  /** assumed: preset of the linked assessment (quiz), for the ORT lock and the kind badge */
  preset?: AssessmentPreset | null;
}

export interface AssignmentStaffOut extends AssignmentStaffSummaryOut {
  description: LocalizedText | null;
  assessment: AssignmentAssessmentBrief | null;
  rubric: RubricCriterionOut[];
  counts: AssignmentCounts;
  /** assumed: brief of the grading scheme version (keeps an older version selectable in the picker) */
  scheme?: SchemeVersionRef | null;
}

/** Own grade on a student payload (only when released). */
export interface AssignmentGradeOut {
  display_value: Num | null;
  label: string | null;
  effective_points: Num | null;
  points_possible: Num | null;
  late_deduction?: Num | null;
  passed?: boolean | null;
  scheme_type?: SchemeType | null;
  labels?: Record<string, SchemeLabelValue> | null;
  released_at: string | null;
}

/** One hand-in (append-only; section 2.2). */
export interface HandInOut {
  id: string;
  attempt_no: number;
  kind: "text" | "file";
  body_text: string | null;
  asset_id: string | null;
  /** assumed file metadata for file hand-ins */
  filename?: string | null;
  bytes?: number | null;
  mime?: string | null;
  submitted_at: string;
  late_seconds: number;
  /** assumed: late_seconds > 0 */
  late?: boolean;
}

export interface AssignmentStudentOut {
  id: string;
  kind: AssignmentKind;
  assessment_id: string | null;
  title: LocalizedText;
  points_possible: Num | null;
  /** effective (override-aware) dates */
  due_at: string | null;
  available_from: string | null;
  available_until: string | null;
  /** absent for org admins (J2) */
  status?: AssignmentStudentStatus | null;
  /** null = unlimited (quiz only) */
  attempts_left?: number | null;
  /** assumed: quiz with an open attempt */
  in_progress_attempt_id?: string | null;
  position?: number;
}

export interface AssignmentStudentDetailOut extends AssignmentStudentOut {
  description: LocalizedText | null;
  hand_ins: HandInOut[];
  /** the grade row id (download route); null before the first hand-in */
  submission_id?: string | null;
  grade?: AssignmentGradeOut | null;
  feedback_text?: string | null;
  feedback_asset_id?: string | null;
  /** assumed: file name of the feedback file */
  feedback_filename?: string | null;
}

export type AssignmentOut = AssignmentStaffOut | AssignmentStudentDetailOut;
export function isStaffAssignment(a: AssignmentOut | AssignmentStaffSummaryOut | AssignmentStudentOut): a is AssignmentStaffOut {
  return "published" in a && "grade_release" in a;
}

export interface QuizCreateIn {
  preset?: AssessmentPreset;
  languages: Lang[];
  subject_key?: string;
}

export interface AssignmentCreateIn {
  title: LocalizedText;
  description?: LocalizedText | null;
  kind: AssignmentKind;
  points_possible?: number | null;
  due_at?: string | null;
  available_from?: string | null;
  available_until?: string | null;
  category_id?: string | null;
  grading_scheme_version_id?: string | null;
  grade_release?: GradeRelease;
  omit_from_total?: boolean;
  quiz?: QuizCreateIn;
}

export interface AssignmentUpdateIn {
  title?: LocalizedText;
  description?: LocalizedText | null;
  points_possible?: number | null;
  due_at?: string | null;
  available_from?: string | null;
  available_until?: string | null;
  category_id?: string | null;
  grading_scheme_version_id?: string | null;
  grade_release?: GradeRelease;
  omit_from_total?: boolean;
  published?: boolean;
}

export interface AssignmentListQuery {
  cursor?: string | null;
  limit?: number;
  deleted?: boolean;
  kind?: AssignmentKind | "";
  published?: boolean;
  category_id?: string | null;
}

/** Response of the hand-in file upload (section 4.2). */
export interface UploadedFileOut {
  asset_id: string;
  filename: string;
  bytes: number;
  mime: string;
}

export interface HandInIn {
  body_text?: string;
  asset_id?: string;
}

/** One roster row of the grading screen (section 4.3). */
export interface AssignmentSubmissionRowOut {
  enrollment_id: string;
  user_id: string;
  student_name: string | null;
  cell: CellOut | null;
  hand_in_count: number;
  latest_submitted_at: string | null;
  late: boolean;
  resubmitted: boolean;
}

export interface RubricScoreOut {
  criterion_id: string;
  points: Num;
  comment: string | null;
}

export interface RubricScoreIn {
  criterion_id: string;
  points: number;
  comment?: string | null;
}

export interface ManualGradeIn {
  /** null clears the grade */
  points: number | null;
  rubric_scores?: RubricScoreIn[];
  feedback_text?: string | null;
  feedback_asset_id?: string | null;
  /** optimistic token of the existing row (absent for the first grade) */
  version?: number;
}

/** `SubmissionStaffOut` with the Phase 7a fields (section 4.3). */
export interface AssignmentSubmissionStaffOut extends SubmissionStaffOut {
  assignment_id: string;
  kind: AssignmentKind;
  hand_ins: HandInOut[];
  rubric_scores: RubricScoreOut[];
  feedback_text: string | null;
  feedback_asset_id: string | null;
  graded_by_name: string | null;
  graded_at: string | null;
  graded_item_id?: string | null;
}

/** New `assignments.errors.*` codes (sections 3 and 4). */
export const ASSIGNMENT_ERROR_CODES = [
  "assignment_not_found", "submission_closed", "already_graded", "asset_not_usable", "quiz_body_required",
  "quiz_body_forbidden", "quiz_publish_via_assessment", "quiz_grade_via_attempts", "rubric_locked", "rubric_sum_mismatch",
  "rubric_total_mismatch", "points_out_of_range", "stale_grade", "template_locked", "exam_templates_not_available",
  "access_code_required", "access_code_invalid", "storage_full", "file_too_large", "image_too_large", "submission_not_found",
  "rate_limited", "network", "forbidden", "not_found",
] as const;
export type AssignmentErrorCode = (typeof ASSIGNMENT_ERROR_CODES)[number];
