"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getAssessment, listAssessmentVersions } from "@/lib/lms/assessments";
import { isStaffAssessment, type AssessmentDetailOut, type VersionOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { btnPrimary, btnSecondary } from "@/components/lms/content/ui";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";
import { LobbyView } from "@/components/lms/assessments/LobbyView";
import { PublishPanel } from "@/components/lms/assessments/PublishPanel";
import { sectionName } from "@/components/lms/assessments/SectionCard";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";
import { MyAttemptsPanel } from "@/components/lms/home/MyAttemptsPanel"; // Phase 6 S6b

export default function AssessmentPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const params = useParams<{ assessmentId: string }>();
  const aid = params.assessmentId;
  const canEdit = useCanEditContent();
  const base = `/${lang}/courses/${course.id}/assessments`;
  const [data, setData] = useState<AssessmentDetailOut | null>(null);
  const [versions, setVersions] = useState<VersionOut[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      const out = await getAssessment(course.id, aid);
      setData(out);
      setError(null);
      if (isStaffAssessment(out)) {
        try { setVersions((await listAssessmentVersions(course.id, aid, { limit: 20 })).items); } catch { setVersions([]); }
      }
    } catch (e) {
      setError(e);
    }
  }, [course.id, aid]);
  useEffect(() => { void load(); }, [load]);

  if (error && !data) return <AssessmentError error={error} onRetry={() => void load()} />;
  if (!data) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  // --- Phase 6 S6b begin --- (UX S1: "My attempts" with the result link; first after the last attempt)
  if (!isStaffAssessment(data)) {
    const exhausted = !data.can_start && data.reason === "attempts_exhausted";
    const attempts = <MyAttemptsPanel courseId={course.id} assessmentId={data.id} exhausted={exhausted} />;
    return (
      <div className="space-y-4">
        <Link href={base} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0">{t("assessments.backToList")}</Link>
        {exhausted && attempts}
        <LobbyView lobby={data} />
        {!exhausted && attempts}
      </div>
    );
  }
  // --- Phase 6 S6b end ---

  const a = data;
  const title = pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled");
  return (
    <div className="space-y-4">
      <Link href={base} className="text-sm font-medium text-brand-700 hover:underline">{t("assessments.backToList")}</Link>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-900">{title}</h2>
        <div className="flex gap-2">
          <Link href={`${base}/${a.id}/attempts`} className={btnSecondary}>{t("assessments.overview.attempts")}</Link>
          {canEdit && <Link href={`${base}/${a.id}/edit`} className={btnPrimary}>{t("assessments.list.edit")}</Link>}
        </div>
      </div>
      <PublishPanel assessment={a} courseId={course.id} canEdit={canEdit} onChanged={load} />
      <dl className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-slate-500">{t("assessments.overview.items")}</dt><dd className="font-medium">{a.item_count} · {t("assessments.overview.points", { n: fmtPoints(a.points_possible) })}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("assessments.settings.languages")}</dt><dd className="font-medium">{a.languages.map((l) => l.toUpperCase()).join(", ")}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("assessments.settings.attempts")}</dt><dd className="font-medium">{a.allowed_attempts === -1 ? t("assessments.settings.unlimited") : a.allowed_attempts}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("assessments.settings.timeLimit")}</dt><dd className="font-medium">{a.time_limit_s ? t("assessments.student.minutes", { n: Math.round(a.time_limit_s / 60) }) : t("assessments.lobby.noLimit")}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("assessments.settings.navigation")}</dt><dd className="font-medium">{t(`assessments.navigation.${a.navigation}`)}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("assessments.settings.resultsPolicy")}</dt><dd className="font-medium">{t(`assessments.results.${a.results_policy}`)}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("assessments.settings.availableFrom")}</dt><dd className="font-medium">{a.available_from ? fmtDateTime(a.available_from) : t("assessments.lobby.anytime")}</dd></div>
        <div><dt className="text-xs text-slate-500">{t("assessments.settings.availableUntil")}</dt><dd className="font-medium">{a.available_until ? fmtDateTime(a.available_until) : t("assessments.lobby.noEnd")}</dd></div>
      </dl>
      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-900">{t("assessments.builder.sections")}</h3>
        <ol className="space-y-1 text-sm">
          {a.sections.map((s) => (
            <li key={s.id} className="flex justify-between gap-3">
              <span>{s.position}. {sectionName(s, lang, course.default_language, t)}</span>
              <span className="text-slate-500">{t("assessments.section.itemCount", { n: s.items.length })}{s.time_limit_s ? ` · ${t("assessments.student.minutes", { n: Math.round(s.time_limit_s / 60) })}` : ""}</span>
            </li>
          ))}
        </ol>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-900">{t("assessments.overview.versions")}</h3>
        {versions.length === 0 ? <p className="text-sm text-slate-500">{t("assessments.overview.noVersions")}</p> : (
          <ul className="space-y-1 text-sm">
            {versions.map((v) => (
              <li key={v.id} className="flex flex-wrap justify-between gap-3">
                <span className="font-medium">{t("assessments.list.version", { n: v.version_no })}</span>
                <span className="text-slate-500">
                  {fmtDateTime(v.created_at)}{v.created_by_name ? ` · ${v.created_by_name}` : ""} · {t("assessments.list.attempts", { inProgress: v.attempt_counts.in_progress, submitted: v.attempt_counts.submitted })}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
