// Phase 7b S4: building-block catalog, frontend mirror of `backend/app/lms/exam_templates/blocks.py` and the
// question type registry (PHASE_7B_DESIGN 7). `backend/tests/lms/test_blocks_contract.py` parses the literal
// arrays below with a regex and compares them with the backend: keep each array on ONE line, `as const`.
import { lazy, type ComponentType, type LazyExoticComponent } from "react";

type PassageComponent = ComponentType<{ text: string; className?: string }>;
// Lazy: the renderers pull the math renderer (KaTeX); screens that only need the labels stay light.
const NumberedPassage = lazy(() => import("@/components/lms/NumberedPassage").then((m) => ({ default: m.NumberedPassage as PassageComponent })));
const PlainPassage = lazy(() => import("@/components/lms/PlainPassage").then((m) => ({ default: m.PlainPassage as PassageComponent })));

export const RESULT_VIEWS = ["general", "ort"] as const;
export const PASSAGE_DISPLAYS = ["plain", "numbered"] as const;
export const DISPLAY_MODES = ["one_per_page", "scrolling"] as const;
export const NAVIGATIONS = ["free", "section_forward_only"] as const;
export const IMPORTER_PROFILES = ["general", "ort"] as const;
export const QUESTION_TYPES = ["single_choice", "multiple_answers", "true_false", "comparison", "numeric", "short_text", "essay"] as const;

export type ResultView = (typeof RESULT_VIEWS)[number];
export type PassageDisplay = (typeof PASSAGE_DISPLAYS)[number];
export type DisplayMode = (typeof DISPLAY_MODES)[number];
export type BlockNavigation = (typeof NAVIGATIONS)[number];
export type ImporterProfile = (typeof IMPORTER_PROFILES)[number];
export type BlockQuestionType = (typeof QUESTION_TYPES)[number];

/** Display modes a new exam may use today: `scrolling` is accepted in a spec but refused at create until 8b (P7B-1). */
export const AVAILABLE_DISPLAY_MODES: readonly DisplayMode[] = ["one_per_page"];

/** Result views: the i18n label of each (`examTemplates.blocks.resultViews.*`). The result pages pick their own renderer. */
export const resultViews: Record<ResultView, { titleKey: string }> = {
  general: { titleKey: "examTemplates.blocks.resultViews.general" },
  ort: { titleKey: "examTemplates.blocks.resultViews.ort" },
};

/** Passage renderers by `passage_display` (the components the player and the builder already use; render in <Suspense>). */
export const passageRenderers: Record<PassageDisplay, { titleKey: string; Component: LazyExoticComponent<PassageComponent> }> = {
  plain: { titleKey: "examTemplates.blocks.passageDisplays.plain", Component: PlainPassage },
  numbered: { titleKey: "examTemplates.blocks.passageDisplays.numbered", Component: NumberedPassage },
};

/** i18n key of a question type's name (same keys as the backend `QuestionType.title_key`). */
export const questionTypeTitleKey = (type: string): string => `bank.types.${type}.name`;
