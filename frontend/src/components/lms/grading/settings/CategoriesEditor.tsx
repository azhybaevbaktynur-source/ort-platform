"use client";

import React, { useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { createCategory, deleteCategory, reorderCategories, updateCategory } from "@/lib/lms/grading";
import type { CategoryOut, TotalMode } from "@/lib/lms/gradingTypes";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { btnDanger, btnPrimary, btnSecondary, btnSmall, inputCls, labelCls } from "@/components/lms/content/ui";
import { SchemeError } from "../schemes/SchemeError";

interface Draft { id: string | null; title: LocalizedText; weight: string }

/** Categories of a course: add, rename, weight, reorder (up/down), delete. Each action calls the API and reports the new list. */
export function CategoriesEditor({
  courseId, categories, mode, languages, defaultLanguage, onChange,
}: {
  courseId: string;
  categories: CategoryOut[];
  mode: TotalMode;
  languages: Lang[];
  defaultLanguage: Lang;
  onChange: (cats: CategoryOut[]) => void;
}) {
  const { lang, t } = useTranslation();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) { setError(e); } finally { setBusy(false); }
  };

  const sum = categories.reduce((acc, c) => acc + (Number(c.weight) || 0), 0);
  const weightNum = draft ? Number(draft.weight) : NaN;
  const draftValid = !!draft && cleanLocalized(draft.title, languages)[defaultLanguage] !== undefined
    && draft.weight.trim() !== "" && Number.isFinite(weightNum) && weightNum >= 0 && weightNum <= 1000;

  const save = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!draft || !draftValid) return;
    void run(async () => {
      const body = { title: cleanLocalized(draft.title, languages), weight: weightNum };
      if (draft.id) {
        const out = await updateCategory(courseId, draft.id, body);
        onChange(categories.map((c) => (c.id === out.id ? out : c)));
      } else {
        onChange([...categories, await createCategory(courseId, body)]);
      }
      setDraft(null);
    });
  };

  // 409 category_in_use is shown by SchemeError below (lms.errors.category_in_use).
  const remove = (c: CategoryOut) => void run(async () => {
    await deleteCategory(courseId, c.id);
    onChange(categories.filter((x) => x.id !== c.id));
  });

  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= categories.length) return;
    const ids = categories.map((c) => c.id);
    [ids[i], ids[j]] = [ids[j], ids[i]];
    void run(async () => { onChange(await reorderCategories(courseId, ids)); });
  };

  return (
    <div className="space-y-3">
      <h3 className="text-base font-bold text-slate-900">{t("grading.settings.categories")}</h3>
      <p className="text-xs text-slate-500">{t("grading.settings.categoriesHint")}</p>
      {categories.length === 0 && <p className="text-sm text-slate-500">{t("grading.settings.noCategories")}</p>}
      <ul className="space-y-2">
        {categories.map((c, i) => (
          <li key={c.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-slate-900">{pickLocalized(c.title, lang, defaultLanguage)}</p>
              <p className="text-xs text-slate-500">
                {t("grading.settings.weightValue", { weight: String(Number(c.weight)) })} · {t("grading.settings.assessmentCount", { count: c.assessment_count })}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              <button type="button" className={btnSmall} disabled={busy || i === 0} aria-label={t("grading.settings.moveUp")} onClick={() => move(i, -1)}>
                <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              <button type="button" className={btnSmall} disabled={busy || i === categories.length - 1} aria-label={t("grading.settings.moveDown")} onClick={() => move(i, 1)}>
                <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              <button type="button" className={btnSmall} disabled={busy} onClick={() => { setError(null); setDraft({ id: c.id, title: c.title, weight: String(Number(c.weight)) }); }}>
                {t("grading.settings.edit")}
              </button>
              <button type="button" className={btnDanger} disabled={busy} onClick={() => remove(c)}>{t("grading.settings.delete")}</button>
            </div>
          </li>
        ))}
      </ul>
      {categories.length > 0 && (
        <p className="text-xs text-slate-600">
          {t("grading.settings.weightsSum", { sum: String(Math.round(sum * 100) / 100) })}
          {mode === "weighted" && <> {t("grading.settings.normalization")}</>}
        </p>
      )}
      {draft ? (
        <form onSubmit={save} className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3" noValidate>
          <LocalizedTextInput label={t("grading.settings.categoryTitle")} languages={languages} defaultLanguage={defaultLanguage}
            value={draft.title} onChange={(title) => setDraft({ ...draft, title })} maxLength={100} required disabled={busy} />
          <div className="max-w-[10rem]">
            <label htmlFor="cat-weight" className={labelCls}>{t("grading.settings.weight")}</label>
            <input id="cat-weight" type="number" min={0} max={1000} step="any" className={inputCls} disabled={busy}
              value={draft.weight} onChange={(e) => setDraft({ ...draft, weight: e.target.value })} />
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={btnPrimary} disabled={busy || !draftValid}>{busy ? t("lms.common.loading") : t("lms.common.save")}</button>
            <button type="button" className={btnSecondary} disabled={busy} onClick={() => { setDraft(null); setError(null); }}>{t("lms.common.cancel")}</button>
          </div>
        </form>
      ) : (
        <button type="button" className={btnSecondary} disabled={busy} onClick={() => { setError(null); setDraft({ id: null, title: {}, weight: "0" }); }}>
          {t("grading.settings.addCategory")}
        </button>
      )}
      <SchemeError error={error} />
    </div>
  );
}
