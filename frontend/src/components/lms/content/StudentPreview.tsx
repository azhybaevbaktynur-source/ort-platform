"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { TemplatePassage } from "@/components/lms/PlainPassage";
import type { StudentQuestionOut } from "@/lib/lms/contentTypes";

/** Read-only render of the student view (no key). */
export function StudentPreview({ q }: { q: StudentQuestionOut }) {
  const { t } = useTranslation();
  const d = q.data || {};
  return (
    <div className="space-y-4">
      {q.passage && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          {q.passage.title && <h3 className="mb-2 font-semibold text-slate-900">{q.passage.title}</h3>}
          {q.passage.image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={q.passage.image_url} alt="" className="mb-3 max-h-72 w-auto rounded-lg" />
          )}
          <TemplatePassage text={q.passage.body} />
        </div>
      )}
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        {q.stem && <MathRenderer content={q.stem} />}
        {q.image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={q.image_url} alt="" className="mt-3 max-h-80 w-auto rounded-lg" />
        )}
        {q.type === "comparison" && (
          <div className="mt-4 space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 p-3">
                <p className="mb-1 text-xs font-bold uppercase text-slate-500">{t("bank.editor.columnA")}</p>
                <MathRenderer content={d.column_a || ""} />
              </div>
              <div className="rounded-xl border border-slate-200 p-3">
                <p className="mb-1 text-xs font-bold uppercase text-slate-500">{t("bank.editor.columnB")}</p>
                <MathRenderer content={d.column_b || ""} />
              </div>
            </div>
            <ul className="space-y-2">
              {(["A", "B", "C", "D"] as const).map((k) => (
                <li key={k} className="flex items-center gap-3 rounded-xl border border-slate-200 px-3 py-2 text-sm">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-100 text-xs font-bold">{k}</span>
                  {t(`bank.types.comparison.labels.${k}`)}
                </li>
              ))}
            </ul>
          </div>
        )}
        {(q.type === "single_choice" || q.type === "multiple_answers") && (
          <ul className="mt-4 space-y-2">
            {(d.choices || []).map((c) => (
              <li key={c.id} className="flex items-start gap-3 rounded-xl border border-slate-200 px-3 py-2 text-sm">
                <span className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold">{c.id}</span>
                <div>
                  {c.text && <MathRenderer content={c.text} />}
                  {c.image_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={c.image_url} alt="" className="mt-1 max-h-40 w-auto rounded-lg" />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {q.type === "true_false" && (
          <ul className="mt-4 flex gap-3">
            {[true, false].map((v) => (
              <li key={String(v)} className="rounded-xl border border-slate-200 px-4 py-2 text-sm">{t(v ? "bank.editor.true" : "bank.editor.false")}</li>
            ))}
          </ul>
        )}
        {(q.type === "numeric" || q.type === "short_text") && (
          <input disabled aria-label={t("bank.preview.answerField")} placeholder={t("bank.preview.answerField")}
            className="mt-4 w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-sm" />
        )}
        {q.type === "matching" && (
          <ul className="mt-4 space-y-2">
            {(d.lefts || []).map((l) => (
              <li key={l.id} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">{l.text}</li>
            ))}
            <li className="pt-1 text-xs font-bold uppercase text-slate-500">{t("player.structured.choose")}</li>
            {(d.rights || []).map((r) => (
              <li key={r.id} className="rounded-xl border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-700">{r.text}</li>
            ))}
          </ul>
        )}
        {q.type === "fill_blank" && (
          <p className="mt-4 whitespace-pre-wrap text-sm leading-8">
            {(d.text || "").split(/\{\{(\d+)\}\}/).map((part, i) => i % 2 === 0
              ? <span key={i}>{part}</span>
              : <span key={i} className="mx-1 inline-block w-28 border-b-2 border-slate-400" aria-label={t("player.structured.blankN", { n: part })}>&nbsp;</span>)}
          </p>
        )}
        {q.type === "ordering" && (
          <ol className="mt-4 list-inside list-decimal space-y-2">
            {(d.items || []).map((i) => <li key={i.id} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">{i.text}</li>)}
          </ol>
        )}
        {q.type === "essay" && (
          <div className="mt-4">
            <textarea disabled rows={5} aria-label={t("bank.preview.essayField")} placeholder={t("bank.preview.essayField")}
              className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-sm" />
            {d.word_limit ? <p className="mt-1 text-xs text-slate-500">{t("bank.preview.wordLimit", { n: d.word_limit })}</p> : null}
          </div>
        )}
        {q.points !== undefined && (
          <p className="mt-3 text-xs text-slate-500">{t("bank.preview.points", { n: String(q.points) })}</p>
        )}
      </div>
    </div>
  );
}
