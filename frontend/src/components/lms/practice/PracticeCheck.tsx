"use client";

// Phase 10 S3 (PHASE_10_DESIGN 3): "Check" under a practice question: correct / partial / wrong, the key, the explanation.
// Mounted by PlayerShell only when `state.is_practice`; ORT and other attempts never render it.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button } from "@/components/ui";
import { checkPracticeItem, getPracticeFeedback } from "@/lib/lms/practice";
import { isLmsApiError } from "@/lib/lms/client";
import type { PracticeFeedback, StudentQuestion } from "@/lib/lms/attemptTypes";

/** Feedback of the checked items of a practice attempt; loaded once on mount (reload keeps the checks). */
export function usePracticeFeedback(attemptId: string, enabled: boolean) {
  const [fb, setFb] = useState<Record<number, PracticeFeedback>>({});
  const ref = useRef<Record<number, PracticeFeedback>>({});
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    getPracticeFeedback(attemptId)
      .then((r) => {
        if (!alive) return;
        const m: Record<number, PracticeFeedback> = {};
        for (const f of r.items) m[f.position] = f;
        ref.current = { ...m, ...ref.current };
        setFb(ref.current);
      })
      .catch(() => { /* the check button still works; feedback is just not restored */ });
    return () => { alive = false; };
  }, [attemptId, enabled]);
  const add = useCallback((f: PracticeFeedback) => {
    ref.current = { ...ref.current, [f.position]: f };
    setFb(ref.current);
  }, []);
  return { fb, add, lockedRef: ref };
}

const asArr = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : v === null || v === undefined ? [] : [String(v)]);

function entryText(a: unknown): string {
  if (a === null || a === undefined) return "";
  if (typeof a === "object") {
    const o = a as Record<string, unknown>;
    if (o.kind === "range" || ("min" in o && "max" in o)) return `${o.min ?? o.low ?? ""} – ${o.max ?? o.high ?? ""}`;
    if ("value" in o) return o.tolerance ? `${String(o.value)} ± ${String(o.tolerance)}` : String(o.value);
    return JSON.stringify(a);
  }
  return String(a);
}

export function PracticeCheck({ attemptId, position, question, feedback, answered, flush, onChecked }: {
  attemptId: string;
  position: number;
  question: StudentQuestion;
  feedback: PracticeFeedback | undefined;
  /** the student has given an answer (an empty one is refused by the server anyway) */
  answered: boolean;
  /** `queue.flushNow()`: the check scores the stored answer, so it must be saved first. */
  flush: () => Promise<boolean | undefined>;
  onChecked: (f: PracticeFeedback) => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const press = async () => {
    setBusy(true);
    setError(null);
    try {
      if ((await flush()) === false) { setError({ code: "practice_save_failed" }); return; }
      onChecked(await checkPracticeItem(attemptId, position));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (!feedback) {
    const empty = isLmsApiError(error) && error.code === "empty_response";
    return (
      <div className="mt-3">
        <Button onClick={() => void press()} loading={busy} disabled={!answered && !busy}>{t("practice.check")}</Button>
        {!answered && <p className="mt-2 text-xs text-slate-600">{t("practice.answerFirst")}</p>}
        {empty ? <p role="alert" className="mt-2 text-sm text-danger-700">{t("practice.answerFirst")}</p>
          : error && (error as { code?: string }).code === "practice_save_failed" ? <p role="alert" className="mt-2 text-sm text-danger-700">{t("practice.saveFailed")}</p>
          : error ? <ErrorMessage error={error} className="mt-2" /> : null}
      </div>
    );
  }

  const c = feedback.correctness;
  const tone = c === "correct" ? "border-emerald-300 bg-emerald-50 text-emerald-900" : c === "partial" ? "border-amber-300 bg-amber-50 text-amber-900" : "border-red-300 bg-red-50 text-red-900";
  const key = feedback.key ?? {};
  const choices = question.data.choices ?? [];
  const choiceText = (id: string) => choices.find((x) => x.id === id)?.text ?? id;
  let keyLine = "";
  if (Array.isArray(key.answers) && key.answers.length) keyLine = key.answers.map(entryText).join(" ; ");
  else if (typeof key.correct === "boolean") keyLine = key.correct ? t("results.true") : t("results.false");
  else if (key.correct !== undefined && key.correct !== null) {
    keyLine = question.type === "comparison" && typeof key.correct === "string"
      ? t(`bank.types.comparison.labels.${key.correct}`)
      : asArr(key.correct).map(choiceText).join("; ");
  }

  return (
    <div className={`mt-3 rounded-xl border p-4 text-sm ${tone}`} role="status" data-testid="practice-feedback" data-correctness={c}>
      <p className="flex items-center gap-2 font-semibold">
        {c === "correct" ? <Check className="h-4 w-4" aria-hidden="true" /> : <X className="h-4 w-4" aria-hidden="true" />}
        {t(`results.correctness.${c}`)}
      </p>
      {c !== "correct" && keyLine && (
        <p className="mt-2"><span className="font-medium">{t("results.correctAnswer")}: </span>{keyLine}</p>
      )}
      {feedback.explanation && <p className="mt-2 whitespace-pre-line">{feedback.explanation}</p>}
    </div>
  );
}
