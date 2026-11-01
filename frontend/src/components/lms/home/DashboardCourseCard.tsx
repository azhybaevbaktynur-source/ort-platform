"use client";

// UX rework (UX_REWORK_DESIGN C): one course on the dashboard. The whole card is the link: a colored band with the
// course name, then the teacher and, when set, the next due date.
import React from "react";
import Link from "next/link";
import { CalendarClock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { courseColor } from "@/lib/lms/courseColor";
import { cn, focusRing } from "@/components/ui";
import { fmtDayMonthTime } from "./format";

export function DashboardCourseCard({ id, title, teacher, nextDue }: {
  id: string;
  title: string;
  teacher: string | null;
  nextDue?: string | null;
}) {
  const { lang, t } = useTranslation();
  return (
    <li className="min-w-0">
      <Link href={`/${lang}/courses/${id}`}
        className={cn("group flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md", focusRing)}>
        <span className="flex h-24 shrink-0 items-end px-4 py-3" style={{ backgroundColor: courseColor(id) }}>
          <span title={title} className="line-clamp-2 break-words text-base font-semibold leading-6 text-white group-hover:underline">{title}</span>
        </span>
        <span className="flex flex-1 flex-col gap-1 px-4 py-3 sm:min-h-[4.5rem] text-sm leading-5">
          {teacher && <span className="truncate text-slate-700">{teacher}</span>}
          {nextDue && (
            <span className="inline-flex items-center gap-1.5 text-slate-600">
              <CalendarClock aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
              <span className="min-w-0 truncate">{t("home.todo.due", { date: fmtDayMonthTime(nextDue, lang) })}</span>
            </span>
          )}
        </span>
      </Link>
    </li>
  );
}
