"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { updateAssessment } from "@/lib/lms/assessments";
import {
  RESULTS_POLICIES, SCORE_POLICIES, type AssessmentStaffOut, type Navigation, type ResultsPolicy, type ScorePolicy,
} from "@/lib/lms/assessmentTypes";
import { cleanLocalized } from "@/lib/lms/localized";
import { isAssessmentLocked, useTemplateUi } from "@/lib/lms/templates";
import { LMS_LANGS, type Lang, type LocalizedText } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { inputCls, labelCls } from "@/components/lms/content/ui";
import { btnPrimary } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { AssessmentError } from "./AssessmentError";
import { SettingsPanelGrading, type GradingFormValue } from "./SettingsPanelGrading";
import { fromLocalInput, minToSec, secToMin, toLocalInput } from "./format";
import { AccessCodeField, accessCodeError } from "@/components/lms/accommodations/AccessCodeField"; // Phase 7a S5

function gradingOf(a: AssessmentStaffOut): GradingFormValue {
  return {
    schemeVersionId: a.grading_scheme_version_id,
    categoryId: a.grade_category_id,
    dueAt: toLocalInput(a.due_at),
    release: a.grade_release,
    omit: a.omit_from_total,
  };
}

/** Assessment settings form. Saves with the current draft_rev; 409 draft_conflict asks the parent to reload. */
export function SettingsPanel({
  assessment, courseId, courseLanguages, defaultLanguage, disabled, onSaved, onConflict,
}: {
  assessment: AssessmentStaffOut;
  courseId: string;
  courseLanguages: Lang[];
  defaultLanguage: Lang;
  disabled: boolean;
  onSaved: () => void | Promise<void>;
  onConflict: () => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const a = assessment;
  const [title, setTitle] = useState<LocalizedText>(a.title);
  const [description, setDescription] = useState<LocalizedText>(a.description ?? {});
  const [languages, setLanguages] = useState<Lang[]>(a.languages);
  const [attempts, setAttempts] = useState(String(a.allowed_attempts === -1 ? 1 : a.allowed_attempts));
  const [unlimited, setUnlimited] = useState(a.allowed_attempts === -1);
  const [limit, setLimit] = useState(secToMin(a.time_limit_s));
  const [navigation, setNavigation] = useState<Navigation>(a.navigation);
  const [results, setResults] = useState<ResultsPolicy>(a.results_policy);
  const [showCorrect, setShowCorrect] = useState(a.show_correct_answers);
  const [scorePolicy, setScorePolicy] = useState<ScorePolicy>(a.score_policy);
  const [shuffleItems, setShuffleItems] = useState(a.shuffle_items);
  const [shuffleChoices, setShuffleChoices] = useState(a.shuffle_choices);
  const [from, setFrom] = useState(toLocalInput(a.available_from));
  const [until, setUntil] = useState(toLocalInput(a.available_until));
  const [grading, setGrading] = useState<GradingFormValue>(() => gradingOf(a));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  // --- Phase 6 S4b: locked course template (design §5.4): navigation and grading scheme are fixed ---
  const tplLocked = isAssessmentLocked(useTemplateUi(), a.preset);
  // --- Phase 7a S5: access code (undefined = unchanged, string = set, null = clear; PHASE_7A_DESIGN 2.7) ---
  const [accessCode, setAccessCode] = useState<string | null | undefined>(undefined);
  const accessCodeBad = typeof accessCode === "string" && accessCode.trim() !== "" && !!accessCodeError(accessCode);
  // --- Phase 7a S5 end ---

  // Re-seed when the server copy changes (after reload).
  useEffect(() => {
    setTitle(a.title); setDescription(a.description ?? {}); setLanguages(a.languages);
    setAttempts(String(a.allowed_attempts === -1 ? 1 : a.allowed_attempts)); setUnlimited(a.allowed_attempts === -1);
    setLimit(secToMin(a.time_limit_s)); setNavigation(a.navigation); setResults(a.results_policy);
    setShowCorrect(a.show_correct_answers); setScorePolicy(a.score_policy); setShuffleItems(a.shuffle_items);
    setShuffleChoices(a.shuffle_choices); setFrom(toLocalInput(a.available_from)); setUntil(toLocalInput(a.available_until));
    setGrading(gradingOf(a));
    setAccessCode(undefined); // Phase 7a S5
  }, [a]);

  const toggleLang = (l: Lang) =>
    setLanguages((cur) => (cur.includes(l) ? (cur.length > 1 ? cur.filter((x) => x !== l) : cur) : LMS_LANGS.filter((x) => cur.includes(x) || x === l)));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (accessCodeBad) return; // Phase 7a S5
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await updateAssessment(courseId, a.id, {
        draft_rev: a.draft_rev,
        title: cleanLocalized(title, courseLanguages),
        description: cleanLocalized(description, courseLanguages),
        languages,
        time_limit_s: minToSec(limit),
        allowed_attempts: unlimited ? -1 : Math.max(1, Math.round(Number(attempts) || 1)),
        score_policy: scorePolicy,
        shuffle_items: shuffleItems,
        shuffle_choices: shuffleChoices,
        navigation,
        results_policy: results,
        show_correct_answers: showCorrect,
        available_from: fromLocalInput(from),
        available_until: fromLocalInput(until),
        grading_scheme_version_id: grading.schemeVersionId,
        grade_category_id: grading.categoryId,
        due_at: fromLocalInput(grading.dueAt),
        grade_release: grading.release,
        omit_from_total: grading.omit,
        // Phase 7a S5: sent only when changed (absent = unchanged)
        ...(accessCode === null ? { access_code: null } : typeof accessCode === "string" && accessCode.trim() ? { access_code: accessCode.trim() } : {}),
      });
      setSaved(true);
      await onSaved();
    } catch (err) {
      setError(err);
      if ((err as { code?: string }).code === "draft_conflict") await onConflict();
    } finally {
      setBusy(false);
    }
  };

  const check = (id: string, label: string, v: boolean, set: (b: boolean) => void) => (
    <label className="flex items-center gap-2 text-sm text-slate-700" htmlFor={id}>
      <input id={id} type="checkbox" checked={v} disabled={disabled} onChange={(e) => set(e.target.checked)} />{label}
    </label>
  );

  return (
    <form onSubmit={save} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
      <LocalizedTextInput label={t("assessments.settings.title")} languages={courseLanguages} defaultLanguage={defaultLanguage}
        value={title} onChange={setTitle} maxLength={200} required disabled={disabled} />
      <LocalizedTextInput label={t("assessments.settings.description")} languages={courseLanguages} defaultLanguage={defaultLanguage}
        value={description} onChange={setDescription} multiline disabled={disabled} />
      <fieldset disabled={disabled}>
        <legend className={labelCls}>{t("assessments.settings.languages")}</legend>
        <div className="flex flex-wrap gap-3">
          {courseLanguages.map((l) => (
            <label key={l} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-3 py-2 text-sm">
              <input type="checkbox" checked={languages.includes(l)} onChange={() => toggleLang(l)} />{t(`courses.languages.${l}`)}
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-slate-500">{t("assessments.settings.languagesHint")}</p>
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={labelCls} htmlFor="as-attempts">{t("assessments.settings.attempts")}</label>
          <input id="as-attempts" type="number" min={1} max={100} className={inputCls} disabled={disabled || unlimited} value={attempts} onChange={(e) => setAttempts(e.target.value)} />
          <div className="mt-1">{check("as-unl", t("assessments.settings.unlimited"), unlimited, setUnlimited)}</div>
        </div>
        <div>
          <label className={labelCls} htmlFor="as-limit">{t("assessments.settings.timeLimit")}</label>
          <input id="as-limit" type="number" min={1} max={1440} className={inputCls} disabled={disabled} value={limit} onChange={(e) => setLimit(e.target.value)} />
          <p className="mt-1 text-xs text-slate-500">{t("assessments.settings.timeLimitHint")}</p>
        </div>
        <div>
          <label className={labelCls} htmlFor="as-from">{t("assessments.settings.availableFrom")}</label>
          <input id="as-from" type="datetime-local" className={inputCls} disabled={disabled} value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="as-until">{t("assessments.settings.availableUntil")}</label>
          <input id="as-until" type="datetime-local" className={inputCls} disabled={disabled} value={until} onChange={(e) => setUntil(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="as-nav">{t("assessments.settings.navigation")}</label>
          <select id="as-nav" className={inputCls} disabled={disabled || tplLocked} value={navigation} onChange={(e) => setNavigation(e.target.value as Navigation)}>
            <option value="free">{t("assessments.navigation.free")}</option>
            <option value="section_forward_only">{t("assessments.navigation.section_forward_only")}</option>
          </select>
          {tplLocked && <p className="mt-1 text-xs text-slate-500">{t("templates.lockedNote")}</p>}
        </div>
        <div>
          <label className={labelCls} htmlFor="as-results">{t("assessments.settings.resultsPolicy")}</label>
          <select id="as-results" className={inputCls} disabled={disabled} value={results} onChange={(e) => setResults(e.target.value as ResultsPolicy)}>
            {RESULTS_POLICIES.map((p) => <option key={p} value={p}>{t(`assessments.results.${p}`)}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="as-score">{t("assessments.settings.scorePolicy")}</label>
          <select id="as-score" className={inputCls} disabled={disabled} value={scorePolicy} onChange={(e) => setScorePolicy(e.target.value as ScorePolicy)}>
            {SCORE_POLICIES.map((p) => <option key={p} value={p}>{t(`assessments.scorePolicy.${p}`)}</option>)}
          </select>
        </div>
      </div>
      <div className="space-y-2">
        {check("as-correct", t("assessments.settings.showCorrect"), showCorrect, setShowCorrect)}
        {check("as-shuf-i", t("assessments.settings.shuffleItems"), shuffleItems, setShuffleItems)}
        {check("as-shuf-c", t("assessments.settings.shuffleChoices"), shuffleChoices, setShuffleChoices)}
      </div>
      <SettingsPanelGrading courseId={courseId} assessmentId={a.id} value={grading} onChange={setGrading}
        currentScheme={a.scheme} defaultLanguage={defaultLanguage} disabled={disabled} schemeLocked={tplLocked} />
      {/* --- Phase 7a S5: access code --- */}
      {/* security review 7a / owner Q4: no access codes on ORT preset exams (the server refuses them) */}
      {a.preset === "none" && <AccessCodeField hasCode={!!a.has_access_code} value={accessCode} onChange={setAccessCode} disabled={disabled} />}
      <AssessmentError error={error} />
      <div className="flex items-center gap-3">
        <button type="submit" className={btnPrimary} disabled={disabled || busy}>{busy ? t("lms.common.loading") : t("lms.common.save")}</button>
        {saved && !error && <span role="status" className="text-sm text-emerald-700">{t("assessments.settings.saved")}</span>}
      </div>
    </form>
  );
}
