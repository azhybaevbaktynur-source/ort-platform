// TypeScript mirrors of the Phase 3 assessment API (docs/phases/PHASE_3_DESIGN.md sections 1, 3.3 and 5).
// Builder and lobby DTOs only; attempt/player types live in attemptTypes.ts (F2).
import type { Lang, LocalizedText } from "./types";
import type { Difficulty, QuestionType } from "./contentTypes";
import type { AssessmentGradingFields, AssessmentGradingUpdate, SchemeStudentRef } from "./gradingTypes";
import type { DraftOut } from "./quizEditorTypes"; // Phase 7c S3

export type AssessmentPreset = "none" | "ort_main" | "ort_subject";
export const ASSESSMENT_PRESETS: AssessmentPreset[] = ["none", "ort_main", "ort_subject"];
export type AssessmentStatus = "draft" | "published";
export type ScorePolicy = "highest" | "latest" | "first" | "average";
export const SCORE_POLICIES: ScorePolicy[] = ["highest", "latest", "first", "average"];
export type Navigation = "free" | "section_forward_only";
export type ResultsPolicy = "never" | "after_submit" | "after_close";
export const RESULTS_POLICIES: ResultsPolicy[] = ["never", "after_submit", "after_close"];
export type ItemKind = "question" | "passage" | "pick";

/** Subject keys accepted by the ort_subject preset (section keys, labels `sections.*`). */
export const ORT_SUBJECT_KEYS = [
  "chemistry", "biology", "physics", "history", "english", "advanced_math", "native_language",
] as const;

export interface SectionRules {
  allowed_types?: QuestionType[];
  max_items?: number;
  allow_passages?: boolean;
}

export interface PickFilter {
  section?: string;
  topic?: string;
  difficulty?: Difficulty;
  type?: QuestionType;
  tags?: string[];
}

export interface ItemQuestionOut {
  id: string;
  type: QuestionType;
  language: Lang;
  stem_excerpt: string;
  deleted: boolean;
  newer_version_available: boolean;
}

export interface ItemPassageOut {
  id: string;
  title: string | null;
}

export interface ItemPickOut {
  bank_id: string;
  count: number;
  filter: PickFilter;
  pool_size: Partial<Record<Lang, number>>;
}

export interface ItemOut {
  id: string;
  kind: ItemKind;
  position: number;
  points: number | string | null;
  question?: ItemQuestionOut | null;
  passage?: ItemPassageOut | null;
  children?: ItemOut[] | null;
  pick?: ItemPickOut | null;
}

export interface SectionOut {
  id: string;
  position: number;
  key: string | null;
  title: LocalizedText | null;
  instructions: LocalizedText | null;
  time_limit_s: number | null;
  rules: SectionRules;
  items: ItemOut[];
}

export interface AttemptCounts {
  in_progress: number;
  submitted: number;
}

export interface AssessmentStaffSummaryOut {
  id: string;
  title: LocalizedText;
  preset: AssessmentPreset;
  status: AssessmentStatus;
  languages: Lang[];
  item_count: number;
  points_possible: number | string;
  has_unpublished_changes: boolean;
  current_version_no: number | null;
  attempt_counts: AttemptCounts;
  available_from: string | null;
  available_until: string | null;
  deleted_at: string | null;
}

export interface LastResult {
  raw_score: number | string;
  points_possible: number | string;
}

export interface AssessmentStudentSummaryOut {
  id: string;
  title: LocalizedText;
  languages: Lang[];
  time_limit_s: number | null;
  item_count: number;
  available_from: string | null;
  available_until: string | null;
  allowed_attempts: number;
  attempts_used: number;
  in_progress_attempt_id: string | null;
  last_result?: LastResult | null;
  /** Phase 4 */
  due_at?: string | null;
  scheme?: SchemeStudentRef | null;
}

export type AssessmentSummaryOut = AssessmentStaffSummaryOut | AssessmentStudentSummaryOut;

/** Staff `warnings` of GET /assessments/{a}: advisory, never block publishing (labels `assessments.issues.<code>`). */
export interface AssessmentWarning {
  code: "newer_version" | "unresolved_language" | (string & {});
  item_id?: string | null;
  language?: Lang | null;
}

/** Details of the 409 `confirm_required` publish error. */
export interface ConfirmRequiredDetails {
  in_progress: number;
  submitted: number;
}

/** Details of the 409 `draft_conflict` error: the current revision to reload. */
export interface DraftConflictDetails {
  draft_rev: number;
}

/** Student lobby `reason` when `can_start` is false (anything else falls back to the generic message). */
export const LOBBY_REASONS = ["not_open_yet", "closed", "attempts_exhausted", "unpublished", "not_a_student", "course_not_active"] as const; // Phase 6 S4b: last two
export type LobbyReason = (typeof LOBBY_REASONS)[number];

export interface AssessmentStaffOut extends AssessmentStaffSummaryOut, AssessmentGradingFields {
  description: LocalizedText | null;
  draft_rev: number;
  time_limit_s: number | null;
  allowed_attempts: number;
  score_policy: ScorePolicy;
  shuffle_items: boolean;
  shuffle_choices: boolean;
  navigation: Navigation;
  results_policy: ResultsPolicy;
  show_correct_answers: boolean;
  sections: SectionOut[];
  warnings: AssessmentWarning[];
}

export interface LobbySectionOut {
  pos: number;
  key: string | null;
  title: LocalizedText | null;
  time_limit_s: number | null;
  item_count: number;
}

export interface AssessmentLobbyOut {
  id: string;
  title: LocalizedText;
  description: LocalizedText | null;
  languages: Lang[];
  sections: LobbySectionOut[];
  time_limit_s: number | null;
  navigation: Navigation;
  allowed_attempts: number;
  attempts_used: number;
  available_from: string | null;
  available_until: string | null;
  in_progress_attempt_id: string | null;
  can_start: boolean;
  reason?: LobbyReason | (string & {}) | null;
  /** Phase 4 */
  due_at?: string | null;
  scheme?: SchemeStudentRef | null;
}

/** GET /assessments/{a} returns the staff or lobby shape depending on the caller's role. */
export type AssessmentDetailOut = AssessmentStaffOut | AssessmentLobbyOut;
export function isStaffAssessment(a: AssessmentDetailOut): a is AssessmentStaffOut {
  return "draft_rev" in a;
}

export interface AssessmentCreateIn {
  title: LocalizedText;
  description?: LocalizedText | null;
  preset: AssessmentPreset;
  languages: Lang[];
  subject_key?: string;
}

export interface AssessmentUpdateIn extends AssessmentGradingUpdate {
  draft_rev: number;
  title?: LocalizedText;
  description?: LocalizedText | null;
  languages?: Lang[];
  time_limit_s?: number | null;
  allowed_attempts?: number;
  score_policy?: ScorePolicy;
  shuffle_items?: boolean;
  shuffle_choices?: boolean;
  navigation?: Navigation;
  results_policy?: ResultsPolicy;
  show_correct_answers?: boolean;
  available_from?: string | null;
  available_until?: string | null;
  /** Phase 8b: display settings of a general exam (null passage display / result view = inherit from the course). */
  display_mode?: "one_per_page" | "scrolling";
  passage_display?: "plain" | "numbered" | null;
  result_view?: "general" | "ort" | null;
}

export interface SectionIn {
  title?: LocalizedText | null;
  key?: string | null;
  instructions?: LocalizedText | null;
  time_limit_s?: number | null;
  rules?: SectionRules;
}

export interface ItemCreateIn {
  kind: ItemKind;
  question_id?: string;
  passage_id?: string;
  /** Passage children. */
  question_ids?: string[];
  points?: number | null;
  pick?: { bank_id: string; count: number; filter: PickFilter };
}

export interface ItemUpdateIn {
  points?: number | null;
  section_id?: string;
  pick?: { bank_id: string; count: number; filter: PickFilter };
}

export interface BulkAddIn {
  question_ids?: string[];
  bank_id?: string;
  filter?: PickFilter & { q?: string; language?: Lang; passage_id?: string };
  points?: number;
  group_passages?: boolean;
}

export interface BulkAddOut {
  added: number;
  skipped: { question_id: string; code: string }[];
}

export interface ItemsOrderIn {
  item_ids: string[];
  parent_item_id?: string | null;
}

/** Validation / publish issue; codes map to `assessments.issues.<code>`. */
export interface Issue {
  code: string;
  section_pos?: number | null;
  item_id?: string | null;
  language?: Lang | null;
  [k: string]: unknown;
}

export interface ValidationOut {
  errors: Issue[];
  warnings: Issue[];
}

export interface PublishedVersionBrief {
  id: string;
  version_no: number;
  item_count: number;
  points_possible: number | string;
  created_at: string;
}

export interface PublishOut {
  assessment: AssessmentStaffOut;
  version: PublishedVersionBrief;
  unchanged: boolean;
}

export interface VersionOut extends PublishedVersionBrief {
  created_by_name: string | null;
  attempt_counts: AttemptCounts;
}

/** Result of POST .../preview. Full shape is `AttemptStateOut` in attemptTypes.ts (F2); the builder needs the id only. */
export interface PreviewStartOut {
  id?: string;
  attempt_id?: string;
  [k: string]: unknown;
}
export function previewAttemptId(p: PreviewStartOut): string | null {
  if (typeof p.id === "string") return p.id;
  if (typeof p.attempt_id === "string") return p.attempt_id;
  const a = p.attempt as { id?: unknown } | undefined;
  return a && typeof a.id === "string" ? a.id : null;
}

/** New `lms.errors.*` codes introduced by Phase 3 builder/lobby (keys in fragments/F1.*.json). */
export const ASSESSMENT_ERROR_CODES = [
  "assessment_not_found", "section_not_found", "item_not_found", "draft_conflict", "languages_not_in_course",
  "too_many_sections", "too_many_items", "section_not_empty", "order_mismatch", "preset_rule_locked",
  "item_type_not_allowed", "item_language_mismatch", "item_duplicate", "passage_mismatch", "publish_invalid",
  "confirm_required", "not_published", "attempts_in_progress", "assessment_not_available", "attempts_exhausted",
  "language_not_available", "question_not_found", "bank_not_found", "passage_not_found", "not_deleted",
  "not_implemented", "validation_failed", "unsupported_type", "access_code_too_short",
] as const;
export type AssessmentErrorCode = (typeof ASSESSMENT_ERROR_CODES)[number];

/** Issue codes of the publish validator (labels `assessments.issues.<code>`). */
export const ISSUE_CODES = [
  "no_sections", "empty_section", "unresolved_language", "question_deleted", "type_not_allowed", "passage_mismatch",
  "pick_pool_too_small", "section_limit_in_free_navigation", "section_limits_exceed_total", "after_close_needs_until",
  "too_many_items", "languages_not_in_course", "empty_passage", "newer_version",
  "too_few_items", // Phase 7b S4 (P7B-4)
  "unfinished_drafts", // Phase 7c S3 (PHASE_7C_DESIGN 5.8: a warning, publishing still succeeds)
] as const;

// --- Phase 7b S4 begin --- (PHASE_7B_DESIGN 2.3, 2.4, 9.1; interface merging keeps the Phase 3 declarations intact)
export interface SectionRules {
  min_items?: number;
}

/** `exam_template` of a staff assessment created from an exam template (null for blank and preset exams). */
export interface AssessmentExamTemplateRef {
  template_id: string;
  title: LocalizedText;
  version_no: number;
  version_id: string;
  latest_version_no: number | null;
  /** Course-template lock field names fixed by the template (`templates/base.py`), e.g. "navigation". */
  locked_fields: string[];
  /** Phase 7b S6: the template is locked now (the server refuses "Save as template"). */
  template_locked?: boolean;
}

export interface AssessmentStaffOut {
  exam_template?: AssessmentExamTemplateRef | null;
  display_mode?: string;
  passage_display?: string | null;
  result_view?: string | null;
  structure_locked?: boolean;
}

export interface AssessmentCreateIn {
  exam_template_id?: string;
  exam_template_version_id?: string;
  parameters?: Record<string, string>;
}

/** Lock fields of a template exam that are fixed right now (empty for blank and preset exams). */
export function templateLockedFields(a: Pick<AssessmentStaffOut, "exam_template" | "structure_locked">): Set<string> {
  return new Set(a.structure_locked && a.exam_template ? a.exam_template.locked_fields : []);
}
// --- Phase 7b S4 end ---

// --- Phase 7c S3 begin --- (PHASE_7C_DESIGN 6.1: quiz editor fields of the staff assessment; interface merging)
export interface ItemQuestionOut {
  /** `quiz` = the question lives in this quiz's own bank; `shared` = a course bank. */
  bank_kind?: "quiz" | "shared";
  /** Number of other live quizzes of the course that use this question. */
  used_elsewhere?: number;
  /** Phase 7c S5: staff only, the correct answer(s) in one line (true/false: "true" | "false"; essay: null). */
  correct_summary?: string | null;
}

export interface ItemOut {
  /** A card draft exists for this item (only for readers with content.read_admin). */
  has_draft?: boolean;
}

export interface AssessmentStaffOut {
  /** Card drafts of the quiz editor ([] for readers without content.read_admin). */
  drafts?: DraftOut[];
}
// --- Phase 7c S3 end ---
