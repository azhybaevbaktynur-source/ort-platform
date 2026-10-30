"use client";

// Phase 8c S2 (PHASE_8C_DESIGN §3.5): the teacher Course page "To do" panel (`GET _C/todo`, S1). Sections, each
// omitted when empty: To grade (links to the assignment's Submissions tab filtered to "to grade", never to Grades),
// Drafts (assignments and quizzes, plus the unpublished modules count), the join code (teachers only) and the active
// students. Below `lg` the panel is one line ("To grade: 3 · Drafts: 2") that expands in place. It reloads on window
// focus and when `refreshKey` changes (after outline writes).
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { withFrom } from "@/lib/lms/nav";
import { getTodo } from "@/lib/lms/todo";
import type { CourseStaffOut, TodoOut } from "@/lib/lms/types";
import { JoinCodeDisplay } from "@/components/lms/JoinCodeDisplay";
import { useModuleErrorText } from "@/components/lms/modules/moduleUi";
import { Button, Skeleton, cn, focusRing } from "@/components/ui";

const linkCls = cn("rounded font-medium text-brand-700 underline-offset-2 hover:text-brand-800 hover:underline", focusRing);

export function TodoPanel({ course, refreshKey = 0, className, compact = false }: {
  course: CourseStaffOut; refreshKey?: number; className?: string;
  /** Phase 8c UX M7 (ORT courses): the one-line form that expands in place, at every width (no column). */
  compact?: boolean;
}) {
  const { lang, t } = useTranslation();
  const errorText = useModuleErrorText();
  const base = `/${lang}/courses/${course.id}`;
  const [data, setData] = useState<TodoOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [open, setOpen] = useState(false);

  const reload = useCallback(async () => {
    try {
      setData(await getTodo(course.id));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [course.id]);
  useEffect(() => { void reload(); }, [reload, refreshKey]);
  useEffect(() => {
    const onFocus = () => { void reload(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [reload]);

  const title = (v: TodoOut["to_grade"][number]["title"]) => pickLocalized(v, lang, course.default_language) || t("assignments.untitled");
  const draftsCount = (data?.drafts_total ?? 0) + (data?.unpublished_modules ?? 0);
  const line = !data
    ? t("todo.title")
    : data.to_grade_total === 0 && draftsCount === 0
      ? t("todo.nothing")
      : t("todo.toGradeLine", { toGrade: data.to_grade_total, drafts: draftsCount });

  let body: React.ReactNode;
  if (error && !data) {
    body = (
      <div className="space-y-2">
        <p role="alert" className="text-sm text-danger-800">{errorText(error)}</p>
        <Button size="sm" variant="secondary" onClick={() => void reload()}>{t("lms.common.retry")}</Button>
      </div>
    );
  } else if (!data) {
    body = <div aria-hidden="true" className="space-y-3"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-5 w-full" /><Skeleton className="h-5 w-1/2" /></div>;
  } else {
    const sectionTitle = "text-sm font-semibold uppercase tracking-wide text-slate-600";
    body = (
      <div className="space-y-5">
        {data.to_grade_total === 0 && draftsCount === 0 && <p className="text-sm leading-6 text-slate-700">{t("todo.nothing")}</p>}

        {data.to_grade.length > 0 && (
          <section aria-labelledby="todo-grade" className="space-y-2">
            <h3 id="todo-grade" className={sectionTitle}>{t("todo.toGrade")}</h3>
            <ul className="space-y-2">
              {data.to_grade.map((g) => (
                <li key={g.assignment_id} className="text-base leading-6 sm:text-sm">
                  <Link href={withFrom(`${base}/assignments/${g.assignment_id}?tab=submissions&filter=to_grade`, base)} className={cn(linkCls, "break-words")}>
                    {title(g.title)}
                  </Link>
                  <span className="block text-sm text-slate-600">{t("todo.waiting", { n: g.needs_grading })} · {t(`assignments.kinds.${g.kind}`)}</span>
                </li>
              ))}
            </ul>
            {data.to_grade_total > data.to_grade.length && (
              <Link href={`${base}/assignments?needs_grading=1`} className={cn(linkCls, "inline-flex min-h-11 items-center text-sm sm:min-h-0")}>
                {t("todo.more", { n: data.to_grade_total - data.to_grade.length })}
              </Link>
            )}
          </section>
        )}

        {draftsCount > 0 && (
          <section aria-labelledby="todo-drafts" className="space-y-2">
            <h3 id="todo-drafts" className={sectionTitle}>{t("todo.drafts")}</h3>
            {data.drafts.length > 0 && (
              <ul className="space-y-2">
                {data.drafts.map((d) => (
                  <li key={d.assignment_id} className="text-base leading-6 sm:text-sm">
                    <Link href={d.kind === "quiz" && d.assessment_id
                      ? withFrom(`${base}/assessments/${d.assessment_id}/edit`, base)
                      : withFrom(`${base}/assignments/${d.assignment_id}`, base)} className={cn(linkCls, "break-words")}>
                      {title(d.title)}
                    </Link>
                    <span className="block text-sm text-slate-600">{t(`assignments.kinds.${d.kind}`)}</span>
                  </li>
                ))}
              </ul>
            )}
            {data.drafts_total > data.drafts.length && (
              <Link href={`${base}/assignments?published=no`} className={cn(linkCls, "inline-flex min-h-11 items-center text-sm sm:min-h-0")}>
                {t("todo.more", { n: data.drafts_total - data.drafts.length })}
              </Link>
            )}
            {data.unpublished_modules > 0 && (
              <p className="text-base leading-6 sm:text-sm">
                {data.first_unpublished_module_id ? (
                  <a href={`#m-${data.first_unpublished_module_id}`} className={linkCls}>{t("todo.unpublishedModules", { n: data.unpublished_modules })}</a>
                ) : t("todo.unpublishedModules", { n: data.unpublished_modules })}
              </p>
            )}
          </section>
        )}

        {data.join_code && (
          <section aria-labelledby="todo-join" className="space-y-2">
            <h3 id="todo-join" className={sectionTitle}>{t("courses.settings.joinCode")}</h3>
            <JoinCodeDisplay code={data.join_code} />
            {/* Phase 8c UX M5: a published course only needs joining by code turned on */}
            {!data.join_code_active && (
              <p className="text-sm leading-6 text-warning-800">
                {course.status === "published" ? t("todo.joinCodeOff") : t("courses.settings.joinCodeInactive")}
              </p>
            )}
            <Link href={`${base}/settings`} className={cn(linkCls, "inline-flex min-h-11 items-center text-sm sm:min-h-0")}>{t("teaching.manageEnrollment")}</Link>
          </section>
        )}

        <section aria-labelledby="todo-students" className="space-y-1">
          <h3 id="todo-students" className={sectionTitle}>{t("todo.studentsTitle")}</h3>
          <Link href={`${base}/people`} className={cn(linkCls, "inline-flex min-h-11 items-center text-base sm:min-h-0 sm:text-sm")}>
            {t("todo.students", { n: data.active_students })}
          </Link>
        </section>
      </div>
    );
  }

  return (
    <aside aria-label={t("todo.title")} className={cn("rounded-2xl border border-slate-200 bg-white shadow-sm", className)}>
      <button type="button" aria-expanded={open} aria-controls="todo-body" onClick={() => setOpen((o) => !o)}
        className={cn("flex min-h-12 w-full items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left", !compact && "lg:hidden", focusRing)}>
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-slate-900">{t("todo.title")}</span>
          <span className="block text-sm text-slate-700">{line}</span>
        </span>
        <ChevronDown aria-hidden="true" className={cn("h-5 w-5 shrink-0 text-slate-600 transition-transform", open && "rotate-180")} />
      </button>
      <div id="todo-body" className={cn("border-t border-slate-100 p-4", !compact && "lg:block lg:border-t-0 lg:p-5", open ? "block" : "hidden")}>
        {!compact && <h2 className="mb-4 hidden text-lg font-semibold leading-7 text-slate-900 lg:block">{t("todo.title")}</h2>}
        {body}
      </div>
    </aside>
  );
}
