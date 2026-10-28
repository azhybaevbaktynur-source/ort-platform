import type { Lang } from "@/lib/lms/types";
import type {
  ChoiceData, ComparisonChoice, Difficulty, EssayData, ImageOut, MultipleAnswersData, NumericAnswer, NumericData,
  QuestionContentIn, QuestionMetaIn, QuestionStaffOut, QuestionType, ShortTextData, SingleChoiceData, TrueFalseData,
  ComparisonData, VersionOut,
} from "@/lib/lms/contentTypes";
import type { CardPayload } from "@/lib/lms/quizEditorTypes"; // Phase 7c S3

export interface ChoiceForm { id: string; text: string; image: ImageOut | null }
export interface NumericForm { kind: "exact" | "range"; value: string; margin: string; min: string; max: string }

export interface QuestionForm {
  type: QuestionType;
  language: Lang;
  stem: string;
  explanation: string;
  points: string;
  image: ImageOut | null;
  topic: string;
  section: string;
  difficulty: Difficulty | "";
  tags: string;
  passageId: string;
  // choice types
  choices: ChoiceForm[];
  correctSingle: string;
  correctMulti: string[];
  shuffle: boolean;
  scoring: "all_or_nothing" | "partial";
  // other types
  tf: boolean;
  columnA: string;
  columnB: string;
  compCorrect: ComparisonChoice;
  numeric: NumericForm[];
  shortAnswers: string;
  caseSensitive: boolean;
  wordLimit: string;
  rubric: string;
}

export const CHOICE_LETTERS = "ABCDEFGHIJ".split("");
export const nextChoiceId = (choices: ChoiceForm[]): string =>
  CHOICE_LETTERS.find((l) => !choices.some((c) => c.id === l)) || `C${choices.length + 1}`;

const blankChoices = (): ChoiceForm[] => ["A", "B", "C", "D"].map((id) => ({ id, text: "", image: null }));
export const blankNumeric = (): NumericForm => ({ kind: "exact", value: "", margin: "0", min: "", max: "" });

export function emptyForm(type: QuestionType, language: Lang): QuestionForm {
  return {
    type, language, stem: "", explanation: "", points: "1", image: null,
    topic: "", section: "", difficulty: "", tags: "", passageId: "",
    choices: blankChoices(), correctSingle: "A", correctMulti: [], shuffle: false, scoring: "all_or_nothing",
    tf: true, columnA: "", columnB: "", compCorrect: "A",
    numeric: [blankNumeric()], shortAnswers: "", caseSensitive: false, wordLimit: "", rubric: "",
  };
}

const toChoiceForm = (cs: ChoiceData[]): ChoiceForm[] => cs.map((c) => ({ id: c.id, text: c.text, image: c.image || null }));

export function formFromStaff(q: QuestionStaffOut): QuestionForm {
  const v: VersionOut = q.current_version;
  const f = emptyForm(v.type, v.language);
  f.stem = v.stem;
  f.explanation = v.explanation || "";
  f.points = String(v.default_points ?? 1);
  f.image = v.image;
  f.topic = q.topic || "";
  f.section = q.section || "";
  f.difficulty = q.difficulty || "";
  f.tags = (q.tags || []).join(", ");
  f.passageId = q.passage_id || "";
  switch (v.type) {
    case "single_choice": {
      const d = v.data as SingleChoiceData;
      f.choices = toChoiceForm(d.choices); f.correctSingle = d.correct; f.shuffle = !!d.shuffle;
      break;
    }
    case "multiple_answers": {
      const d = v.data as MultipleAnswersData;
      f.choices = toChoiceForm(d.choices); f.correctMulti = [...d.correct]; f.shuffle = !!d.shuffle; f.scoring = d.scoring;
      break;
    }
    case "true_false": f.tf = (v.data as TrueFalseData).correct; break;
    case "comparison": {
      const d = v.data as ComparisonData;
      f.columnA = d.column_a; f.columnB = d.column_b; f.compCorrect = d.correct;
      break;
    }
    case "numeric": {
      const d = v.data as NumericData;
      f.numeric = d.answers.map((a) => a.kind === "exact"
        ? { ...blankNumeric(), kind: "exact", value: a.value, margin: a.margin ?? "0" }
        : { ...blankNumeric(), kind: "range", min: a.min, max: a.max });
      break;
    }
    case "short_text": {
      const d = v.data as ShortTextData;
      f.shortAnswers = d.answers.join("\n"); f.caseSensitive = !!d.case_sensitive;
      break;
    }
    case "essay": {
      const d = v.data as EssayData;
      f.wordLimit = d.word_limit ? String(d.word_limit) : ""; f.rubric = d.rubric_note || "";
      break;
    }
  }
  return f;
}

const choicesIn = (cs: ChoiceForm[]) => cs.map((c) => ({ id: c.id, text: c.text, image_asset_id: c.image?.asset_id ?? null }));

export function contentFromForm(f: QuestionForm): QuestionContentIn {
  const base = {
    type: f.type, stem: f.stem, explanation: f.explanation.trim() ? f.explanation : null,
    default_points: Number(f.points), image_asset_id: f.image?.asset_id ?? null,
  };
  switch (f.type) {
    case "single_choice":
      return { ...base, data: { choices: choicesIn(f.choices), correct: f.correctSingle, shuffle: f.shuffle } };
    case "multiple_answers":
      return { ...base, data: { choices: choicesIn(f.choices), correct: f.correctMulti, shuffle: f.shuffle, scoring: f.scoring } };
    case "true_false": return { ...base, data: { correct: f.tf } };
    case "comparison": return { ...base, data: { column_a: f.columnA, column_b: f.columnB, correct: f.compCorrect } };
    case "numeric":
      return { ...base, data: { answers: f.numeric.map((n): NumericAnswer => n.kind === "exact"
        ? { kind: "exact", value: n.value.trim(), margin: n.margin.trim() || "0" }
        : { kind: "range", min: n.min.trim(), max: n.max.trim() }) } };
    case "short_text":
      return { ...base, data: { answers: f.shortAnswers.split("\n").map((s) => s.trim()).filter(Boolean), case_sensitive: f.caseSensitive } };
    case "essay": {
      const wl = parseInt(f.wordLimit, 10);
      return { ...base, data: { word_limit: Number.isFinite(wl) && wl > 0 ? wl : null, rubric_note: f.rubric.trim() ? f.rubric : null } };
    }
  }
}

export function metaFromForm(f: QuestionForm): QuestionMetaIn {
  return {
    topic: f.topic.trim() || null,
    difficulty: f.difficulty || null,
    section: f.section.trim() || null,
    tags: f.tags.split(",").map((s) => s.trim()).filter(Boolean).slice(0, 20),
    passage_id: f.passageId || null,
  };
}

/** Light client-side checks; the server stays authoritative. Returns an i18n key or null. */
export function validateForm(f: QuestionForm): string | null {
  const needsStem = f.type !== "comparison";
  if (needsStem && !f.stem.trim()) return "bank.editor.errStem";
  if (!(Number(f.points) >= 0) || f.points.trim() === "") return "bank.editor.errPoints";
  if (f.type === "single_choice" || f.type === "multiple_answers") {
    if (f.choices.length < 2) return "bank.editor.errChoices";
    if (f.choices.some((c) => !c.text.trim() && !c.image)) return "bank.editor.errChoiceEmpty";
    if (f.type === "single_choice" && !f.choices.some((c) => c.id === f.correctSingle)) return "bank.editor.errCorrect";
    if (f.type === "multiple_answers" && f.correctMulti.length === 0) return "bank.editor.errCorrect";
  }
  if (f.type === "comparison" && (!f.columnA.trim() || !f.columnB.trim())) return "bank.editor.errColumns";
  if (f.type === "numeric") {
    if (f.numeric.length === 0) return "bank.editor.errAnswers";
    for (const n of f.numeric) {
      if (n.kind === "exact" && !n.value.trim()) return "bank.editor.errAnswers";
      if (n.kind === "range" && (!n.min.trim() || !n.max.trim())) return "bank.editor.errAnswers";
    }
  }
  if (f.type === "short_text" && f.shortAnswers.split("\n").every((s) => !s.trim())) return "bank.editor.errAnswers";
  return null;
}

// --- Phase 7c S3 begin --- (PHASE_7C_DESIGN 8.4: quiz editor card payloads; pure additions)

/** Draft payload of a quiz card. Half-typed values are allowed (drafts are validated only at "Done"). */
export function payloadFromForm(f: QuestionForm): CardPayload {
  const n = Number(f.points);
  const points = f.points.trim() !== "" && Number.isFinite(n) && n >= 0 && n <= 1000 ? n : 0;
  const content = contentFromForm(f);
  return {
    type: content.type, language: f.language, stem: content.stem, data: content.data as unknown as Record<string, unknown>,
    explanation: content.explanation ?? null, default_points: points, image_asset_id: content.image_asset_id ?? null,
    points, meta: metaFromForm(f),
  };
}

const str = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

/** Form of a draft payload. `imageOf` turns an asset id into an image (its url may be "" when unknown). */
export function formFromPayload(p: CardPayload, imageOf: (assetId: string) => ImageOut | null = () => null): QuestionForm {
  const f = emptyForm(p.type, p.language);
  const d = (p.data || {}) as Record<string, unknown>;
  const img = (id: unknown) => (typeof id === "string" && id ? imageOf(id) : null);
  f.stem = p.stem || "";
  f.explanation = p.explanation || "";
  f.points = String(p.points ?? 1);
  f.image = img(p.image_asset_id);
  f.topic = p.meta?.topic || "";
  f.section = p.meta?.section || "";
  f.difficulty = p.meta?.difficulty || "";
  f.tags = (p.meta?.tags || []).join(", ");
  f.passageId = p.meta?.passage_id || "";
  const choices = arr(d.choices).map((c) => {
    const o = (c || {}) as Record<string, unknown>;
    return { id: str(o.id), text: str(o.text), image: img(o.image_asset_id) };
  }).filter((c) => c.id);
  switch (p.type) {
    case "single_choice":
      if (choices.length) f.choices = choices;
      f.correctSingle = str(d.correct);
      f.shuffle = !!d.shuffle;
      break;
    case "multiple_answers":
      if (choices.length) f.choices = choices;
      f.correctMulti = arr(d.correct).map(str).filter(Boolean);
      f.shuffle = !!d.shuffle;
      f.scoring = d.scoring === "partial" ? "partial" : "all_or_nothing";
      break;
    case "true_false": f.tf = d.correct !== false; break;
    case "comparison":
      f.columnA = str(d.column_a);
      f.columnB = str(d.column_b);
      if (["A", "B", "C", "D"].includes(str(d.correct))) f.compCorrect = str(d.correct) as ComparisonChoice;
      break;
    case "numeric": {
      const answers = arr(d.answers).map((x): NumericForm => {
        const o = (x || {}) as Record<string, unknown>;
        return o.kind === "range"
          ? { ...blankNumeric(), kind: "range", min: str(o.min), max: str(o.max) }
          : { ...blankNumeric(), kind: "exact", value: str(o.value), margin: str(o.margin) || "0" };
      });
      if (answers.length) f.numeric = answers;
      break;
    }
    case "short_text":
      f.shortAnswers = arr(d.answers).map(str).join("\n");
      f.caseSensitive = !!d.case_sensitive;
      break;
    case "essay":
      f.wordLimit = typeof d.word_limit === "number" && d.word_limit > 0 ? String(d.word_limit) : "";
      f.rubric = str(d.rubric_note);
      break;
  }
  return f;
}
// --- Phase 7c S3 end ---
