"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getCourseGrading, updateCourseGrading } from "@/lib/lms/grading";
import {
  isStaffCourseGrading, TOTAL_MODES, type CategoryOut, type CourseGradingStaffOut, type LatePolicy, type TotalMode,
} from "@/lib/lms/gradingTypes";
import type { Lang } from "@/lib/lms/types";
import { btnPrimary, inputCls, labelCls } from "@/components/lms/content/ui";
import { SchemeError } from "../schemes/SchemeError";
import { CategoriesEditor } from "./CategoriesEditor";
import { SchemePicker } from "./SchemePicker";

const card = "rounded-2xl border border-slate-200 bg-white p-6";
const DEFAULT_LATE: LatePolicy = { percent_per_day: 10, max_percent: 50, grace_minutes: 0 };
const inRange = (v: string, lo: number, hi: number) => v.trim() !== "" && Number.isFinite(Number(v)) && Number(v) >= lo && Number(v) <= hi;

/** Course "Grading" settings: total mode, course scheme, late policy, categories. PUT /grading is a full replace. */
export function CourseGradingSection({
  courseId, languages, defaultLanguage,
}: { courseId: string; languages: Lang[]; defaultLanguage: Lang }) {
  const { t } = useTranslation();
  const [data, setData] = useState<CourseGradingStaffOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [mode, setMode] = useState<TotalMode>("points");
  const [schemeId, setSchemeId] = useState<string | null>(null);
  const [lateOn, setLateOn] = useState(false);
  const [perDay, setPerDay] = useState("");
  const [maxPct, setMaxPct] = useState("");
  const [grace, setGrace] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const seed = useCallback((g: CourseGradingStaffOut) => {
    setMode(g.total_mode);
    setSchemeId(g.scheme?.id ?? null);
    setLateOn(!!g.late_policy);
    const lp = g.late_policy ?? DEFAULT_LATE;
    setPerDay(String(lp.percent_per_day)); setMaxPct(String(lp.max_percent)); setGrace(String(lp.grace_minutes));
  }, []);

  /** `reseed` replaces the form fields (first load, after save); otherwise only server-derived data (categories, warnings). */
  const load = useCallback(async (reseed: boolean) => {
    try {
      const g = await getCourseGrading(courseId);
      if (isStaffCourseGrading(g)) { setData(g); if (reseed) seed(g); }
      setLoadError(null);
    } catch (e) {
      setLoadError(e);
    }
  }, [courseId, seed]);
  useEffect(() => { void load(true); }, [load]);

  if (loadError && !data) return <section className={card}><SchemeError error={loadError} onRetry={() => void load(true)} /></section>;
  if (!data) return <section className={card}><p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p></section>;

  const lateValid = !lateOn || (inRange(perDay, 0, 100) && inRange(maxPct, 0, 100) && inRange(grace, 0, 1440));

  const save = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!lateValid) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const out = await updateCourseGrading(courseId, {
        total_mode: mode,
        grading_scheme_version_id: schemeId,
        late_policy: lateOn ? { percent_per_day: Number(perDay), max_percent: Number(maxPct), grace_minutes: Math.round(Number(grace)) } : null,
      });
      if (isStaffCourseGrading(out)) { setData(out); seed(out); }
      setSaved(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  // Warnings depend on categories: refresh after a category change without touching unsaved form fields.
  const setCategories = (cats: CategoryOut[]) => { setData({ ...data, categories: cats }); void load(false); };

  return (
    <section className={`${card} space-y-6`}>
      <h2 className="text-lg font-bold text-slate-900">{t("grading.settings.title")}</h2>
      {data.warnings.map((w) => (
        <p key={w} role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm text-amber-900">
          {t(`grading.settings.warnings.${w}`)}
        </p>
      ))}
      <form onSubmit={save} className="space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="cg-mode" className={labelCls}>{t("grading.settings.totalMode")}</label>
            <select id="cg-mode" className={inputCls} disabled={busy} value={mode} onChange={(e) => setMode(e.target.value as TotalMode)}>
              {TOTAL_MODES.map((m) => <option key={m} value={m}>{t(`grading.settings.totalModes.${m}`)}</option>)}
            </select>
            <p className="mt-1 text-xs text-slate-500">{t(`grading.settings.totalModeHint.${mode}`)}</p>
          </div>
          <div>
            <label htmlFor="cg-scheme" className={labelCls}>{t("grading.settings.courseScheme")}</label>
            <SchemePicker id="cg-scheme" value={schemeId} current={data.scheme} onChange={setSchemeId} disabled={busy} defaultLanguage={defaultLanguage} />
            <p className="mt-1 text-xs text-slate-500">{t("grading.settings.courseSchemeHint")}</p>
          </div>
        </div>
        <fieldset className="space-y-3" disabled={busy}>
          <legend className={labelCls}>{t("grading.settings.latePolicy")}</legend>
          <label className="flex items-center gap-2 text-sm text-slate-700" htmlFor="cg-late">
            <input id="cg-late" type="checkbox" checked={lateOn} onChange={(e) => setLateOn(e.target.checked)} />{t("grading.settings.lateEnable")}
          </label>
          {lateOn && (
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label htmlFor="cg-perday" className={labelCls}>{t("grading.settings.latePerDay")}</label>
                <input id="cg-perday" type="number" min={0} max={100} step="any" className={inputCls} value={perDay} onChange={(e) => setPerDay(e.target.value)} />
              </div>
              <div>
                <label htmlFor="cg-max" className={labelCls}>{t("grading.settings.lateMax")}</label>
                <input id="cg-max" type="number" min={0} max={100} step="any" className={inputCls} value={maxPct} onChange={(e) => setMaxPct(e.target.value)} />
              </div>
              <div>
                <label htmlFor="cg-grace" className={labelCls}>{t("grading.settings.lateGrace")}</label>
                <input id="cg-grace" type="number" min={0} max={1440} step={1} className={inputCls} value={grace} onChange={(e) => setGrace(e.target.value)} />
              </div>
            </div>
          )}
          {lateOn && !lateValid && <p className="text-xs text-red-700">{t("grading.settings.lateInvalid")}</p>}
          <p className="text-xs text-slate-500">{t("grading.settings.lateHint")}</p>
        </fieldset>
        <SchemeError error={error} />
        <div className="flex items-center gap-3">
          <button type="submit" className={btnPrimary} disabled={busy || !lateValid}>{busy ? t("lms.common.loading") : t("lms.common.save")}</button>
          {saved && !error && <span role="status" className="text-sm text-emerald-700">{t("courses.settings.saved")}</span>}
        </div>
      </form>
      <CategoriesEditor courseId={courseId} categories={data.categories} mode={mode} languages={languages}
        defaultLanguage={defaultLanguage} onChange={setCategories} />
    </section>
  );
}
