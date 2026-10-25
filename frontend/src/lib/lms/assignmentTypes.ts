// Phase 7a S5: TypeScript mirrors of the assignments API (docs/phases/PHASE_7A_DESIGN.md sections 2 and 4).
// snake_case as on the wire. Decimal columns may arrive as strings (`Num`). Phase 7a S6: reconciled field by field with
// backend/app/lms/assignments/schemas.py and grading/serializers.py (the backend is the source of truth).
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

/** Counts on staff payloads (`AssignmentCountsOut`): students with work in, hand-ins without a grade, graded, released. */
export interface AssignmentCounts {
  submitted: number;
  needs_grading: number;
  graded: number;
  released: number;
}

/** Brief of the linked assessment on a quiz assignment (staff, `AssessmentBriefOut`). */
export interface AssignmentAssessmentBrief {
  id: string;
  preset: AssessmentPreset;
  status: AssessmentStatus;
  draft_rev: number;
  allowed_attempts: number;
  has_unpublished_changes: boolean;
  has_access_code: boolean;
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
  counts: AssignmentCounts;
}

export interface AssignmentStaffOut extends AssignmentStaffSummaryOut {
  description: LocalizedText | null;
  assessment: AssignmentAssessmentBrief | null;
  rubric: RubricCriterionOut[];
  rubric_total: Num;
  warnings: Record<string, unknown>[];
}

/** Own released grade on a student payload (`StudentGradeOut`). `points` = the effective points. */
export interface AssignmentGradeOut {
  points: Num | null;
  points_possible: Num | null;
  late_deduction: Num;
  display_value: Num | null;
  label: string | null;
  passed: boolean | null;
  excused: boolean;
  feedback_text: string | null;
  feedback_asset_id: string | null;
  /** the grade row id (hand-in and feedback file downloads) */
  submission_id: string;
  rubric_scores: { criterion_id: string; points: Num; comment: string | null }[];
  released_at: string;
}

/** One hand-in (append-only; section 2.2). */
export interface HandInOut {
  id: string;
  /** the grade row id (download route) */
  submission_id: string;
  attempt_no: number;
  kind: "text" | "file";
  body_text: string | null;
  asset_id: string | null;
  filename: string | null;
  bytes: number | null;
  mime: string | null;
  submitted_at: string;
  late_seconds: number;
  late: boolean;
}

/** Hand-in limits on the student detail (`HandInLimitsOut`). */
export interface HandInLimitsOut {
  text_max_chars: number;
  pdf_max_bytes: number;
  image_max_bytes: number;
  max_file_hand_ins: number;
  accepted_mimes: string[];
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
  position: number;
  /** latest hand-in */
  submitted_at?: string | null;
  late?: boolean;
}

export interface AssignmentStudentDetailOut extends AssignmentStudentOut {
  description: LocalizedText | null;
  rubric: RubricCriterionOut[];
  hand_ins: HandInOut[];
  /** released grade only, with the feedback */
  grade: AssignmentGradeOut | null;
  can_hand_in: boolean;
  /** why not: not_open_yet | closed | already_graded | limit_reached | course_not_active ... */
  reason: string | null;
  limits: HandInLimitsOut | null;
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
  /** quiz only: the assessment's draft_rev for the delegated builder update */
  draft_rev?: number;
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
  filename: string | null;
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

/** `GET /courses/{c}/assignments/{a}/submissions` (`AssignmentSubmissionsPageOut`): `rows`, not `items`. */
export interface AssignmentSubmissionsPageOut {
  rows: AssignmentSubmissionRowOut[];
  next_cursor: string | null;
}

export interface RubricScoreOut {
  criterion_id: string;
  points: Num;
  comment: string | null;
  title?: LocalizedText | null;
  max_points?: Num | null;
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
  // Phase 7a S6: every remaining code of assignments/**, accommodations/** and the manual grade path
  "access_code_format", "body_text_empty", "body_text_too_long", "course_storage_full", "enrollment_not_found",
  "file_already_handed_in", "file_invalid", "grade_release_auto", "hand_in_kind_mismatch", "hand_in_not_accepted",
  "hand_in_limit_reached", "rubric_criteria_mismatch", "window_invalid", "criterion_duplicate", "criterion_not_found",
  "points_possible_required", "preset_template_exclusive", "rubric_not_for_quiz", "too_many_criteria",
] as const;
export type AssignmentErrorCode = (typeof ASSIGNMENT_ERROR_CODES)[number];
