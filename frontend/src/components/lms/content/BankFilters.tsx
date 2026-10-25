"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { DIFFICULTIES, QUESTION_TYPES, ORT_SECTIONS, type Difficulty, type QuestionType } from "@/lib/lms/contentTypes";
import { LMS_LANGS, type Lang } from "@/lib/lms/types";
import { Button, Checkbox, Input, SearchInput, Select } from "@/components/ui";

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

/**
 * Question filters. Phase 6b S11b (UX 1): design-system `SearchInput` / `Select` / `Input` / `Checkbox` with visible
 * labels (16 px text on phones); the card spans the full width.
 */
export function BankFilters({ value, onChange }: { value: BankFilterState; onChange: (v: BankFilterState) => void }) {
  const { t } = useTranslation();
  const set = (p: Partial<BankFilterState>) => onChange({ ...value, ...p });
  const dirty = JSON.stringify(value) !== JSON.stringify(EMPTY_FILTERS);
  const all = { value: "", label: t("bank.filters.all") };
  return (
    <div role="search" className="w-full space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
      <SearchInput label={t("bank.filters.search")} value={value.q} onChange={(q) => set({ q })} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Select label={t("bank.filters.type")} value={value.type} onChange={(e) => set({ type: e.target.value as QuestionType | "" })}
          options={[all, ...QUESTION_TYPES.map((ty) => ({ value: ty, label: t(`bank.types.${ty}.name`) }))]} />
        <Select label={t("bank.filters.language")} value={value.language} onChange={(e) => set({ language: e.target.value as Lang | "" })}
          options={[all, ...LMS_LANGS.map((l) => ({ value: l, label: t(`courses.languages.${l}`) }))]} />
        <Input label={t("bank.filters.section")} list="bank-filter-sections" value={value.section} onChange={(e) => set({ section: e.target.value })} />
        <datalist id="bank-filter-sections">
          {ORT_SECTIONS.map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}
        </datalist>
        <Input label={t("bank.filters.topic")} value={value.topic} onChange={(e) => set({ topic: e.target.value })} />
        <Select label={t("bank.filters.difficulty")} value={value.difficulty} onChange={(e) => set({ difficulty: e.target.value as Difficulty | "" })}
          options={[all, ...DIFFICULTIES.map((d) => ({ value: d, label: t(`bank.difficulty.${d}`) }))]} />
        <Input label={t("bank.filters.tag")} value={value.tag} onChange={(e) => set({ tag: e.target.value })} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Checkbox label={t("bank.filters.deleted")} checked={value.deleted} onChange={(e) => set({ deleted: e.target.checked })} />
        {dirty && <Button variant="secondary" size="sm" onClick={() => onChange(EMPTY_FILTERS)}>{t("bank.filters.reset")}</Button>}
      </div>
    </div>
  );
}
