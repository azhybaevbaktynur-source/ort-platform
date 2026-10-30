"use client";

// Phase 6b S5c: shared pieces of the staff course screens on the design system (course bar, badges, crumbs).
import React from "react";
import Link from "next/link";
import { ChevronRight, Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { templateTitle, templateUi } from "@/lib/lms/templates";
import type { CourseOut } from "@/lib/lms/types";
import { Badge, type BadgeTone, type Breadcrumb, focusRing, cn } from "@/components/ui";
import { StudentViewButton } from "./StudentViewBanner"; // Phase 8c S1

const COURSE_TONE: Record<string, BadgeTone> = { draft: "warning", published: "success", concluded: "neutral" };

export function CourseStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return <Badge tone={COURSE_TONE[status] ?? "neutral"}>{t(`courses.status.${status}`)}</Badge>;
}

const ASSESSMENT_TONE: Record<string, BadgeTone> = { draft: "neutral", published: "success" };

export function AssessmentStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return <Badge tone={ASSESSMENT_TONE[status] ?? "neutral"}>{t(`assessments.status.${status}`)}</Badge>;
}

/** "Fixed by the template" badge of a locked course template (ORT), so staff do not look for missing buttons. */
export function TemplateLockBadge({ course }: { course: Pick<CourseOut, "template"> }) {
  const { t } = useTranslation();
  const ui = templateUi(course);
  if (!ui.locked || !ui.key) return null;
  const name = templateTitle(t, ui.key);
  return (
    <Badge tone="neutral" icon={<Lock aria-hidden="true" />} title={t("templates.lockedHint")}>
      {t("teaching.templateBadge", { name })}
    </Badge>
  );
}

/**
 * Staff course bar (above the course tabs): "My courses ›" crumb, course title and badges.
 * The page below owns the one `<h1>` (design-system `PageHeader`).
 */
export function StaffCourseBar({ course, titleAsHeading = false, studentViewButton = false }: {
  course: CourseOut;
  /** Phase 8c S1 (§2.4): on the Course page the course title is the page `<h1>`; elsewhere it links to the course. */
  titleAsHeading?: boolean;
  /** Phase 8c S1 (§2.4, §6): the right-aligned "Student view" button (teacher and assistant; never in a sandbox). */
  studentViewButton?: boolean;
}) {
  const { lang, t } = useTranslation();
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const titleClass = "min-w-0 break-words rounded text-xl font-bold leading-7 text-slate-900";
  return (
    <div className="mb-3">
      <nav aria-label={t("ui.breadcrumbs")}>
        <ol className="flex flex-wrap items-center gap-1 text-sm leading-6 text-slate-600">
          <li className="inline-flex items-center gap-1">
            <Link href={`/${lang}/courses`} className={cn("inline-flex min-h-11 items-center rounded font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
              {t("courses.list.title")}
            </Link>
            <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" />
          </li>
        </ol>
      </nav>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-2">
        {titleAsHeading ? (
          <h1 className={titleClass}>{title}</h1>
        ) : (
          <Link href={`/${lang}/courses/${course.id}`} className={cn(titleClass, "hover:text-brand-700", focusRing)}>
            {title}
          </Link>
        )}
        <CourseStatusBadge status={course.status} />
        <TemplateLockBadge course={course} />
        {studentViewButton && <div className="w-full sm:ml-auto sm:w-auto"><StudentViewButton courseId={course.id} /></div>}
      </div>
    </div>
  );
}

/** Breadcrumbs of a page under a course tab: the tab root, then the given crumbs (the last one is the current page).
 * Phase 8c S1 (§4.2): the Tests list is gone, so "assessments" pages (quiz builder, ORT builder, results) start with
 * the Assignments crumb. */
export function useTabCrumbs(tab: "assessments" | "bank" | "people" | "grades", rest: Breadcrumb[], courseId: string): Breadcrumb[] {
  const { lang, t } = useTranslation();
  const labels = { assessments: t("assignments.tab"), bank: t("bank.tab"), people: t("courses.people.tab"), grades: t("gradebook.tab") };
  const path = tab === "assessments" ? "assignments" : tab;
  return [{ label: labels[tab], href: `/${lang}/courses/${courseId}/${path}` }, ...rest];
}

/** Count line of a cursor-paginated list: "Found: N" when complete, "Shown: N" while more pages exist. */
export function useListCount() {
  const { t } = useTranslation();
  return (n: number, hasMore: boolean) => (hasMore ? t("teaching.shown", { n }) : t("ui.table.count", { count: n }));
}
