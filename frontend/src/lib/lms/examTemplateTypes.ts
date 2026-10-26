// Phase 7b S4: TypeScript mirrors of the exam template API (PHASE_7B_DESIGN 4, 5, 7, 9).
import type { LocalizedText } from "./types";
import type { DisplayMode, PassageDisplay, ResultView } from "./blocks";
import type { Navigation, ResultsPolicy, ScorePolicy } from "./assessmentTypes";

export type ExamTemplateScope = "platform" | "organization" | "teacher";
export const EXAM_TEMPLATE_SCOPES: ExamTemplateScope[] = ["platform", "organization", "teacher"];
export type ExamTemplateStatus = "draft" | "published" | "archived";
export const EXAM_TEMPLATE_STATUSES: ExamTemplateStatus[] = ["draft", "published", "archived"];

/** Spec `lock_scope` keys (`ids.py::LOCK_SCOPE_KEYS`). */
export const LOCK_SCOPE_KEYS = [
  "sections", "section_time_limit_s", "rules", "navigation", "scheme", "result_view", "importer_profile", "display_mode",
] as const;
export type LockScopeKey = (typeof LOCK_SCOPE_KEYS)[number];

// ---- ExamTemplateSpec (EXAM_TEMPLATES_DESIGN 3.1; spec.py) ----
export interface SpecDefaults {
  time_limit_s?: number | null;
  allowed_attempts?: number;
  score_policy?: ScorePolicy;
  results_policy?: ResultsPolicy;
  show_correct_answers?: boolean;
  shuffle_items?: boolean;
  shuffle_choices?: boolean;
}

export interface SpecSection {
  key?: string | null;
  title?: LocalizedText | null;
  instructions?: LocalizedText | null;
  time_limit_s?: number | null;
  min_items?: number | null;
  max_items?: number | null;
  allowed_types: string[];
  allow_passages?: boolean;
  passage_display?: PassageDisplay | null;
}

export interface SpecParameter {
  key: string;
  kind: "choice";
  options: string[];
  binds: string;
}

export interface ExamTemplateSpec {
  schema?: number;
  navigation?: Navigation;
  display_mode?: DisplayMode;
  passage_display?: PassageDisplay | null;
  result_view?: ResultView | null;
  importer_profile?: string | null;
  defaults?: SpecDefaults;
  sections: SpecSection[];
  scoring?: { grading_scheme_version_id: string } | null;
  parameters?: SpecParameter[];
  lock_scope?: LockScopeKey[];
}

// ---- Templates and versions ----
export interface ExamTemplateOut {
  id: string;
  owner_scope: ExamTemplateScope;
  organization_id: string | null;
  organization_name?: string | null;
  title: LocalizedText;
  description: LocalizedText | null;
  status: ExamTemplateStatus;
  locked: boolean;
  current_version_id: string | null;
  current_version_no: number | null;
  /** Management payloads only (never in course pickers). */
  draft_spec?: ExamTemplateSpec | null;
  draft_rev?: number;
  /** The current version's spec, when the payload carries it (picker / detail). */
  current_spec?: ExamTemplateSpec | null;
  created_at: string;
  updated_at: string;
}

export interface ExamTemplateVersionOut {
  id: string;
  template_id: string;
  version_no: number;
  spec: ExamTemplateSpec;
  spec_hash: string;
  grading_scheme_version_id: string | null;
  published_at: string;
}

export interface ExamTemplateCreateIn {
  owner_scope: ExamTemplateScope;
  organization_id?: string | null;
  title: LocalizedText;
  description?: LocalizedText | null;
  draft_spec?: ExamTemplateSpec | null;
}

export interface ExamTemplatePatchIn {
  draft_rev: number;
  title?: LocalizedText;
  description?: LocalizedText | null;
  draft_spec?: ExamTemplateSpec | null;
}

export interface ExamTemplateListParams {
  scope?: ExamTemplateScope;
  organization_id?: string;
  course_id?: string;
  status?: ExamTemplateStatus;
  cursor?: string | null;
  limit?: number;
}

// ---- Block catalog (GET /exam-templates/blocks, design 7) ----
export interface BlockQuestionTypeOut {
  key: string;
  title_key: string;
  supports_passages: boolean;
  import_columns: string[];
}
export interface BlockSchemeVersionOut {
  id: string;
  title: LocalizedText | string;
  type: string;
  scope: "system" | "mine";
}
export interface BlocksOut {
  question_types: BlockQuestionTypeOut[];
  result_views: string[];
  passage_displays: string[];
  display_modes: string[];
  navigations: string[];
  importer_profiles: string[];
  scheme_versions: BlockSchemeVersionOut[];
}

// ---- Import format (design 8) ----
export interface ImportFormatSectionOut {
  key: string | null;
  title: LocalizedText | null;
  position: number;
  allowed_types: string[];
  allow_passages: boolean;
  min_items: number | null;
  max_items: number | null;
  columns: string[];
}
export interface ImportFormatOut {
  template_id: string;
  version_no: number;
  header: string[];
  sections: ImportFormatSectionOut[];
}

// ---- Assessment-bound actions (design 5.5, 9.1) ----
export interface SectionCountsIn {
  position: number;
  min_items?: number | null;
  max_items?: number | null;
}
export interface SaveAsTemplateIn {
  owner_scope: ExamTemplateScope;
  organization_id?: string | null;
  title: LocalizedText;
  description?: LocalizedText | null;
  lock_scope?: LockScopeKey[];
  display_mode?: DisplayMode;
  sections_counts?: SectionCountsIn[];
}

/** Create-from-template fields of `POST /assessments` and of the quiz part of `POST /assignments`. */
export interface TemplateCreateFields {
  exam_template_id?: string;
  exam_template_version_id?: string;
  parameters?: Record<string, string>;
}

/** Error codes of `exam_templates/ids.py` (labels `examTemplates.errors.<code>`). */
export const EXAM_TEMPLATE_ERROR_CODES = [
  "template_not_found", "template_not_published", "template_archived", "spec_invalid", "nothing_to_publish",
  "draft_conflict", "template_locked", "preset_template_exclusive", "preset_not_templatable", "parameter_missing",
  "parameter_invalid", "display_mode_not_available", "importer_profile_reserved", "scheme_not_shareable",
  "template_upgrade_not_allowed", "not_a_template_assessment", "scope_not_allowed",
  "section_not_in_template", "type_not_allowed_in_section", "passage_not_allowed", "type_required",
  "count_below_min", "count_above_max", "attach_target_mismatch", "format_mismatch",
] as const;
export type ExamTemplateErrorCode = (typeof EXAM_TEMPLATE_ERROR_CODES)[number];

/** One `spec_invalid` detail: where (`loc`) and what (`msg`). */
export interface SpecIssue {
  loc: (string | number)[];
  msg: string;
}
