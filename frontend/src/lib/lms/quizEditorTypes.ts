// TypeScript mirrors of the Phase 7c quiz editor API (backend/app/lms/quiz_editor/schemas.py, PHASE_7C_DESIGN 5, 6.1).
import type { Lang, LocalizedText } from "./types";
import type { Difficulty, QuestionStaffOut, QuestionType } from "./contentTypes";
import type { ItemOut } from "./assessmentTypes";

export interface CardMeta {
  topic?: string | null;
  difficulty?: Difficulty | null;
  section?: string | null;
  tags?: string[];
  passage_id?: string | null;
}

/** The card's whole form. Drafts accept half-typed content; it is validated only at commit ("Done"). */
export interface CardPayload {
  type: QuestionType;
  language: Lang;
  stem: string;
  data: Record<string, unknown>;
  explanation?: string | null;
  default_points: number;
  image_asset_id?: string | null;
  /** Points of the item in this quiz. */
  points: number;
  meta: CardMeta;
}

export interface DraftOut {
  id: string;
  /** Null for a new card (the question is created on the first valid "Done"). */
  item_id: string | null;
  section_id: string;
  after_item_id: string | null;
  base_version_id: string | null;
  payload: CardPayload;
  draft_rev: number;
  updated_at: string;
  updated_by_name: string | null;
}

export interface DraftCreateIn {
  item_id?: string;
  section_id?: string;
  after_item_id?: string | null;
  payload: CardPayload;
}

export interface DraftUpdateIn {
  draft_rev: number;
  payload: CardPayload;
}

export type EditScope = "all" | "this";
export type CommitApplied = "created" | "in_place" | "all" | "this" | "unchanged";

export interface CommitIn {
  draft_rev: number;
  scope?: EditScope | null;
}

export interface CommitOut {
  item: ItemOut;
  question: QuestionStaffOut;
  applied: CommitApplied;
  version_created: boolean;
}

export interface QuizQuestionCreateIn {
  section_id?: string;
  after_item_id?: string | null;
  payload: CardPayload;
}

export interface UsageAssessmentOut {
  id: string;
  title: LocalizedText;
  status: string;
  is_this: boolean;
}

export interface QuestionUsageOut {
  other_count: number;
  assessments: UsageAssessmentOut[];
  published_anywhere: boolean;
}

/** Details of 409 `scope_required`: the question is used in other quizzes; the teacher picks a scope. */
export interface ScopeRequiredDetails {
  assessment_count: number;
  can_update_all: boolean;
  assessments: UsageAssessmentOut[];
}

/** Details of 409 `draft_conflict` on a card draft: the other tab's state. */
export interface CardDraftConflictDetails {
  draft_rev: number;
  payload: CardPayload;
  updated_by_name: string | null;
}

export interface CopyToBankIn {
  bank_id: string;
  mode: "move" | "copy";
}

/** Error codes of the quiz editor (labels `quizEditor.errors.<code>`). */
export const QUIZ_EDITOR_ERROR_CODES = [
  "draft_conflict", "draft_exists", "draft_not_found", "scope_required", "scope_not_allowed", "passage_child_scope",
  "payload_too_large", "passage_not_in_quiz_bank", "quiz_bank_private",
] as const;
