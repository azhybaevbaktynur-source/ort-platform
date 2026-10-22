// TypeScript mirrors of the Phase 2 content API (docs/phases/PHASE_2_DESIGN.md sections 2, 3.4 and 5).
// Shared by the bank/editor UI (C6) and the import UI (C7).
import type { Lang } from "./types";

export type QuestionType =
  | "single_choice"
  | "multiple_answers"
  | "true_false"
  | "comparison"
  | "numeric"
  | "short_text"
  | "essay";
export const QUESTION_TYPES: QuestionType[] = [
  "single_choice", "multiple_answers", "true_false", "comparison", "numeric", "short_text", "essay",
];
export type Difficulty = "easy" | "medium" | "hard";
export const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];
export type VersionOrigin = "create" | "edit" | "import" | "revert";
export type MoveDirection = "up" | "down";

/** Known ORT section codes (labels: i18n `sections.*`). Sections are free labels in general mode. */
export const ORT_SECTIONS = [
  "math_1", "math_2", "analogies", "reading", "grammar",
  "chemistry", "biology", "physics", "history", "english",
] as const;

/** Image as the staff API returns it: expanded with a ready URL. */
export interface ImageOut {
  asset_id: string;
  url: string;
  sha256?: string;
}

// ---- Per-type `data` payloads (staff view: includes the key and expanded image refs) ----
export interface ChoiceData {
  id: string;
  text: string;
  image?: ImageOut | null;
}
/** Editor-side choice: image is sent back as `image_asset_id`. */
export interface ChoiceIn {
  id: string;
  text: string;
  image_asset_id?: string | null;
}
export interface SingleChoiceData {
  choices: ChoiceData[];
  correct: string;
  shuffle: boolean;
}
export interface MultipleAnswersData {
  choices: ChoiceData[];
  correct: string[];
  shuffle: boolean;
  scoring: "all_or_nothing" | "partial";
}
export interface TrueFalseData {
  correct: boolean;
}
export type ComparisonChoice = "A" | "B" | "C" | "D";
export interface ComparisonData {
  column_a: string;
  column_b: string;
  correct: ComparisonChoice;
}
export type NumericAnswer =
  | { kind: "exact"; value: string; margin: string }
  | { kind: "range"; min: string; max: string };
export interface NumericData {
  answers: NumericAnswer[];
}
export interface ShortTextData {
  answers: string[];
  case_sensitive: boolean;
}
export interface EssayData {
  word_limit: number | null;
  rubric_note: string | null;
}

export type QuestionData =
  | SingleChoiceData
  | MultipleAnswersData
  | TrueFalseData
  | ComparisonData
  | NumericData
  | ShortTextData
  | EssayData;

/** Request-side data: choice images are referenced by asset id. */
export type QuestionDataIn =
  | { choices: ChoiceIn[]; correct: string; shuffle: boolean }
  | { choices: ChoiceIn[]; correct: string[]; shuffle: boolean; scoring: "all_or_nothing" | "partial" }
  | TrueFalseData
  | ComparisonData
  | NumericData
  | ShortTextData
  | EssayData;

// ---- Banks ----
export interface BankOut {
  id: string;
  title: string;
  description: string | null;
  source_id: string | null;
  default_language: Lang | null;
  question_count: number;
  passage_count: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}
export interface BankCreateIn {
  title: string;
  description?: string | null;
  default_language?: Lang | null;
}
export interface BankUpdateIn {
  title?: string;
  description?: string | null;
  default_language?: Lang | null;
}

// ---- Questions ----
export interface QuestionSummaryOut {
  id: string;
  bank_id: string;
  type: QuestionType;
  language: Lang;
  topic: string | null;
  difficulty: Difficulty | null;
  section: string | null;
  tags: string[];
  position: number;
  q_num: string | null;
  stem_excerpt: string;
  has_image: boolean;
  passage_id: string | null;
  translation_group_id: string | null;
  version_no: number;
  updated_at: string;
  deleted_at: string | null;
}

export interface VersionSummaryOut {
  id: string;
  version_no: number;
  type: QuestionType;
  origin: VersionOrigin;
  created_at: string;
  created_by_name: string | null;
}
export interface VersionOut {
  id: string;
  version_no: number;
  type: QuestionType;
  language: Lang;
  stem: string;
  data: QuestionData;
  explanation: string | null;
  default_points: number | string;
  image: ImageOut | null;
  origin: VersionOrigin;
  created_at: string;
  created_by_name: string | null;
}

export interface TranslationRef {
  question_id: string;
  language: Lang;
  bank_id: string;
}

export interface QuestionStaffOut extends QuestionSummaryOut {
  current_version: VersionOut;
  passage?: PassageSummaryOut | null;
  translations: TranslationRef[];
  /** Present on PATCH responses. */
  unchanged?: boolean;
}

export interface QuestionContentIn {
  type: QuestionType;
  stem: string;
  data: QuestionDataIn;
  explanation?: string | null;
  default_points: number;
  image_asset_id?: string | null;
}
export interface QuestionMetaIn {
  topic?: string | null;
  difficulty?: Difficulty | null;
  section?: string | null;
  tags?: string[];
  passage_id?: string | null;
}
export interface QuestionCreateIn extends QuestionContentIn, QuestionMetaIn {
  language: Lang;
  tags?: string[];
}
export interface QuestionUpdateIn {
  base_version_id?: string;
  content?: QuestionContentIn;
  meta?: QuestionMetaIn;
}
export interface RevertIn {
  base_version_id: string;
}

export interface QuestionListParams {
  q?: string;
  type?: QuestionType | "";
  language?: Lang | "";
  section?: string;
  topic?: string;
  difficulty?: Difficulty | "";
  tag?: string;
  passage_id?: string;
  deleted?: boolean;
  cursor?: string | null;
  limit?: number;
}

// ---- Preview (student view of a version) ----
export interface StudentPassageOut {
  id: string;
  title: string | null;
  body: string;
  image_url: string | null;
}
export interface StudentChoiceOut {
  id: string;
  text: string;
  image_url?: string | null;
}
export interface StudentQuestionOut {
  id: string;
  type: QuestionType;
  language: Lang;
  stem: string;
  image_url: string | null;
  points?: number | string;
  /** choices/shuffle for choice types, column_a/column_b for comparison, word_limit for essay, {} otherwise. */
  data: {
    choices?: StudentChoiceOut[];
    shuffle?: boolean;
    column_a?: string;
    column_b?: string;
    word_limit?: number | null;
  };
  passage?: StudentPassageOut | null;
}

// ---- Translations ----
export interface TranslationCreateIn {
  language: Lang;
  bank_id?: string | null;
}
export interface TranslationLinkIn {
  question_id: string;
}

// ---- Passages ----
export interface PassageSummaryOut {
  id: string;
  language: Lang;
  title: string | null;
  body_excerpt: string;
  question_count: number;
  version_no: number;
  updated_at: string;
  deleted_at: string | null;
}
export interface PassageVersionOut {
  id: string;
  version_no: number;
  language: Lang;
  title: string | null;
  body: string;
  image: ImageOut | null;
  origin: VersionOrigin;
  created_at: string;
  created_by_name: string | null;
}
export interface PassageVersionSummaryOut {
  id: string;
  version_no: number;
  origin: VersionOrigin;
  created_at: string;
  created_by_name: string | null;
}
export interface PassageOut extends PassageSummaryOut {
  bank_id?: string;
  current_version: PassageVersionOut;
  questions: QuestionSummaryOut[];
}
export interface PassageCreateIn {
  language: Lang;
  title?: string | null;
  body: string;
  image_asset_id?: string | null;
}
export interface PassageUpdateIn {
  base_version_id: string;
  title?: string | null;
  body: string;
  image_asset_id?: string | null;
}

// ---- Assets ----
export interface AssetOut {
  id: string;
  url?: string | null;
  visibility?: "public" | "private";
  mime: string;
  bytes: number;
  width: number | null;
  height: number | null;
  sha256: string;
  original_filename: string | null;
  created_at: string;
  deduplicated?: boolean;
}

/** New `lms.errors.*` codes introduced by Phase 2 (keys exist in en/ky/ru). */
export const CONTENT_ERROR_CODES = [
  "bank_not_found", "question_not_found", "passage_not_found", "version_not_found", "asset_not_found",
  "version_conflict", "invalid_question_data", "unsupported_type", "asset_not_usable", "image_invalid",
  "image_too_large", "image_too_many_pixels", "storage_quota_exceeded", "storage_full",
  "language_not_in_course", "translation_language_taken", "translation_scope_mismatch",
  "translation_type_mismatch", "source_conflict", "bank_deleted", "passage_in_use", "invalid_move",
  "import_busy", "file_too_large",
] as const;
export type ContentErrorCode = (typeof CONTENT_ERROR_CODES)[number];
