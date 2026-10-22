"use client";

import React from "react";
import { Check } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import type {
  ComparisonData, EssayData, MultipleAnswersData, NumericData, ShortTextData, SingleChoiceData, TrueFalseData, VersionOut,
} from "@/lib/lms/contentTypes";

/** Staff view of one question version (with the key marked). Used for history comparison. */
export function VersionView({ v }: { v: VersionOut }) {
  const { t } = useTranslation();
  const choiceList = (v.type === "single_choice" || v.type === "multiple_answers")
    ? (v.data as SingleChoiceData | MultipleAnswersData) : null;
  const isCorrect = (id: string) => {
    if (!choiceList) return false;
    const c = (choiceList as { correct: string | string[] }).correct;
    return Array.isArray(c) ? c.includes(id) : c === id;
  };
  return (
    <div className="space-y-3 text-sm">
      {v.stem && <MathRenderer content={v.stem} />}
      {v.image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={v.image.url} alt="" className="max-h-48 w-auto rounded-lg" />
      )}
      {choiceList && (
        <ul className="space-y-1.5">
          {choiceList.choices.map((c) => (
            <li key={c.id} className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 ${isCorrect(c.id) ? "border-emerald-300 bg-emerald-50" : "border-slate-200"}`}>
              <span className="font-bold">{c.id}.</span>
              <div className="flex-1">
                {c.text && <MathRenderer content={c.text} />}
                {c.image && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={c.image.url} alt="" className="mt-1 max-h-24 w-auto rounded" />
                )}
              </div>
              {isCorrect(c.id) && <Check className="h-4 w-4 text-emerald-600" aria-label={t("bank.editor.correct")} />}
            </li>
          ))}
        </ul>
      )}
      {v.type === "true_false" && <p>{t("bank.editor.correct")}: <b>{t((v.data as TrueFalseData).correct ? "bank.editor.true" : "bank.editor.false")}</b></p>}
      {v.type === "comparison" && (() => {
        const d = v.data as ComparisonData;
        return (
          <div className="space-y-1">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 p-2"><b>{t("bank.editor.columnA")}</b><MathRenderer content={d.column_a} /></div>
              <div className="rounded-lg border border-slate-200 p-2"><b>{t("bank.editor.columnB")}</b><MathRenderer content={d.column_b} /></div>
            </div>
            <p>{t("bank.editor.correct")}: <b>{d.correct}. {t(`bank.types.comparison.labels.${d.correct}`)}</b></p>
          </div>
        );
      })()}
      {v.type === "numeric" && (
        <ul className="list-inside list-disc">
          {(v.data as NumericData).answers.map((a, i) => (
            <li key={i}>{a.kind === "exact" ? `${a.value} (±${a.margin})` : `${a.min} ... ${a.max}`}</li>
          ))}
        </ul>
      )}
      {v.type === "short_text" && (
        <ul className="list-inside list-disc">{(v.data as ShortTextData).answers.map((a, i) => <li key={i}>{a}</li>)}</ul>
      )}
      {v.type === "essay" && (v.data as EssayData).word_limit ? <p>{t("bank.preview.wordLimit", { n: (v.data as EssayData).word_limit as number })}</p> : null}
      {v.explanation && (
        <div className="rounded-lg bg-slate-50 p-2">
          <p className="text-xs font-semibold uppercase text-slate-500">{t("bank.editor.explanation")}</p>
          <MathRenderer content={v.explanation} />
        </div>
      )}
      <p className="text-xs text-slate-500">{t("bank.editor.points")}: {String(v.default_points)}</p>
    </div>
  );
}
