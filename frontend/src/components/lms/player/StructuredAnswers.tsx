"use client";

import React from "react";
import { ArrowDown, ArrowUp, Check } from "lucide-react";
import { cn, focusRing } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import type { StudentQuestion } from "@/lib/lms/attemptTypes";
import type { StudentQuestionOut } from "@/lib/lms/contentTypes";
import type { ResponseObj } from "./playerUtils";

/** The structured fields of a student question (attemptTypes keeps the older, narrower `data` type). */
const sdata = (q: StudentQuestion) => q.data as StudentQuestionOut["data"];

type Props = {
  question: StudentQuestion;
  response: ResponseObj;
  disabled?: boolean;
  onChange: (response: ResponseObj) => void;
};

const SELECT = `min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-base focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200`;
const MOVE_BTN = `inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40 ${focusRing}`;

export function MatchingAnswer({ question, response, disabled, onChange }: Props) {
  const { t } = useTranslation();
  const lefts = sdata(question).lefts ?? [];
  const rights = sdata(question).rights ?? [];
  const pairs = ((response ?? {}).pairs ?? {}) as Record<string, string>;
  const set = (leftId: string, rightId: string) => {
    const next = { ...pairs };
    if (rightId) next[leftId] = rightId;
    else delete next[leftId];
    onChange({ pairs: next });
  };
  return (
    <div role="group" aria-label={t("player.answers")} className="space-y-3">
      {lefts.map((l) => (
        <div key={l.id} className="grid gap-1.5 rounded-xl border border-slate-200 p-3 md:grid-cols-2 md:items-center md:gap-4">
          <MathRenderer content={l.text} className="text-base text-slate-900" />
          <select
            disabled={disabled}
            value={pairs[l.id] ?? ""}
            onChange={(e) => set(l.id, e.target.value)}
            className={SELECT}
            aria-label={t("player.structured.matchWith", { item: l.text })}
          >
            <option value="">{t("player.structured.choose")}</option>
            {rights.map((r) => <option key={r.id} value={r.id}>{r.text}</option>)}
          </select>
        </div>
      ))}
    </div>
  );
}

export function FillBlankAnswer({ question, response, disabled, onChange }: Props) {
  const { t } = useTranslation();
  const text = sdata(question).text ?? "";
  const blanks = ((response ?? {}).blanks ?? {}) as Record<string, string>;
  const set = (n: string, value: string) => {
    const next = { ...blanks };
    if (value) next[n] = value;
    else delete next[n];
    onChange({ blanks: next });
  };
  // "a {{1}} b" -> ["a ", "1", " b"]: odd indexes are blank numbers.
  const parts = text.split(/\{\{(\d+)\}\}/);
  return (
    <p className="text-base leading-[2.6] text-slate-900">
      {parts.map((part, i) => i % 2 === 0 ? (
        <span key={i} className="whitespace-pre-wrap">{part}</span>
      ) : (
        <input
          key={i}
          type="text"
          autoComplete="off"
          maxLength={200}
          disabled={disabled}
          value={blanks[part] ?? ""}
          onChange={(e) => set(part, e.target.value)}
          aria-label={t("player.structured.blankN", { n: part })}
          className="mx-1 inline-block min-h-11 w-40 max-w-full rounded-xl border border-slate-300 px-3 py-1 align-middle text-base focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
        />
      ))}
    </p>
  );
}

export function OrderingAnswer({ question, response, disabled, onChange }: Props) {
  const { t } = useTranslation();
  const items = sdata(question).items ?? [];
  const byId = new Map(items.map((i) => [i.id, i]));
  const stored = (response ?? {}).order;
  const answered = Array.isArray(stored) && stored.length > 0;
  // Rows in the saved order, then anything the saved list misses (never drops an item from the screen).
  const ids = answered ? (stored as string[]).filter((id) => byId.has(id)) : [];
  for (const i of items) if (!ids.includes(i.id)) ids.push(i.id);
  const moveBy = (idx: number, d: -1 | 1) => {
    const j = idx + d;
    if (j < 0 || j >= ids.length) return;
    const next = [...ids];
    [next[idx], next[j]] = [next[j], next[idx]];
    onChange({ order: next });
  };
  return (
    <div className="space-y-2">
      <ol aria-label={t("player.answers")} className="space-y-2">
        {ids.map((id, idx) => (
          <li key={id} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-2">
            <span className="w-6 shrink-0 text-center text-sm font-semibold text-slate-500" aria-hidden="true">{idx + 1}</span>
            <span className="min-w-0 flex-1 text-base text-slate-900"><MathRenderer content={byId.get(id)?.text ?? ""} /></span>
            <button type="button" disabled={disabled || idx === 0} className={MOVE_BTN} onClick={() => moveBy(idx, -1)}
              aria-label={t("player.structured.moveUp", { item: byId.get(id)?.text ?? "" })}>
              <ArrowUp className="h-5 w-5" aria-hidden="true" />
            </button>
            <button type="button" disabled={disabled || idx === ids.length - 1} className={MOVE_BTN} onClick={() => moveBy(idx, 1)}
              aria-label={t("player.structured.moveDown", { item: byId.get(id)?.text ?? "" })}>
              <ArrowDown className="h-5 w-5" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ol>
      <button
        type="button"
        disabled={disabled || answered}
        onClick={() => onChange({ order: ids })}
        className={cn("inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-60", focusRing)}
      >
        {answered && <Check className="h-4 w-4" aria-hidden="true" />}
        {t("player.structured.keepOrder")}
      </button>
    </div>
  );
}
