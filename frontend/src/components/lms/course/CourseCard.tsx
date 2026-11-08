"use client";

// The one course card: student dashboard, catalog, Teaching list and trash (F7c, STUDENT_UI_FIX_PLAN 7.2). A low
// cover (150 px) on top, the title (two lines), one meta line "Russian · 12 tests · 8 lessons" (zero parts left out), the teacher
// and organization only for a course that is not the platform's, then a two-line description, or for a joined course
// the progress bar. One action. The title is the link and stretches over the card, so the action slot can hold its own
// controls (a link inside a link is invalid). The action sits at the bottom, so cards in a grid align.
import React from "react";
import Link from "next/link";
import { CalendarClock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { cn } from "@/components/ui";
import { fmtDayMonthTime, isDueSoon } from "@/components/lms/home/format";
import { CourseCardCover } from "./CourseCardCover";

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

/** The one grid of course cards (FB8-1): 1 column below 768 px, 2 from 768, 3 from 1200, 4 from 1600 (viewport widths); cards are at most 360 px wide and stay left-aligned. */
export const COURSE_GRID =
  "grid grid-cols-1 gap-4 min-[768px]:grid-cols-[repeat(2,minmax(0,360px))] min-[1200px]:grid-cols-[repeat(3,minmax(0,360px))] min-[1600px]:grid-cols-[repeat(4,minmax(0,360px))]";

export interface CourseCardData {
  id: string;
  title: LocalizedText;
  description?: LocalizedText | null;
  languages: Lang[];
  default_language: Lang;
  owner_display_name?: string | null;
  /** root organization; null for a personal one, whose name means nothing to students */
  organization_display_name?: string | null;
  /** a platform course shows no teacher or organization line */
  is_platform_course?: boolean;
  cover_url?: string | null;
  tests_count?: number;
  lessons_count?: number;
  /** F7: a platform course with a published paid test: a quiet gold "Pro" mark */
  has_paid_tests?: boolean;
}

function Progress({ done, total }: { done: number; total: number }) {
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

export function CourseCard({ course, href, headingLevel = 3, badges, progress, nextDue, action }: {
  course: CourseCardData;
  /** where the card leads; null: a card that opens nothing (a course in the trash) */
  href: string | null;
  headingLevel?: 2 | 3;
  /** only badges that matter: "Pro", "by code", "application"; the staff list adds its status */
  badges?: React.ReactNode;
  /** joined course: the bar replaces the description (null: nothing to finish, the description stays) */
  progress?: { done: number; total: number } | null;
  nextDue?: string | null;
  action?: React.ReactNode;
}) {
  const { lang, t } = useTranslation();
  const uiLang = lang as Lang;
  const title = pickLocalized(course.title, uiLang, course.default_language) || t("courses.list.untitled");
  const description = pickLocalized(course.description, uiLang, course.default_language);
  const owner = course.owner_display_name && course.owner_display_name !== "—" ? course.owner_display_name : null;
  const people = course.is_platform_course ? null : [owner, course.organization_display_name || null].filter(Boolean).join(" · ") || null;
  const meta = [
    course.languages.map((l) => t(`courses.languages.${l}`)).join(", "),
    course.tests_count ? t("courses.card.tests", { count: course.tests_count }) : null,
    course.lessons_count ? t("courses.card.lessons", { count: course.lessons_count }) : null,
  ].filter(Boolean).join(" · ");
  const soon = isDueSoon(nextDue);
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <li className="group relative flex min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      <CourseCardCover card courseId={course.id} coverUrl={course.cover_url} platform={course.is_platform_course} />
      <div className="flex flex-1 flex-col gap-2 px-4 py-3">
        {(badges || course.has_paid_tests) && (
          <div className="flex flex-wrap items-center gap-2">
            {course.has_paid_tests && (
              <span title={t("courses.card.proHint")} data-testid="course-card-pro"
                className="inline-flex items-center rounded-full border border-gold-200 bg-gold-50 px-2 py-0.5 text-xs font-semibold leading-5 text-gold-800">
                {t("courses.card.pro")}<span className="sr-only">{` (${t("courses.card.proHint")})`}</span>
              </span>
            )}
            {badges}
          </div>
        )}
        <Heading title={title} className="line-clamp-2 min-w-0 break-words text-base font-semibold leading-6 text-slate-900">
          {href
            ? (
              <Link href={href}
                className="rounded after:absolute after:inset-0 after:rounded-2xl group-hover:text-brand-700 focus:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-brand-500">
                {title}
              </Link>
            )
            : title}
        </Heading>
        <p title={meta} className="truncate text-sm leading-5 text-slate-600">{meta}</p>
        {people && <p title={people} className="truncate text-sm leading-5 text-slate-600">{people}</p>}
        {progress
          ? <Progress done={progress.done} total={progress.total} />
          : description ? <p className="line-clamp-2 break-words text-sm leading-5 text-slate-600">{description}</p> : null}
        {(nextDue || action) && (
          <div className="mt-auto space-y-2 pt-1">
            {nextDue && (
              <p className={cn("flex items-center gap-1.5 text-sm leading-5", soon ? "font-medium text-danger-700" : "text-slate-600")}>
                <CalendarClock aria-hidden="true" className={cn("h-4 w-4 shrink-0", soon ? "text-danger-700" : "text-slate-500")} />
                <span className="min-w-0 truncate">{t("home.todo.due", { date: fmtDayMonthTime(nextDue, lang) })}</span>
              </p>
            )}
            {action && <div className="relative z-10 pt-1">{action}</div>}
          </div>
        )}
      </div>
    </li>
  );
}
