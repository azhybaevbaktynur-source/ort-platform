"use client";

// The one course card: student dashboard, catalog, Teaching list and trash. A colored band with the title (same color
// for a course everywhere), teacher, organization and language, a two-line description; joined courses add progress and
// the next due date. The title is the link and stretches over the card, so the action slot can hold its own controls
// (a link inside a link is invalid). Every row keeps its height when its content is missing, so cards in a grid align.
import React from "react";
import Link from "next/link";
import { CalendarClock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { cn } from "@/components/ui";
import { fmtDayMonthTime, isDueSoon } from "@/components/lms/home/format";

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-amber-100 text-amber-800",
  published: "bg-emerald-100 text-emerald-800",
  concluded: "bg-slate-200 text-slate-700",
};

export function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLE[status] ?? "bg-slate-100 text-slate-700"}`}>
      {t(`courses.status.${status}`)}
    </span>
  );
}

/** Grid of cards for a full-width page; the dashboard has a narrower column and its own breakpoints. */
export const COURSE_GRID = "grid gap-4 sm:grid-cols-2 lg:grid-cols-3 min-[1700px]:grid-cols-4";

export interface CourseCardData {
  id: string;
  title: LocalizedText;
  description?: LocalizedText | null;
  languages: Lang[];
  default_language: Lang;
  owner_display_name?: string | null;
  /** root organization; null for a personal one, whose name means nothing to students */
  organization_display_name?: string | null;
  /** a platform course shows the platform organization, not its owner */
  is_platform_course?: boolean;
}

function Progress({ courseId, done, total }: { courseId: string; done: number; total: number }) {
  const { t } = useTranslation();
  const label = t("modules.progressCount", { done, total });
  return (
    <div>
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}
        className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-brand-600" style={{ width: `${total > 0 ? Math.min(100, (done / total) * 100) : 0}%` }} />
      </div>
      <p aria-hidden="true" className="mt-1 text-xs leading-5 text-slate-600">{label}</p>
    </div>
  );
}

export function CourseCard({ course, href, headingLevel = 3, badges, progress, nextDue, meta, action }: {
  course: CourseCardData;
  /** where the card leads; null: a card that opens nothing (a course in the trash) */
  href: string | null;
  headingLevel?: 2 | 3;
  badges?: React.ReactNode;
  progress?: { done: number; total: number } | null;
  nextDue?: string | null;
  /** one more quiet line, e.g. the student count in the catalog */
  meta?: React.ReactNode;
  action?: React.ReactNode;
}) {
  const { lang, t } = useTranslation();
  const uiLang = lang as Lang;
  const title = pickLocalized(course.title, uiLang, course.default_language) || t("courses.list.untitled");
  const description = pickLocalized(course.description, uiLang, course.default_language);
  const owner = course.owner_display_name && course.owner_display_name !== "—" ? course.owner_display_name : null;
  const teacher = course.is_platform_course ? null : owner;
  // a platform course shows the platform's name in the UI language, not the stored organization name (UR2-5)
  const organization = course.is_platform_course ? t("common.appName") : course.organization_display_name || null;
  const languages = course.languages.map((l) => t(`courses.languages.${l}`)).join(", ");
  const soon = isDueSoon(nextDue);
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <li className="group relative flex min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      <div className="flex h-24 shrink-0 items-end bg-gradient-to-br from-brand-700 to-brand-500 px-4 py-3">
        <Heading title={title} className="line-clamp-2 min-w-0 break-words text-base font-semibold leading-6 text-white">
          {href
            ? (
              <Link href={href}
                className="rounded after:absolute after:inset-0 after:rounded-2xl group-hover:underline focus:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-brand-500">
                {title}
              </Link>
            )
            : title}
        </Heading>
      </div>
      <div className="flex flex-1 flex-col gap-2 px-4 py-3">
        {badges && <div className="flex flex-wrap items-center gap-2">{badges}</div>}
        {/* three rows of height from `sm`, so the descriptions of a row start level with or without an organization */}
        <div className="text-sm leading-5 sm:min-h-[3.75rem]">
          <p title={teacher ?? organization ?? undefined} className="min-h-5 truncate font-medium text-slate-800">{teacher ?? organization}</p>
          {teacher && organization && <p title={organization} className="truncate text-slate-600">{organization}</p>}
          <p title={languages} className="truncate text-slate-600">{languages}</p>
        </div>
        <p className="line-clamp-2 break-words text-sm leading-5 text-slate-600 sm:min-h-10">{description}</p>
        {(progress || nextDue || meta || action) && (
          <div className="mt-auto space-y-2 pt-1">
            {progress && <Progress courseId={course.id} done={progress.done} total={progress.total} />}
            {nextDue && (
              <p className={cn("flex items-center gap-1.5 text-sm leading-5", soon ? "font-medium text-danger-700" : "text-slate-600")}>
                <CalendarClock aria-hidden="true" className={cn("h-4 w-4 shrink-0", soon ? "text-danger-700" : "text-slate-500")} />
                <span className="min-w-0 truncate">{t("home.todo.due", { date: fmtDayMonthTime(nextDue, lang) })}</span>
              </p>
            )}
            {meta && <div className="text-sm leading-5 text-slate-600">{meta}</div>}
            {action && <div className="relative z-10 pt-1">{action}</div>}
          </div>
        )}
      </div>
    </li>
  );
}
