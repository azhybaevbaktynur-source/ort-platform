/** Student attempt DTOs (docs/phases/PHASE_3_DESIGN.md sections 3.5-3.9 and 5). snake_case as on the wire. */
import type { Lang } from "./types";
import type { QuestionType, StudentChoiceOut } from "./contentTypes";
import type { AttemptGradeOut } from "./gradingTypes";

export type { AttemptGradeOut };

export type AttemptStatus = "in_progress" | "submitted" | "needs_review" | "graded" | "void";
export type AttemptNavigation = "free" | "section_forward_only";
export type SubmitReason = "manual" | "timeout" | "sweep" | "closed";
export type Correctness = "correct" | "incorrect" | "partial" | "unanswered" | "pending";

/** Per-type response objects stored in `attempt_items.response`. `null` clears the answer. */
export type ItemResponse =
  | { choice_id: string | null }
  | { choice_ids: string[] }
  | { value: boolean | null }
  | { choice: "A" | "B" | "C" | "D" | null }
  | { value: string }
  | { text: string };

export interface AttemptSectionState {
  pos: number;
  started_at: string | null;
  deadline_at: string | null;
  closed_at: string | null;
}

export interface AttemptItemState {
  position: number;
  section_pos: number;
  /** question version id (key into `AttemptContent.questions`); null for unresolved pick slots */
  qv: string | null;
  /** passage version id (key into `AttemptContent.passages`) */
  pv: string | null;
  points: number | string;
  /** choice ids in display order; null when not shuffled */
  choice_order: string[] | null;
  response: Record<string, unknown> | null;
  flagged: boolean;
}

export interface StudentPassage {
  id: string;
  title: string | null;
  body: string;
  image_url: string | null;
}

export interface StudentQuestion {
  id: string;
  type: QuestionType;
  language: Lang;
  stem: string;
  image_url: string | null;
  points?: number | string;
  data: {
    choices?: StudentChoiceOut[];
    shuffle?: boolean;
    column_a?: string;
    column_b?: string;
    word_limit?: number | null;
  };
  passage?: StudentPassage | null;
}

export interface AttemptState {
  id: string;
  assessment_id: string;
  version_id: string;
  status: AttemptStatus;
  language: Lang;
  is_preview: boolean;
  /** ISO UTC; also used to compute the client clock offset */
  server_now: string;
  grace_s: number;
  started_at: string;
  deadline_at: string | null;
  current_section_pos: number;
  navigation: AttemptNavigation;
  sections: AttemptSectionState[];
  items: AttemptItemState[];
  /**
   * Free navigation and previews: the whole-exam payload. Forward-only: the CURRENT section's payload
   * (`/attempts/{t}/content?section={pos}`); it changes when the section advances (review finding 7).
   */
  content_url: string;
  content_etag: string;
  /** pick items: fragments not present in the shared payload, keyed by qv (forward-only: sections up to the current one) */
  extra_questions?: Record<string, StudentQuestion>;
  results_available: boolean;
}

export interface ContentSection {
  pos: number;
  key: string | null;
  title: string | null;
  instructions: string | null;
  time_limit_s: number | null;
  item_count: number;
}

/**
 * Shared payload from GET /attempts/{t}/content (same for every student of a version+language[+section]).
 * `sections` always lists every section; `questions`/`passages` are one section's when `section_pos` is set.
 */
export interface AttemptContent {
  version_id: string;
  language: Lang;
  /** set when the payload holds one section only (forward-only navigation) */
  section_pos?: number;
  sections: ContentSection[];
  questions: Record<string, StudentQuestion>;
  passages: Record<string, StudentPassage>;
  image_urls: string[];
}

export interface AnswerIn {
  position: number;
  response?: Record<string, unknown> | null;
  flagged?: boolean;
  client_ts: number;
}

export interface SaveOut {
  saved: number[];
  stale: number[];
  server_now: string;
  status: AttemptStatus;
  current_section_pos: number;
}

export interface SubmitIn {
  answers?: AnswerIn[];
}

export interface AttemptResultSection {
  pos: number;
  key: string | null;
  raw: number | string;
  possible: number | string;
  answered: number;
  correct: number;
}

export interface AttemptResultOut {
  raw_score: number | string;
  points_possible: number | string;
  sections: AttemptResultSection[];
  pending_review: number;
  submitted_at: string | null;
  /** Phase 4: server-sent grade, only when visible to the student (previews: computed inline). */
  grade?: AttemptGradeOut | null;
}

/** Why a submit-body answer was not stored (B2). Autosave error codes plus `deadline` and `already_submitted`. */
export type SubmitRejectReason =
  | "deadline"
  | "already_submitted"
  | "attempt_closed"
  | "section_closed"
  | "stale"
  | "item_not_found"
  | "invalid_response"
  | "too_many_answers";

export interface RejectedAnswer {
  position: number;
  reason: SubmitRejectReason;
}

export interface SubmitOut {
  status: AttemptStatus;
  submitted_at: string | null;
  results_available: boolean;
  already_submitted?: boolean;
  result?: AttemptResultOut | null;
  /** Positions from the submit body that were stored (absent on older servers). */
  saved?: number[];
  /** Submit-body answers that were NOT stored, with the reason. */
  rejected?: RejectedAnswer[];
}

export interface StartIn {
  language?: Lang;
}

export interface MyAttemptOut {
  id: string;
  attempt_no: number | null;
  status: AttemptStatus;
  started_at: string;
  submitted_at: string | null;
  results_available: boolean;
  result?: AttemptResultOut | null;
  grade?: AttemptGradeOut | null;
}

/** Review/result DTOs for F3 (shape per section 3.9; fields beyond these may be added by A4). */
export interface ReviewItemOut {
  position: number;
  section_pos: number;
  question: StudentQuestion;
  passage?: StudentPassage | null;
  response: Record<string, unknown> | null;
  flagged: boolean;
  correctness: Correctness | null;
  score: number | string | null;
  /** maximum points of the slot */
  points?: number | string | null;
  feedback?: string | null;
  key?: Record<string, unknown> | null;
  explanation?: string | null;
}
export interface ReviewOut {
  items: ReviewItemOut[];
}
