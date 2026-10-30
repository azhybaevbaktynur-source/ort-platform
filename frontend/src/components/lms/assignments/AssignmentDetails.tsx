"use client";

// Phase 8c S3 (PHASE_8C_DESIGN §5.1): the Details tab of the assignment page: a read-only summary (kind, dates, points,
// category, grade release, hand-in counts), the modules that list the assignment ("Used in modules"), the
// student-facing instructions and, for a quiz, the way to its questions ("Edit questions", with `from`) and to its
// publishing and versions.
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { getModules } from "@/lib/lms/modules";
import type { AssignmentStaffOut } from "@/lib/lms/assignmentTypes";
import type { ModulesStaffOut } from "@/lib/lms/modulesTypes";
import type { LocalizedText } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { withFrom } from "@/lib/lms/nav";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { MathRenderer } from "@/components/math/MathRenderer";
import { Card, DescriptionList, LinkButton, type DescriptionItem } from "@/components/ui";
import { KindBadge, fmtPts } from "./assignmentUi";
import type { ObjectNav } from "./objectNav";
import { useCategories } from "./useCategories";

interface UsedIn { id: string; title: LocalizedText }

export function AssignmentDetails({ assignment: a, nav }: { assignment: AssignmentStaffOut; nav: ObjectNav }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const categories = useCategories(course.id);
  const base = `/${lang}/courses/${course.id}`;
  // null = unknown (loading, modules unavailable in this course or the request failed): the row is left out
  const [usedIn, setUsedIn] = useState<UsedIn[] | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getModules(course.id, { signal: ctrl.signal })
      .then((out) => {
        const mods = (out as ModulesStaffOut).modules ?? [];
        setUsedIn(mods.filter((m) => !m.deleted_at && (m.items ?? []).some((i) => i.assignment_id === a.id))
          .map((m) => ({ id: m.id, title: m.title })));
      })
      .catch(() => { if (!ctrl.signal.aborted) setUsedIn(null); });
    return () => ctrl.abort();
  }, [course.id, a.id]);

  const quiz = a.kind === "quiz";
  const ort = !!a.assessment?.preset && a.assessment.preset !== "none";
  const when = (v: string | null) => (v ? fmtShortDateTime(v, lang) : "—");
  const category = a.category_id ? categories.find((c) => c.id === a.category_id) : null;
  const description = pickLocalized(a.description, lang, course.default_language);

  const items: DescriptionItem[] = [
    { key: "kind", term: t("assignments.list.colKind"), description: <KindBadge kind={a.kind} ort={ort} /> },
    { key: "due", term: t("assignments.fields.due"), description: when(a.due_at) },
    { key: "from", term: t("assignments.fields.availableFrom"), description: when(a.available_from) },
    { key: "until", term: t("assignments.fields.availableUntil"), description: when(a.available_until) },
    { key: "points", term: t("assignments.fields.points"), description: fmtPts(a.points_possible) || "—" },
    {
      key: "category", term: t("grading.settings.category"),
      description: category ? pickLocalized(category.title, lang, course.default_language) || "—" : t("grading.settings.noCategory"),
    },
    { key: "release", term: t("grading.settings.release"), description: t(`grading.settings.releaseModes.${a.grade_release}`) },
  ];
  if (usedIn) {
    items.push({
      key: "modules", term: t("assignments.page.usedIn"),
      description: usedIn.length === 0 ? t("assignments.page.usedInNone") : (
        <span className="flex flex-wrap gap-x-3 gap-y-1">
          {usedIn.map((m) => (
            <Link key={m.id} href={`${base}#m-${m.id}`} className="break-words font-medium text-brand-700 hover:underline">
              {pickLocalized(m.title, lang, course.default_language) || t("assignments.untitled")}
            </Link>
          ))}
        </span>
      ),
    });
  }
  const counts: DescriptionItem[] = [
    { key: "submitted", term: t("assignments.page.counts.submitted"), description: a.counts.submitted },
    { key: "needs", term: t("assignments.page.counts.needsGrading"), description: a.counts.needs_grading },
    { key: "graded", term: t("assignments.page.counts.graded"), description: a.counts.graded },
    { key: "released", term: t("assignments.page.counts.released"), description: a.counts.released },
  ];

  return (
    <div className="space-y-4">
      {quiz && a.assessment_id && (
        <Card title={t("assignments.page.quizTitle")} description={t("assignments.page.quizHint")}>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap [&>*]:w-full sm:[&>*]:w-auto">
            <LinkButton href={withFrom(`${base}/assessments/${a.assessment_id}/edit`, nav.here)}>
              {canEdit ? t("assignments.page.editQuestions") : t("assignments.page.viewQuestions")}
            </LinkButton>
            <LinkButton variant="secondary" href={`${base}/assessments/${a.assessment_id}`}>{t("assignments.page.publishing")}</LinkButton>
          </div>
        </Card>
      )}
      <Card title={t("assignments.page.summary")}>
        <DescriptionList items={items} twoColumns />
      </Card>
      <Card title={t("assignments.page.progress")}>
        <DescriptionList items={counts} twoColumns />
        {!quiz && a.counts.needs_grading > 0 && (
          <div className="mt-4 [&>*]:w-full sm:[&>*]:w-auto">
            <LinkButton variant="secondary" href={`${base}/assignments/${a.id}?${new URLSearchParams({ tab: "submissions", filter: "to_grade", ...(nav.from ? { from: nav.from } : {}) })}`}>
              {t("assignments.page.gradeNow", { n: a.counts.needs_grading })}
            </LinkButton>
          </div>
        )}
      </Card>
      <Card title={t("assignments.fields.instructions")}>
        {description
          ? <MathRenderer content={description} className="whitespace-pre-line break-words text-base sm:text-sm" />
          : <p className="text-sm text-slate-600">{t("assignments.page.noInstructions")}</p>}
      </Card>
    </div>
  );
}
