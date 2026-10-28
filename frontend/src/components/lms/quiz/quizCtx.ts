import type { MutableRefObject } from "react";
import type { AssessmentStaffOut, ItemOut, SectionOut } from "@/lib/lms/assessmentTypes";
import type { CardPayload } from "@/lib/lms/quizEditorTypes";
import type { Lang } from "@/lib/lms/types";
import type { AddItemsTab } from "@/components/lms/assessments/AddItemsDialog";

/** Card keys: `item:<item id>` or `draft:<draft id>` (a new card). */
export const itemKey = (id: string) => `item:${id}`;
export const draftKey = (id: string) => `draft:${id}`;

/** Editor operations the sections and cards call (implemented by QuizEditor). */
export interface QuizOps {
  openKey: string | null;
  /** Closes the open card (committing it when valid) and opens this one. */
  requestOpen: (key: string) => void;
  closed: () => void;
  /** A new card in `section` after `afterItemId` (null: at the end), optionally pre-filled. */
  addQuestion: (section: SectionOut | null, afterItemId: string | null, payload?: CardPayload) => Promise<void>;
  /** Find questions / passage / random group from a shared bank, placed after `afterItemId`. A quiz without sections
   * (S5: an empty quiz) gets its hidden default section first. */
  addFrom: (section: SectionOut | null, afterItemId: string | null, tab: AddItemsTab) => void;
  moveItem: (section: SectionOut, from: number, to: number) => Promise<void>;
  moveChild: (section: SectionOut, parent: ItemOut, from: number, to: number) => Promise<void>;
  moveToSection: (item: ItemOut, sectionId: string) => Promise<void>;
  /** Removes a top-level item and offers "Undo" for 10 s; children are removed without undo. */
  deleteItem: (section: SectionOut, item: ItemOut, index: number, parent?: ItemOut) => Promise<void>;
}

export type CloseMode = "done" | "auto";
/** Closes the open card: commits when valid ("Done"); false keeps it open (errors, a dialog, a conflict). */
export type CardCloser = (mode: CloseMode) => Promise<boolean>;

/** What every part of the quiz editor needs (PHASE_7C_DESIGN 8.3). */
export interface QuizCtx {
  courseId: string;
  a: AssessmentStaffOut;
  canEdit: boolean;
  courseLanguages: Lang[];
  /** Language of a new card: the course default when the quiz offers it, else the quiz's first language. */
  defaultLanguage: Lang;
  reload: () => Promise<void>;
  /** The latest loaded assessment (fresh inside async handlers that started before a reload). */
  current: () => AssessmentStaffOut;
  onError: (e: unknown) => void;
  /** The open card registers its closer here; opening another card or publishing calls it first. */
  closer: MutableRefObject<CardCloser | null>;
}
