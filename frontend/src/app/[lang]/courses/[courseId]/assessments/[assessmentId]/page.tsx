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
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi"; // Phase 6b S5c
import { Card, DescriptionList, EmptyState, LinkButton, PageHeader } from "@/components/ui";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";
import { LobbyView } from "@/components/lms/assessments/LobbyView";
import { PublishPanel, publishIsPrimary } from "@/components/lms/assessments/PublishPanel";
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
  const staffTitle = data && isStaffAssessment(data) ? pickLocalized(data.title, lang, course.default_language) || t("assessments.untitled") : "";
  const crumbs = useTabCrumbs("assessments", [{ label: staffTitle || t("lms.common.loading") }], course.id);

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
  const title = staffTitle;
  // Phase 6b S5c (UX T8): one primary per page: "Publish changes" (in the publish panel) when that is the next step, else "Edit".
  const editPrimary = canEdit && !publishIsPrimary(a);
  const editLink = canEdit ? <LinkButton variant={editPrimary ? "primary" : "secondary"} href={`${base}/${a.id}/edit`}>{t("assessments.list.edit")}</LinkButton> : undefined;
  return (
    <div className="space-y-4">
      <PageHeader breadcrumbs={crumbs} title={title} className="mb-2"
        secondaryActions={<>
          <LinkButton variant="secondary" href={`${base}/${a.id}/attempts`}>{t("assessments.overview.attempts")}</LinkButton>
          {!editPrimary && editLink}
        </>}
        primaryAction={editPrimary ? editLink : undefined} />
      <PublishPanel assessment={a} courseId={course.id} canEdit={canEdit} onChanged={load} />
      <Card padding="md">
        <DescriptionList twoColumns items={[
          { term: t("assessments.overview.items"), description: `${a.item_count} · ${t("assessments.overview.points", { n: fmtPoints(a.points_possible) })}` },
          { term: t("assessments.settings.languages"), description: a.languages.map((l) => l.toUpperCase()).join(", ") },
          { term: t("assessments.settings.attempts"), description: a.allowed_attempts === -1 ? t("assessments.settings.unlimited") : a.allowed_attempts },
          { term: t("assessments.settings.timeLimit"), description: a.time_limit_s ? t("assessments.student.minutes", { n: Math.round(a.time_limit_s / 60) }) : t("assessments.lobby.noLimit") },
          { term: t("assessments.settings.navigation"), description: t(`assessments.navigation.${a.navigation}`) },
          { term: t("assessments.settings.resultsPolicy"), description: t(`assessments.results.${a.results_policy}`) },
          { term: t("assessments.settings.availableFrom"), description: a.available_from ? fmtDateTime(a.available_from) : t("assessments.lobby.anytime") },
          { term: t("assessments.settings.availableUntil"), description: a.available_until ? fmtDateTime(a.available_until) : t("assessments.lobby.noEnd") },
        ]} />
      </Card>
      <Card title={t("assessments.builder.sections")}>
        {a.sections.length === 0 ? (
          <EmptyState variant="plain" className="py-4" title={t("assessments.builder.noSections")}
            action={canEdit ? <LinkButton variant="secondary" href={`${base}/${a.id}/edit`}>{t("assessments.list.edit")}</LinkButton> : undefined} />
        ) : (
        <ol className="space-y-1 text-sm">
          {a.sections.map((s) => (
            <li key={s.id} className="flex justify-between gap-3">
              <span>{s.position}. {sectionName(s, lang, course.default_language, t)}</span>
              <span className="shrink-0 text-slate-600">{t("assessments.section.itemCount", { n: s.items.length })}{s.time_limit_s ? ` · ${t("assessments.student.minutes", { n: Math.round(s.time_limit_s / 60) })}` : ""}</span>
            </li>
          ))}
        </ol>
        )}
      </Card>
      <Card title={t("assessments.overview.versions")}>
        {versions.length === 0 ? <p className="text-sm text-slate-600">{t("assessments.overview.noVersions")}</p> : (
          <ul className="space-y-1 text-sm">
            {versions.map((v) => (
              <li key={v.id} className="flex flex-wrap justify-between gap-3">
                <span className="font-medium">{t("assessments.list.version", { n: v.version_no })}</span>
                <span className="text-slate-600">
                  {fmtDateTime(v.created_at)}{v.created_by_name ? ` · ${v.created_by_name}` : ""} · {t("assessments.list.attempts", { inProgress: v.attempt_counts.in_progress, submitted: v.attempt_counts.submitted })}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
