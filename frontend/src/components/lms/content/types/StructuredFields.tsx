"use client";

import React from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { inputCls, labelCls } from "../ui";
import { btnSmall } from "@/components/lms/course/staffUi";
import type { QuestionForm } from "./formModel";

type Props = { form: QuestionForm; onChange: (patch: Partial<QuestionForm>) => void; disabled?: boolean };

const iconBtn = `${btnSmall} !px-2`;

function move<T>(list: T[], i: number, d: -1 | 1): T[] {
  const j = i + d;
  if (j < 0 || j >= list.length) return list;
  const out = [...list];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

function RowButtons({ i, n, disabled, onMove, onRemove, canRemove }: {
  i: number; n: number; disabled?: boolean; onMove: (d: -1 | 1) => void; onRemove: () => void; canRemove: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex shrink-0 gap-1">
      <button type="button" disabled={disabled || i === 0} className={iconBtn} aria-label={t("bank.editor.structured.up")} onClick={() => onMove(-1)}>
        <ArrowUp className="h-4 w-4" aria-hidden="true" />
      </button>
      <button type="button" disabled={disabled || i === n - 1} className={iconBtn} aria-label={t("bank.editor.structured.down")} onClick={() => onMove(1)}>
        <ArrowDown className="h-4 w-4" aria-hidden="true" />
      </button>
      <button type="button" disabled={disabled || !canRemove} className={iconBtn} aria-label={t("bank.editor.structured.remove")} onClick={onRemove}>
        <Trash2 className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}

export function MatchingFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const pairs = form.matchPairs;
  const setPair = (i: number, patch: Partial<{ left: string; right: string }>) =>
    onChange({ matchPairs: pairs.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const dis = form.matchDistractors;
  return (
    <div className="space-y-3">
      <span className={labelCls}>{t("bank.editor.structured.pairs")}</span>
      {pairs.map((p, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 p-2">
          <input disabled={disabled} className={`${inputCls} min-w-[8rem] flex-1`} value={p.left} maxLength={500}
            aria-label={`${t("bank.editor.structured.left")} ${i + 1}`} placeholder={t("bank.editor.structured.left")}
            onChange={(e) => setPair(i, { left: e.target.value })} />
          <input disabled={disabled} className={`${inputCls} min-w-[8rem] flex-1`} value={p.right} maxLength={500}
            aria-label={`${t("bank.editor.structured.right")} ${i + 1}`} placeholder={t("bank.editor.structured.right")}
            onChange={(e) => setPair(i, { right: e.target.value })} />
          <RowButtons i={i} n={pairs.length} disabled={disabled} canRemove={pairs.length > 2}
            onMove={(d) => onChange({ matchPairs: move(pairs, i, d) })}
            onRemove={() => onChange({ matchPairs: pairs.filter((_, j) => j !== i) })} />
        </div>
      ))}
      <button type="button" disabled={disabled || pairs.length >= 20} className={btnSmall}
        onClick={() => onChange({ matchPairs: [...pairs, { left: "", right: "" }] })}>
        <Plus className="mr-1 inline h-4 w-4" aria-hidden="true" />{t("bank.editor.structured.addPair")}
      </button>
      <span className={labelCls}>{t("bank.editor.structured.distractors")}</span>
      {dis.map((d, i) => (
        <div key={i} className="flex items-center gap-2">
          <input disabled={disabled} className={inputCls} value={d} maxLength={500}
            aria-label={`${t("bank.editor.structured.distractor")} ${i + 1}`}
            onChange={(e) => onChange({ matchDistractors: dis.map((x, j) => (j === i ? e.target.value : x)) })} />
          <button type="button" disabled={disabled} className={iconBtn} aria-label={t("bank.editor.structured.remove")}
            onClick={() => onChange({ matchDistractors: dis.filter((_, j) => j !== i) })}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      ))}
      <button type="button" disabled={disabled || dis.length >= 10} className={btnSmall}
        onClick={() => onChange({ matchDistractors: [...dis, ""] })}>
        <Plus className="mr-1 inline h-4 w-4" aria-hidden="true" />{t("bank.editor.structured.addDistractor")}
      </button>
    </div>
  );
}

export function FillBlankFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const answers = form.blankAnswers;
  const addBlank = () => {
    const n = answers.length + 1;
    const sep = form.blankText && !/\s$/.test(form.blankText) ? " " : "";
    onChange({ blankText: `${form.blankText}${sep}{{${n}}}`, blankAnswers: [...answers, ""] });
  };
  return (
    <div className="space-y-3">
      <label className="block">
        <span className={labelCls}>{t("bank.editor.structured.blankText")}</span>
        <textarea disabled={disabled} rows={3} maxLength={2000} className={inputCls} value={form.blankText}
          onChange={(e) => onChange({ blankText: e.target.value })} />
      </label>
      <p className="text-xs text-slate-500">{t("bank.editor.structured.blankHint")}</p>
      {answers.map((a, i) => (
        <label key={i} className="block">
          <span className={labelCls}>{t("bank.editor.structured.blankN", { n: i + 1 })}</span>
          <input disabled={disabled} className={inputCls} value={a} maxLength={500}
            onChange={(e) => onChange({ blankAnswers: answers.map((x, j) => (j === i ? e.target.value : x)) })} />
        </label>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" disabled={disabled || answers.length >= 10} className={btnSmall} onClick={addBlank}>
          <Plus className="mr-1 inline h-4 w-4" aria-hidden="true" />{t("bank.editor.structured.addBlank")}
        </button>
        <label className="flex items-center gap-1.5 text-sm text-slate-700">
          <input type="checkbox" disabled={disabled} checked={form.caseSensitive} onChange={(e) => onChange({ caseSensitive: e.target.checked })} />
          {t("bank.editor.structured.caseSensitive")}
        </label>
      </div>
    </div>
  );
}

export function OrderingFields({ form, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const items = form.orderItems;
  return (
    <div className="space-y-2">
      <span className={labelCls}>{t("bank.editor.structured.orderItems")}</span>
      {items.map((s, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-6 shrink-0 text-right text-sm font-semibold text-slate-500" aria-hidden="true">{i + 1}.</span>
          <input disabled={disabled} className={inputCls} value={s} maxLength={500}
            aria-label={t("bank.editor.structured.itemN", { n: i + 1 })}
            onChange={(e) => onChange({ orderItems: items.map((x, j) => (j === i ? e.target.value : x)) })} />
          <RowButtons i={i} n={items.length} disabled={disabled} canRemove={items.length > 3}
            onMove={(d) => onChange({ orderItems: move(items, i, d) })}
            onRemove={() => onChange({ orderItems: items.filter((_, j) => j !== i) })} />
        </div>
      ))}
      <button type="button" disabled={disabled || items.length >= 20} className={btnSmall} onClick={() => onChange({ orderItems: [...items, ""] })}>
        <Plus className="mr-1 inline h-4 w-4" aria-hidden="true" />{t("bank.editor.structured.addItem")}
      </button>
    </div>
  );
}
