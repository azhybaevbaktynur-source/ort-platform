"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { DIFFICULTIES, QUESTION_TYPES, ORT_SECTIONS, type Difficulty, type QuestionType } from "@/lib/lms/contentTypes";
import { LMS_LANGS, type Lang } from "@/lib/lms/types";
import { btnSmall, inputCls } from "./ui";

export interface BankFilterState {
  q: string;
  type: QuestionType | "";
  language: Lang | "";
  section: string;
  topic: string;
  difficulty: Difficulty | "";
  tag: string;
  deleted: boolean;
}
export const EMPTY_FILTERS: BankFilterState = { q: "", type: "", language: "", section: "", topic: "", difficulty: "", tag: "", deleted: false };

export function BankFilters({ value, onChange }: { value: BankFilterState; onChange: (v: BankFilterState) => void }) {
  const { t } = useTranslation();
  const set = (p: Partial<BankFilterState>) => onChange({ ...value, ...p });
  const dirty = JSON.stringify(value) !== JSON.stringify(EMPTY_FILTERS);
  const lbl = "text-xs font-medium text-slate-600";
  return (
    <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-3">
      <input type="search" aria-label={t("bank.filters.search")} placeholder={t("bank.filters.search")} className={inputCls}
        value={value.q} onChange={(e) => set({ q: e.target.value })} />
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <label className={lbl}>{t("bank.filters.type")}
          <select className={`${inputCls} mt-0.5`} value={value.type} onChange={(e) => set({ type: e.target.value as QuestionType | "" })}>
            <option value="">{t("bank.filters.all")}</option>
            {QUESTION_TYPES.map((ty) => <option key={ty} value={ty}>{t(`bank.types.${ty}.name`)}</option>)}
          </select>
        </label>
        <label className={lbl}>{t("bank.filters.language")}
          <select className={`${inputCls} mt-0.5`} value={value.language} onChange={(e) => set({ language: e.target.value as Lang | "" })}>
            <option value="">{t("bank.filters.all")}</option>
            {LMS_LANGS.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
          </select>
        </label>
        <label className={lbl}>{t("bank.filters.section")}
          <input list="bank-filter-sections" className={`${inputCls} mt-0.5`} value={value.section} onChange={(e) => set({ section: e.target.value })} />
          <datalist id="bank-filter-sections">
            {ORT_SECTIONS.map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}
          </datalist>
        </label>
        <label className={lbl}>{t("bank.filters.topic")}
          <input className={`${inputCls} mt-0.5`} value={value.topic} onChange={(e) => set({ topic: e.target.value })} />
        </label>
        <label className={lbl}>{t("bank.filters.difficulty")}
          <select className={`${inputCls} mt-0.5`} value={value.difficulty} onChange={(e) => set({ difficulty: e.target.value as Difficulty | "" })}>
            <option value="">{t("bank.filters.all")}</option>
            {DIFFICULTIES.map((d) => <option key={d} value={d}>{t(`bank.difficulty.${d}`)}</option>)}
          </select>
        </label>
        <label className={lbl}>{t("bank.filters.tag")}
          <input className={`${inputCls} mt-0.5`} value={value.tag} onChange={(e) => set({ tag: e.target.value })} />
        </label>
      </div>
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-1.5 text-sm text-slate-700">
          <input type="checkbox" checked={value.deleted} onChange={(e) => set({ deleted: e.target.checked })} />
          {t("bank.filters.deleted")}
        </label>
        {dirty && <button type="button" className={btnSmall} onClick={() => onChange(EMPTY_FILTERS)}>{t("bank.filters.reset")}</button>}
      </div>
    </div>
  );
}
