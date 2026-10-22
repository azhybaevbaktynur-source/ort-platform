"use client";

import React from "react";
import { Bookmark } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import type { StudentQuestion } from "@/lib/lms/attemptTypes";
import { letter, orderedChoices, type ResponseObj } from "./playerUtils";

const OPTION_BASE = "flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all";
const OPTION_ON = "border-brand-600 bg-brand-50/40 ring-1 ring-brand-600 font-medium text-slate-900";
const OPTION_OFF = "border-slate-200 bg-white text-slate-800 hover:border-brand-300 hover:bg-slate-50/50";

function Badge({ on, children, square }: { on: boolean; children: React.ReactNode; square?: boolean }) {
  return (
    <span
      className={`flex h-7 w-7 shrink-0 items-center justify-center text-sm font-semibold ${square ? "rounded-md" : "rounded-full"} ${
        on ? "bg-brand-600 text-white" : "border border-slate-200 bg-slate-100 text-slate-700"
      }`}
    >
      {children}
    </span>
  );
}

/** One question with its answer input. Dispatches on the question type (all 7 types). */
export function ItemView({
  question,
  choiceOrder,
  number,
  total,
  response,
  flagged,
  disabled,
  onChange,
  onToggleFlag,
}: {
  question: StudentQuestion;
  choiceOrder: string[] | null;
  number: number;
  total: number;
  response: ResponseObj;
  flagged: boolean;
  disabled?: boolean;
  onChange: (response: ResponseObj) => void;
  onToggleFlag: () => void;
}) {
  const { t } = useTranslation();
  const r = (response ?? {}) as Record<string, unknown>;

  return (
    <article className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-xs md:p-7" aria-labelledby={`q-${question.id}-h`}>
      <header className="flex items-center justify-between border-b border-slate-100 pb-4">
        <h2 id={`q-${question.id}-h`} className="rounded-lg bg-brand-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-brand-700">
          {t("player.questionOf", { n: number, total })}
        </h2>
        <button
          type="button"
          onClick={onToggleFlag}
          aria-pressed={flagged}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all ${
            flagged ? "border-amber-300 bg-amber-100 text-amber-800" : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100"
          }`}
        >
          <Bookmark className={`h-3.5 w-3.5 ${flagged ? "fill-amber-600 text-amber-600" : ""}`} aria-hidden="true" />
          {flagged ? t("player.unflag") : t("player.flag")}
        </button>
      </header>

      {question.stem ? (
        <div className="min-h-[56px]">
          <MathRenderer content={question.stem} className="font-serif text-base leading-relaxed text-gray-900 md:text-lg" />
        </div>
      ) : null}
      {question.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={question.image_url} alt={t("player.imageAlt")} className="max-h-80 w-auto rounded-lg border border-slate-100" />
      ) : null}

      {question.type === "single_choice" ? (
        <div role="radiogroup" aria-label={t("player.answers")} className="space-y-2">
          {orderedChoices(question, choiceOrder).map((c, i) => {
            const on = r.choice_id === c.id;
            return (
              <button
                key={c.id}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={disabled}
                onClick={() => onChange({ choice_id: on ? null : c.id })}
                className={`${OPTION_BASE} ${on ? OPTION_ON : OPTION_OFF}`}
              >
                <Badge on={on}>{letter(i)}</Badge>
                <ChoiceBody text={c.text} imageUrl={c.image_url} />
              </button>
            );
          })}
        </div>
      ) : null}

      {question.type === "multiple_answers" ? (
        <div role="group" aria-label={t("player.answers")} className="space-y-2">
          <p className="text-xs font-medium text-slate-500">{t("player.multipleHint")}</p>
          {orderedChoices(question, choiceOrder).map((c, i) => {
            const ids = Array.isArray(r.choice_ids) ? (r.choice_ids as string[]) : [];
            const on = ids.includes(c.id);
            return (
              <button
                key={c.id}
                type="button"
                role="checkbox"
                aria-checked={on}
                disabled={disabled}
                onClick={() => onChange({ choice_ids: on ? ids.filter((x) => x !== c.id) : [...ids, c.id] })}
                className={`${OPTION_BASE} ${on ? OPTION_ON : OPTION_OFF}`}
              >
                <Badge on={on} square>{on ? "✓" : letter(i)}</Badge>
                <ChoiceBody text={c.text} imageUrl={c.image_url} />
              </button>
            );
          })}
        </div>
      ) : null}

      {question.type === "true_false" ? (
        <div role="radiogroup" aria-label={t("player.answers")} className="grid grid-cols-2 gap-3">
          {([true, false] as const).map((v) => {
            const on = r.value === v;
            return (
              <button
                key={String(v)}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={disabled}
                onClick={() => onChange({ value: on ? null : v })}
                className={`${OPTION_BASE} justify-center ${on ? OPTION_ON : OPTION_OFF}`}
              >
                {v ? t("player.true") : t("player.false")}
              </button>
            );
          })}
        </div>
      ) : null}

      {question.type === "comparison" ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {(["a", "b"] as const).map((k) => (
              <div key={k} className="flex flex-col items-center rounded-2xl border-2 border-slate-200 bg-slate-50/60 p-4 text-center md:p-6">
                <span className="mb-3 inline-block rounded-md bg-gray-100 px-3 py-1 text-xs font-bold uppercase tracking-widest text-gray-500">
                  {k === "a" ? t("player.comparison.columnA") : t("player.comparison.columnB")}
                </span>
                <div className="flex min-h-[60px] items-center justify-center text-xl font-semibold text-gray-900">
                  <MathRenderer content={(k === "a" ? question.data.column_a : question.data.column_b) || "—"} />
                </div>
              </div>
            ))}
          </div>
          <div role="radiogroup" aria-label={t("player.answers")} className="space-y-2">
            {(["A", "B", "C", "D"] as const).map((id) => {
              const on = r.choice === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  disabled={disabled}
                  onClick={() => onChange({ choice: on ? null : id })}
                  className={`${OPTION_BASE} ${on ? OPTION_ON : OPTION_OFF}`}
                >
                  <Badge on={on}>{id}</Badge>
                  <span className="flex-1">{t(`bank.types.comparison.labels.${id}`)}</span>
                </button>
              );
            })}
          </div>
        </>
      ) : null}

      {question.type === "numeric" ? (
        <label className="block max-w-xs space-y-1">
          <span className="text-xs font-medium text-slate-500">{t("player.numeric.label")}</span>
          <input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            maxLength={100}
            disabled={disabled}
            value={typeof r.value === "string" ? r.value : ""}
            onChange={(e) => onChange({ value: e.target.value })}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 font-mono text-base focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
          />
        </label>
      ) : null}

      {question.type === "short_text" ? (
        <label className="block space-y-1">
          <span className="text-xs font-medium text-slate-500">{t("player.shortText.label")}</span>
          <input
            type="text"
            autoComplete="off"
            maxLength={500}
            disabled={disabled}
            value={typeof r.text === "string" ? r.text : ""}
            onChange={(e) => onChange({ text: e.target.value })}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
          />
        </label>
      ) : null}

      {question.type === "essay" ? <EssayInput question={question} value={typeof r.text === "string" ? r.text : ""} disabled={disabled} onChange={(text) => onChange({ text })} /> : null}
    </article>
  );
}

function ChoiceBody({ text, imageUrl }: { text: string; imageUrl?: string | null }) {
  return (
    <span className="flex flex-1 flex-col gap-2">
      {text ? <MathRenderer content={text} className="font-serif text-base leading-relaxed text-gray-900" /> : null}
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt="" className="max-h-40 w-auto rounded-md" />
      ) : null}
    </span>
  );
}

function EssayInput({
  question,
  value,
  disabled,
  onChange,
}: {
  question: StudentQuestion;
  value: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation();
  const limit = question.data.word_limit ?? null;
  const words = value.trim() ? value.trim().split(/\s+/).length : 0;
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-slate-500">{t("player.essay.label")}</span>
      <textarea
        rows={10}
        maxLength={20000}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base leading-relaxed focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
      />
      <span className={`block text-xs ${limit !== null && words > limit ? "text-red-600" : "text-slate-500"}`}>
        {limit !== null ? t("player.essay.wordsLimit", { n: words, limit }) : t("player.essay.words", { n: words })}
      </span>
    </label>
  );
}
