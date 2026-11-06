"use client";

import React from "react";
import { Award } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { AttemptResultOut } from "@/lib/lms/attemptTypes";
import type { AttemptGradeOut } from "@/lib/lms/gradingTypes";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";
import { fmtNum, fmtPercentile } from "@/components/lms/grading/schemes/params";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { Badge, Mascot, type MascotPose } from "@/components/ui";
import { useGradeText } from "./GradeBadge";

/**
 * SF-1 (STUDENT_UI_FIX_PLAN §2.2 items 2–4 with the §10 overrides): the top of a result card. The cub on the left
 * (celebrating from 80 % of the raw points, hello from 50 %, encouraging below; `data-testid="result-mascot"`), the big
 * score with its scale, one line of meaning from server data only (the percentile when above 0, thresholds the server
 * set, e.g. the golden certificate), and the raw points. A scaled grade with no correct answer (D6) reads "0" with
 * one plain sentence and no percentile or pass/fail. Pass/fail shows only with `showPass` (never on exam-prep student
 * pages); "counts towards the grade" is never shown here (staff views keep it).
 */
export function ExamResultHero({ result, grade, scaled, showPass, showMascot }: {
  result: AttemptResultOut;
  grade: AttemptGradeOut | null;
  /** The ORT-style view: the grade's scaled value is the big number. */
  scaled: boolean;
  showPass: boolean;
  showMascot: boolean;
}) {
  const { lang, t } = useTranslation();
  const label = useSchemeLabel();
  const gradeText = useGradeText();
  const raw = Number(result.raw_score);
  const possible = Number(result.points_possible);
  const ratio = possible > 0 && Number.isFinite(raw) ? raw / possible : NaN;
  const pose: MascotPose | null = !showMascot || !Number.isFinite(ratio) ? null
    : ratio >= 0.8 ? "celebrating" : ratio >= 0.5 ? "hello" : "encouraging";
  const caption = pose === "celebrating" ? "mascot.result.proud" : pose === "hello" ? "mascot.result.good" : "mascot.result.encourage";

  const scaleMin = fmtNum(grade?.scale_min);
  const scaleMax = fmtNum(grade?.scale_max);
  // D6: a scaled grade of 0 because nothing was correct (the scheme's zero rule; data unchanged)
  const zeroRaw = scaled && !!grade && raw === 0 && Number(grade.display_value) === 0;
  const pct = grade && !zeroRaw && Number(grade.percentile) > 0 ? fmtPercentile(grade.percentile) : "";
  const flags = Object.entries(grade?.thresholds ?? {}).filter(([, on]) => on).map(([k]) => k);
  const passed = showPass && !zeroRaw && grade && grade.passed !== null && grade.passed !== undefined && grade.scheme_type !== "pass_fail"
    ? grade.passed : null;

  let value: string;
  let scaleLine = "";
  if (scaled && grade) {
    value = fmtNum(grade.display_value) || "—";
    scaleLine = scaleMin && scaleMax ? t("results.hero.scale", { min: scaleMin, max: scaleMax }) : "";
  } else if (grade) {
    value = gradeText(grade, grade.scheme_type) || "—";
    if (grade.scheme_type !== "percent" && scaleMax && scaleMin) scaleLine = t("results.hero.scale", { min: scaleMin, max: scaleMax });
  } else {
    value = fmtPoints(result.raw_score);
    scaleLine = t("results.hero.outOf", { max: fmtPoints(result.points_possible) });
  }
  const valueLabel = scaled ? t("results.hero.scaledLabel") : grade ? t("results.grade.title") : t("results.rawScore");

  const score = (
    <div className="min-w-0 flex-1" role="group" aria-label={t("results.grade.title")}>
      <p className="text-sm font-medium text-slate-600">{valueLabel}</p>
      <p className="break-words text-5xl font-bold leading-none tracking-tight tabular-nums text-slate-900 sm:text-[56px]">{value}</p>
      {scaleLine && <p className="mt-2 text-sm text-slate-600">{scaleLine}</p>}
    </div>
  );

  return (
    <div className="space-y-4">
      {result.submitted_at && (
        <p className="text-xs text-slate-600">{t("results.submittedAt", { date: fmtDateTime(result.submitted_at, lang) })}</p>
      )}
      {pose ? (
        <div data-testid="result-mascot" className="space-y-3">
          <div className="flex items-center gap-4 sm:gap-6">
            <Mascot pose={pose} size={96} className="h-20 w-auto shrink-0 sm:h-24" />
            {score}
          </div>
          <p className="text-sm font-medium text-slate-700">{t(caption)}</p>
        </div>
      ) : score}
      {zeroRaw && (
        <p className="rounded-control border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-800">
          {t("results.hero.zeroRaw", { min: scaleMin || "0" })}
        </p>
      )}
      {pct && <p className="text-sm text-slate-700">{t("results.hero.percentile", { value: pct })}</p>}
      {grade && (
        <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-slate-700">
          <span>{t("results.rawScore")}</span>
          <span className="font-semibold tabular-nums text-slate-900">{fmtPoints(result.raw_score)} / {fmtPoints(result.points_possible)}</span>
        </p>
      )}
      {(flags.length > 0 || passed !== null || (grade && !grade.released)) && (
        <div className="flex flex-wrap items-center gap-2">
          {flags.map((k) => (
            <Badge key={k} tone="warning" icon={<Award aria-hidden="true" />}>{label(k, grade?.labels)}</Badge>
          ))}
          {passed !== null && <Badge tone={passed ? "success" : "danger"}>{label(passed ? "pass" : "fail")}</Badge>}
          {grade && !grade.released && <Badge tone="neutral">{t("results.grade.notReleased")}</Badge>}
        </div>
      )}
    </div>
  );
}
