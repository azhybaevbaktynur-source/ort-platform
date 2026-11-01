"use client";

// UX rework D (UR-4): "To grade" on the teacher Course page (`GET _C/todo`). A short list from `xl`, one line link below
// it; both appear only when something waits. Each row opens the assignment's Submissions tab filtered to "to grade",
// never Grades. It reloads on window focus and when `refreshKey` changes (after outline writes). A failed load shows
// nothing: this is a shortcut, the Assignments list has the same counts.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { withFrom } from "@/lib/lms/nav";
import { getTodo } from "@/lib/lms/todo";
import type { CourseStaffOut, TodoOut } from "@/lib/lms/types";
import { cn, focusRing } from "@/components/ui";

const linkCls = cn("rounded font-medium text-brand-700 underline-offset-2 hover:text-brand-800 hover:underline", focusRing);

export function useToGrade(courseId: string, refreshKey: number): TodoOut | null {
  const [data, setData] = useState<TodoOut | null>(null);
  const reload = useCallback(async () => {
    try {
      setData(await getTodo(courseId));
    } catch {
      setData(null);
    }
  }, [courseId]);
  useEffect(() => { void reload(); }, [reload, refreshKey]);
  useEffect(() => {
    const onFocus = () => { void reload(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [reload]);
  return data;
}

export function ToGradeLine({ courseId, data, className }: { courseId: string; data: TodoOut; className?: string }) {
  const { lang, t } = useTranslation();
  return (
    <Link href={`/${lang}/courses/${courseId}/assignments?needs_grading=1`}
      className={cn("flex min-h-11 items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-brand-700 hover:bg-slate-50", focusRing, className)}>
      {t("todo.toGradeCount", { n: data.to_grade_total })}
      <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0" />
    </Link>
  );
}

export function ToGradeColumn({ course, data, className }: { course: CourseStaffOut; data: TodoOut; className?: string }) {
  const { lang, t } = useTranslation();
  const base = `/${lang}/courses/${course.id}`;
  return (
    <aside aria-labelledby="to-grade-title" className={className}>
      <h2 id="to-grade-title" className="mb-2 text-base font-semibold leading-6 text-slate-900">{t("todo.toGrade")}</h2>
      <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        {data.to_grade.map((g) => (
          <li key={g.assignment_id} className="px-3 py-2 text-sm leading-5">
            <Link href={withFrom(`${base}/assignments/${g.assignment_id}?tab=submissions&filter=to_grade`, base)} className={cn(linkCls, "break-words")}>
              {pickLocalized(g.title, lang, course.default_language) || t("assignments.untitled")}
            </Link>
            <span className="block text-slate-600">{t("todo.waiting", { n: g.needs_grading })}</span>
          </li>
        ))}
      </ul>
      {data.to_grade_total > data.to_grade.length && (
        <Link href={`${base}/assignments?needs_grading=1`} className={cn(linkCls, "mt-2 inline-flex text-sm")}>
          {t("todo.more", { n: data.to_grade_total - data.to_grade.length })}
        </Link>
      )}
    </aside>
  );
}
