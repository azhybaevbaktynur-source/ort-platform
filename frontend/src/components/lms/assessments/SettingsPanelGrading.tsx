"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getCourseGrading, regradeAssessment } from "@/lib/lms/grading";
import { GRADE_RELEASES, isStaffCourseGrading, type CategoryOut, type GradeRelease, type SchemeVersionRef } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { inputCls, labelCls } from "@/components/lms/content/ui";
import { btnSecondary } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { SchemePicker } from "@/components/lms/grading/settings/SchemePicker";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";

export interface GradingFormValue {
  schemeVersionId: string | null;
  categoryId: string | null;
  /** datetime-local value */
  dueAt: string;
  release: GradeRelease;
  omit: boolean;
}

/** The "Grading" group of the assessment settings form (controlled by SettingsPanel). */
export function SettingsPanelGrading({
  courseId, assessmentId, value, onChange, currentScheme, defaultLanguage, disabled, schemeLocked = false,
}: {
  courseId: string;
  assessmentId: string;
  value: GradingFormValue;
  onChange: (v: GradingFormValue) => void;
  currentScheme: SchemeVersionRef | null;
  defaultLanguage: Lang;
  disabled: boolean;
  /** Phase 6 S4b: the grading scheme is fixed by a locked course template (greyed out with a note). */
  schemeLocked?: boolean;
}) {
  const { lang, t } = useTranslation();
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [regrading, setRegrading] = useState(false);
  const [regradeMsg, setRegradeMsg] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let off = false;
    getCourseGrading(courseId)
      .then((g) => { if (!off && isStaffCourseGrading(g)) setCategories(g.categories); })
      .catch((e) => { if (!off) setError(e); });
    return () => { off = true; };
  }, [courseId]);

  const set = (patch: Partial<GradingFormValue>) => onChange({ ...value, ...patch });

  // Regrade is chunked and resumable: call until nothing is pending.
  const regrade = async () => {
    setRegrading(true);
    setError(null);
    setRegradeMsg(null);
    try {
      let total = 0;
      for (let i = 0; i < 50; i++) {
        const r = await regradeAssessment(courseId, assessmentId);
        total += r.regraded;
        if (!r.pending) break;
      }
      setRegradeMsg(t("grading.settings.regradeDone", { count: total }));
    } catch (e) {
      setError(e);
    } finally {
      setRegrading(false);
    }
  };

  return (
    <fieldset className="space-y-4 rounded-xl border border-slate-200 p-4" disabled={disabled}>
      <legend className="px-1 text-sm font-bold text-slate-900">{t("grading.settings.assessmentGroup")}</legend>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={labelCls} htmlFor="ag-scheme">{t("grading.settings.scheme")}</label>
          <SchemePicker id="ag-scheme" value={value.schemeVersionId} current={currentScheme} disabled={disabled || schemeLocked}
            defaultLanguage={defaultLanguage} onChange={(id) => set({ schemeVersionId: id })} />
          <p className="mt-1 text-xs text-slate-500">{schemeLocked ? t("templates.lockedNote") : t("grading.settings.schemeHint")}</p>
        </div>
        <div>
          <label className={labelCls} htmlFor="ag-category">{t("grading.settings.category")}</label>
          <select id="ag-category" className={inputCls} disabled={disabled} value={value.categoryId ?? ""}
            onChange={(e) => set({ categoryId: e.target.value || null })}>
            <option value="">{t("grading.settings.noCategory")}</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{pickLocalized(c.title, lang, defaultLanguage)}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="ag-due">{t("grading.settings.dueAt")}</label>
          <input id="ag-due" type="datetime-local" className={inputCls} disabled={disabled} value={value.dueAt}
            onChange={(e) => set({ dueAt: e.target.value })} />
          <p className="mt-1 text-xs text-slate-500">{t("grading.settings.dueAtHint")}</p>
        </div>
        <div>
          <label className={labelCls} htmlFor="ag-release">{t("grading.settings.release")}</label>
          <select id="ag-release" className={inputCls} disabled={disabled} value={value.release}
            onChange={(e) => set({ release: e.target.value as GradeRelease })}>
            {GRADE_RELEASES.map((r) => <option key={r} value={r}>{t(`grading.settings.releaseModes.${r}`)}</option>)}
          </select>
          <p className="mt-1 text-xs text-slate-500">{t(`grading.settings.releaseHint.${value.release}`)}</p>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm text-slate-700" htmlFor="ag-omit">
        <input id="ag-omit" type="checkbox" checked={value.omit} disabled={disabled} onChange={(e) => set({ omit: e.target.checked })} />
        {t("grading.settings.omit")}
      </label>
      <div className="space-y-2 border-t border-slate-100 pt-3">
        <p className="text-xs text-slate-500">{t("grading.settings.regradeHint")}</p>
        <button type="button" className={btnSecondary} disabled={disabled || regrading} onClick={() => void regrade()}>
          {regrading ? t("lms.common.loading") : t("grading.settings.regrade")}
        </button>
        {regradeMsg && <p role="status" className="text-sm text-emerald-700">{regradeMsg}</p>}
      </div>
      <SchemeError error={error} />
    </fieldset>
  );
}
