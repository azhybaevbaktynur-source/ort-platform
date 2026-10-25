"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listBanks } from "@/lib/lms/content";
import { DIFFICULTIES, QUESTION_TYPES, type BankOut, type Difficulty, type QuestionType } from "@/lib/lms/contentTypes";
import { useTemplateUi } from "@/lib/lms/templates";
import type { PickFilter } from "@/lib/lms/assessmentTypes";
import { inputCls, labelCls } from "@/components/lms/content/ui";
import { ContentError } from "@/components/lms/content/ContentError";

/** Loads the course banks once (first 100) for pickers. */
export function useBanks(courseId: string, enabled = true) {
  const [banks, setBanks] = useState<BankOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    listBanks(courseId, { limit: 100 }).then((p) => { if (alive) setBanks(p.items); }).catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [courseId, enabled]);
  return { banks, error };
}

export function BankSelect({ banks, value, onChange, id }: { banks: BankOut[]; value: string; onChange: (v: string) => void; id: string }) {
  const { t } = useTranslation();
  return (
    <div>
      <label className={labelCls} htmlFor={id}>{t("assessments.add.bank")}</label>
      <select id={id} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("assessments.add.chooseBank")}</option>
        {banks.map((b) => <option key={b.id} value={b.id}>{b.title}</option>)}
      </select>
    </div>
  );
}

export interface PickValue { bank_id: string; count: number; filter: PickFilter }

/** Pick N random questions from a bank by filter. Pool size (per language) is shown by the item after it is saved. */
export function PickFields({ courseId, value, onChange, lockBank = false }: { courseId: string; value: PickValue; onChange: (v: PickValue) => void; lockBank?: boolean }) {
  const { t } = useTranslation();
  const ui = useTemplateUi();
  const { banks, error } = useBanks(courseId);
  const setF = (p: Partial<PickFilter>) => {
    const f: PickFilter = { ...value.filter, ...p };
    (Object.keys(f) as (keyof PickFilter)[]).forEach((k) => { if (f[k] === "" || f[k] === undefined) delete f[k]; });
    onChange({ ...value, filter: f });
  };
  return (
    <div className="space-y-3">
      <ContentError error={error} />
      {!lockBank && <BankSelect id="pick-bank" banks={banks} value={value.bank_id} onChange={(v) => onChange({ ...value, bank_id: v })} />}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={labelCls} htmlFor="pick-count">{t("assessments.pick.count")}</label>
          <input id="pick-count" type="number" min={1} max={200} className={inputCls} value={value.count}
            onChange={(e) => onChange({ ...value, count: Math.max(1, Math.min(200, Math.round(Number(e.target.value) || 1))) })} />
        </div>
        <div>
          <label className={labelCls} htmlFor="pick-type">{t("bank.filters.type")}</label>
          <select id="pick-type" className={inputCls} value={value.filter.type ?? ""} onChange={(e) => setF({ type: (e.target.value || undefined) as QuestionType | undefined })}>
            <option value="">{t("bank.filters.all")}</option>
            {QUESTION_TYPES.map((q) => <option key={q} value={q}>{t(`bank.types.${q}.name`)}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="pick-section">{t("bank.filters.section")}</label>
          <input id="pick-section" list={ui.sectionKeys.length ? "pick-sections" : undefined} className={inputCls} value={value.filter.section ?? ""} onChange={(e) => setF({ section: e.target.value })} />
          {ui.sectionKeys.length > 0 && <datalist id="pick-sections">{ui.sectionKeys.map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}</datalist>}
        </div>
        <div>
          <label className={labelCls} htmlFor="pick-topic">{t("bank.filters.topic")}</label>
          <input id="pick-topic" className={inputCls} value={value.filter.topic ?? ""} onChange={(e) => setF({ topic: e.target.value })} />
        </div>
        <div>
          <label className={labelCls} htmlFor="pick-diff">{t("bank.filters.difficulty")}</label>
          <select id="pick-diff" className={inputCls} value={value.filter.difficulty ?? ""} onChange={(e) => setF({ difficulty: (e.target.value || undefined) as Difficulty | undefined })}>
            <option value="">{t("bank.filters.all")}</option>
            {DIFFICULTIES.map((d) => <option key={d} value={d}>{t(`bank.difficulty.${d}`)}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="pick-tag">{t("bank.filters.tag")}</label>
          <input id="pick-tag" className={inputCls} value={(value.filter.tags ?? []).join(", ")}
            onChange={(e) => setF({ tags: e.target.value.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 5) })} />
          <p className="mt-1 text-xs text-slate-500">{t("assessments.pick.tagsHint")}</p>
        </div>
      </div>
    </div>
  );
}
