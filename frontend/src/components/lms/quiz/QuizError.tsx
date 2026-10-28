"use client";

import React from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { QUIZ_EDITOR_ERROR_CODES } from "@/lib/lms/quizEditorTypes";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";

const KNOWN = new Set<string>(QUIZ_EDITOR_ERROR_CODES);

/** Error box of the quiz editor: Phase 7c codes are translated here, everything else falls through to AssessmentError. */
export function QuizError({ error, onRetry, className = "" }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = (error as { code?: string }).code;
  if (code && KNOWN.has(code)) {
    return (
      <div role="alert" className={`flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 ${className}`}>
        <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <p className="flex-1">{t(`quizEditor.errors.${code}`)}</p>
        {onRetry && <button type="button" onClick={onRetry} className="font-semibold underline">{t("lms.common.retry")}</button>}
      </div>
    );
  }
  return <AssessmentError error={error} onRetry={onRetry} className={className} />;
}

const SKIP = new Set(["body", "payload"]);
const FIELD_KEYS: Record<string, string> = {
  stem: "bank.editor.stem", explanation: "bank.editor.explanation", points: "bank.editor.points",
  default_points: "bank.editor.points", image_asset_id: "bank.editor.image", type: "bank.editor.type",
  language: "bank.editor.language", data: "quizEditor.card.answersField", meta: "quizEditor.card.detailsField",
};

/** Field names of a 422 `details[].loc` list (the card shows them under the form; the draft is kept). */
export function fieldErrorKeys(details: unknown): string[] {
  if (!Array.isArray(details)) return [];
  const keys = new Set<string>();
  for (const d of details) {
    const loc = Array.isArray((d as { loc?: unknown })?.loc) ? ((d as { loc: unknown[] }).loc) : [];
    const first = loc.map(String).find((x) => !SKIP.has(x))?.split(/[.[]/)[0];
    const key = first ? (FIELD_KEYS[first] ?? (["choices", "correct", "answers", "column_a", "column_b"].includes(first) ? FIELD_KEYS.data : null)) : null;
    keys.add(key ?? "quizEditor.card.otherField");
  }
  return Array.from(keys);
}
