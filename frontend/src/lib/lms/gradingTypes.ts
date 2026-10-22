// TypeScript mirrors of the Phase 4 grading API (docs/phases/PHASE_4_DESIGN.md sections 3.1, 5 and 6).
// Single source of truth for F1 (schemes), F2 (settings), F3 (gradebook) and F4 (results, my grades).
// snake_case as on the wire. Numbers stored as Numeric on the server may arrive as strings: `Num`.
import type { LocalizedText } from "./types";
import type { AttemptStatus } from "./attemptTypes";
import type { ScorePolicy } from "./assessmentTypes";

/** Decimal on the wire (Pydantic Decimal serializes as a string; ints may come as numbers). */
export type Num = number | string;

// ---------------------------------------------------------------------------
// 3.1 Scheme types and params
// ---------------------------------------------------------------------------

export type SchemeType = "points" | "percent" | "bands" | "pass_fail" | "piecewise_curve" | "lookup_table";
export const SCHEME_TYPES: SchemeType[] = ["points", "percent", "bands", "pass_fail", "piecewise_curve", "lookup_table"];

export type RoundingMode = "half_even" | "half_up" | "floor" | "ceil";
export const ROUNDING_MODES: RoundingMode[] = ["half_up", "half_even", "floor", "ceil"];

export interface RoundingParams {
  mode: RoundingMode;
  /** 0..2 */
  decimals: number;
}

export interface PercentileParams {
  mean: number;
  sd: number;
  min: number;
  max: number;
  decimals: number;
}

export interface ThresholdParams {
  key: string;
  min_value: number;
}

export interface ZeroRawParams {
  value: number;
  /** optional on the server (null/absent = no percentile for a zero raw) */
  percentile?: number | null;
}

/** Optional blocks shared by every type (P4-3). */
export interface CommonParams {
  schema: 1;
  rounding?: RoundingParams | null;
  percentile?: PercentileParams | null;
  thresholds?: ThresholdParams[] | null;
  zero_raw?: ZeroRawParams | null;
  apply_to_sections?: boolean;
}

export interface PointsParams extends CommonParams {
  pass_threshold_percent?: number | null;
}

export interface PercentParams extends CommonParams {
  pass_threshold_percent?: number | null;
}

export interface Band {
  /** <= 32 chars, unique */
  key: string;
  /** strictly descending across bands; the last band is 0 */
  min_percent: number;
  /** <= 60 chars per language */
  label: LocalizedText;
  passed: boolean;
}

export interface BandsParams extends CommonParams {
  bands: Band[];
}

export interface PassFailParams extends CommonParams {
  pass_threshold_percent: number;
}

export interface CurveSegment {
  from_ratio: number;
  to_ratio: number;
  from_value: number;
  to_value: number;
  exponent: number;
}

export interface CurveParams extends CommonParams {
  scale_min: number;
  scale_max: number;
  /** contiguous from 0 to 1 */
  segments: CurveSegment[];
  pass_threshold_percent?: number | null;
}

export interface LookupRow {
  raw_from: number;
  raw_to: number;
  value: number;
  label?: string | null;
}

/** No `scale_min`/`scale_max` here: the server derives the scale from the row values and rejects unknown keys. */
export interface LookupTableParams extends CommonParams {
  /** sorted, non-overlapping, covering 0..expected_possible */
  rows: LookupRow[];
  expected_possible?: number | null;
  pass_threshold_percent?: number | null;
}

export interface SchemeParamsByType {
  points: PointsParams;
  percent: PercentParams;
  bands: BandsParams;
  pass_fail: PassFailParams;
  piecewise_curve: CurveParams;
  lookup_table: LookupTableParams;
}
export type SchemeParams = SchemeParamsByType[SchemeType];

/** Labels `pass_fail` produces (i18n `schemes.labels.*` / `grading.labels.*`). */
export type PassFailLabel = "pass" | "fail";
/** Known threshold keys with UI labels; any other key is shown as-is. */
export const KNOWN_THRESHOLD_KEYS = ["golden_certificate"] as const;

// ---------------------------------------------------------------------------
// 5. Scheme library (/grading-schemes)
// ---------------------------------------------------------------------------

/** System scheme keys (P4-6). */
export type SystemSchemeKey = "ort_main" | "ort_subject" | "percent" | "pass_fail";

export interface SchemeVersionBrief {
  id: string;
  version_no: number;
  scale_min: Num | null;
  scale_max: Num | null;
  created_at: string;
}

export interface SchemeSummaryOut {
  id: string;
  key: SystemSchemeKey | (string & {}) | null;
  title: LocalizedText;
  type: SchemeType;
  is_system: boolean;
  is_mine: boolean;
  current_version: SchemeVersionBrief | null;
  deleted_at: string | null;
}

export interface SchemeVersionOut {
  id: string;
  version_no: number;
  type: SchemeType;
  scale_min: Num | null;
  scale_max: Num | null;
  params: SchemeParams;
  /**
   * Label key -> display text. Bands: band key -> LocalizedText. Lookup tables: label -> the same plain string.
   * Pass/fail: empty (labels come from i18n). Render with `labelText()` (components/lms/grading/schemes/labels.ts).
   */
  labels: Record<string, SchemeLabelValue>;
  created_at: string;
  in_use_count: number;
}

/** A value of `SchemeVersionOut.labels`: plain string (lookup_table) or localized text (bands). */
export type SchemeLabelValue = string | LocalizedText;

export interface SchemeOut extends SchemeSummaryOut {
  versions: SchemeVersionOut[];
}

export interface SchemeCreateIn {
  title: LocalizedText;
  type: SchemeType;
  params: SchemeParams;
}

export interface SchemeTitleIn {
  title: LocalizedText;
}

export interface SchemeVersionIn {
  params: SchemeParams;
}

export interface SchemePreviewIn {
  type: SchemeType;
  params: SchemeParams;
  possible: Num;
  /** required; <= 1001 values (the server has no `step`: a step list is expanded by the client) */
  raws: Num[];
}

export interface GradeValueOut {
  display_value: Num | null;
  label: string | null;
  percentile: Num | null;
  passed: boolean | null;
  thresholds: Record<string, boolean>;
}

export interface SchemePreviewRow extends GradeValueOut {
  raw: Num;
}

export interface SchemePreviewOut {
  rows: SchemePreviewRow[];
}

/** `details` of 422 `scheme_params_invalid`. */
export interface SchemeParamsInvalidDetails {
  errors?: { loc?: (string | number)[]; msg?: string; type?: string }[];
}

// ---------------------------------------------------------------------------
// 3.3 / 5. Course and assessment grading settings
// ---------------------------------------------------------------------------

/** Scheme brief on staff payloads (AssessmentStaffOut.scheme, CourseGradingOut.scheme for staff). */
export interface SchemeVersionRef {
  id: string;
  scheme_id: string;
  title: LocalizedText;
  type: SchemeType;
  version_no: number;
  scale_min: Num | null;
  scale_max: Num | null;
  /** the version's label map (band key -> localized text, lookup label -> text); absent on older payloads */
  labels?: Record<string, SchemeLabelValue> | null;
}

/** Scheme brief on student payloads (lobby, course grading GET for students, my grades). */
export interface SchemeStudentRef {
  type: SchemeType;
  scale_min: Num | null;
  scale_max: Num | null;
  title: LocalizedText;
  /** the version's label map (band key -> localized text, lookup label -> text); absent on older payloads */
  labels?: Record<string, SchemeLabelValue> | null;
}

export type GradeRelease = "auto" | "manual";
export const GRADE_RELEASES: GradeRelease[] = ["auto", "manual"];
export type TotalMode = "points" | "weighted";
export const TOTAL_MODES: TotalMode[] = ["points", "weighted"];

/** Assessment fields added by Phase 4 (AssessmentStaffOut / AssessmentUpdateIn, owned by F2). */
export interface AssessmentGradingFields {
  grading_scheme_version_id: string | null;
  grade_category_id: string | null;
  due_at: string | null;
  grade_release: GradeRelease;
  omit_from_total: boolean;
  scheme: SchemeVersionRef | null;
}
export interface AssessmentGradingUpdate {
  grading_scheme_version_id?: string | null;
  grade_category_id?: string | null;
  due_at?: string | null;
  grade_release?: GradeRelease;
  omit_from_total?: boolean;
}

export interface LatePolicy {
  /** 0..100 */
  percent_per_day: number;
  /** 0..100 */
  max_percent: number;
  /** 0..1440 */
  grace_minutes: number;
}

export interface CategoryOut {
  id: string;
  title: LocalizedText;
  weight: Num;
  position: number;
  assessment_count: number;
}

export type CourseGradingWarning =
  | "uncategorized_excluded" | "weights_all_zero" | "points_possible_mismatch" | (string & {});

export interface CourseGradingStaffOut {
  total_mode: TotalMode;
  grading_scheme_version_id?: string | null;
  scheme: SchemeVersionRef | null;
  late_policy: LatePolicy | null;
  categories: CategoryOut[];
  warnings: CourseGradingWarning[];
  grading_changed_at?: string | null;
}

export interface CourseGradingStudentOut {
  total_mode: TotalMode;
  scheme?: SchemeStudentRef | null;
}

/** GET /courses/{c}/grading returns the staff or the student shape. */
export type CourseGradingOut = CourseGradingStaffOut | CourseGradingStudentOut;
export function isStaffCourseGrading(g: CourseGradingOut): g is CourseGradingStaffOut {
  return "categories" in g;
}

export interface CourseGradingIn {
  total_mode: TotalMode;
  grading_scheme_version_id?: string | null;
  late_policy?: LatePolicy | null;
}

export interface CategoryIn {
  title: LocalizedText;
  weight: number;
}

export interface CategoryOrderIn {
  category_ids: string[];
}

// ---------------------------------------------------------------------------
// 5. Gradebook, submissions, actions
// ---------------------------------------------------------------------------

export type SubmissionState = "pending_review" | "graded" | "excused" | "no_attempts";

export type GbAssessmentWarning = "points_possible_mismatch" | "uncategorized_excluded" | (string & {});

export interface GbAssessmentOut {
  id: string;
  title: LocalizedText;
  points_possible: Num | null;
  category_id: string | null;
  omit_from_total: boolean;
  grade_release: GradeRelease;
  due_at: string | null;
  scheme: SchemeVersionRef | null;
  score_policy: ScorePolicy;
  submission_count: number;
  released_count: number;
  stale_count: number;
  warnings: GbAssessmentWarning[];
}

export interface CellOut {
  submission_id: string;
  state: SubmissionState;
  kept_attempt_id: string | null;
  attempts_counted: number;
  raw_points: Num | null;
  points_possible: Num | null;
  late_deduction: Num;
  override_points: Num | null;
  has_override: boolean;
  effective_points: Num | null;
  display_value: Num | null;
  label: string | null;
  percentile: Num | null;
  passed: boolean | null;
  thresholds: Record<string, boolean> | null;
  released_at: string | null;
  /** optimistic token for override/excuse */
  version: number;
}

export interface TotalsOut {
  current_percent: Num | null;
  final_percent: Num | null;
  display_value: Num | null;
  label: string | null;
  passed: boolean | null;
  warnings: CourseGradingWarning[];
}

export interface GbRowOut {
  enrollment_id: string;
  user_id: string;
  student_name: string | null;
  /** keyed by assessment id; absent = no submission */
  cells: Record<string, CellOut>;
  total: TotalsOut;
}

export interface GradebookPageOut {
  assessments: GbAssessmentOut[];
  rows: GbRowOut[];
  next_cursor: string | null;
}

export interface GradebookQuery {
  cursor?: string | null;
  /** <= 50 */
  limit?: number;
  assessment_ids?: string[];
}

/** Per-attempt grade (attempt_grades row) on result and staff payloads (slice G3). */
export interface AttemptGradeSectionOut {
  pos: number;
  display_value: Num | null;
}

export interface AttemptGradeOut {
  scheme_type: SchemeType;
  scale_min: Num | null;
  scale_max: Num | null;
  display_value: Num | null;
  label: string | null;
  percentile: Num | null;
  passed: boolean | null;
  thresholds: Record<string, boolean> | null;
  sections: AttemptGradeSectionOut[] | null;
  is_kept: boolean;
  released: boolean;
  /** `{label: text}` when the scheme version defines a text for `label` (band / lookup label), else {} */
  labels?: Record<string, SchemeLabelValue> | null;
}

export interface SubmissionAttemptOut {
  id: string;
  attempt_no: number | null;
  status: AttemptStatus;
  raw_score: Num | null;
  points_possible: Num | null;
  submitted_at: string | null;
  late_seconds: number;
  grade: AttemptGradeOut | null;
}

export type GradeEventType =
  | "override" | "override_cleared" | "excused" | "unexcused" | "released" | "unreleased" | "regraded" | "attempt_voided";
export const GRADE_EVENT_TYPES: GradeEventType[] = [
  "override", "override_cleared", "excused", "unexcused", "released", "unreleased", "regraded", "attempt_voided",
];

export interface GradeEventOut {
  id: string;
  event: GradeEventType;
  actor_name: string | null;
  attempt_id: string | null;
  old: Record<string, unknown> | null;
  new: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

export interface SubmissionStaffOut extends CellOut {
  override_reason: string | null;
  override_by_name: string | null;
  override_at: string | null;
  attempts: SubmissionAttemptOut[];
  events: GradeEventOut[];
}

export interface OverrideIn {
  /** null clears the override */
  points: number | null;
  /** required (<= 500) when points is set */
  reason?: string | null;
  version: number;
}

export interface ExcuseIn {
  excused: boolean;
  reason?: string | null;
  version: number;
}

export interface ReleaseIn {
  /** omitted = every submission of the assessment; <= 5000 */
  submission_ids?: string[];
}
export interface ReleaseOut {
  released: number;
}
export interface UnreleaseOut {
  unreleased: number;
}

export interface RegradeOut {
  regraded: number;
  /** > 0: call again (UI loops until 0) */
  pending: number;
  scheme_version_id: string | null;
}

export interface VoidAttemptIn {
  /** <= 500 */
  reason: string;
}

// ---------------------------------------------------------------------------
// 5. Student: my grades
// ---------------------------------------------------------------------------

export type MyGradeState = "graded" | "pending" | "missing" | "excused" | "hidden";

export interface MyGradeOut {
  assessment_id: string;
  title: LocalizedText;
  state: MyGradeState;
  display_value?: Num | null;
  label?: string | null;
  percentile?: Num | null;
  passed?: boolean | null;
  thresholds?: Record<string, boolean> | null;
  effective_points?: Num | null;
  points_possible?: Num | null;
  late_deduction?: Num | null;
  released_at?: string | null;
  kept_attempt_id?: string | null;
  due_at?: string | null;
  /** graded rows only: `{label: text}` of the grade's scheme version */
  labels?: Record<string, SchemeLabelValue> | null;
}

export interface MyGradesTotalOut {
  percent: Num | null;
  display_value: Num | null;
  label: string | null;
  passed: boolean | null;
}

export interface MyGradesOut {
  total: MyGradesTotalOut | null;
  scheme?: SchemeStudentRef | null;
  items: MyGradeOut[];
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** New `lms.errors.*` codes introduced by Phase 4 (section 5). */
export const GRADING_ERROR_CODES = [
  "grading_scheme_not_found", "scheme_version_not_found", "scheme_params_invalid", "version_unchanged",
  "submission_not_found", "grade_conflict", "override_reason_required", "category_not_found", "category_in_use",
  "too_many_categories", "too_many_rows", "value_out_of_range", "attempt_in_progress", "already_void",
] as const;
export type GradingErrorCode = (typeof GRADING_ERROR_CODES)[number];
