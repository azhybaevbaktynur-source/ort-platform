"use client";

// UX rework (UX_REWORK_DESIGN B, C): compact side lists of the dashboard and of a course's modules view: "To do" rows
// (kind icon, title, course, date) and the small titled card around them.
import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { HomeTodoOut } from "@/lib/lms/homeTypes";
import { KindIcon } from "@/components/lms/assignments/assignmentUi";
import { cn, focusRing } from "@/components/ui";
import { fmtDayMonthTime } from "./format";

export function SideSection({ id, title, children }: { id: string; title: React.ReactNode; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className="mb-2 text-lg font-semibold leading-7 text-slate-900">{title}</h2>
      <div className="rounded-card border border-slate-200 bg-white p-1">{children}</div>
    </section>
  );
}

/** One tappable row of a side list (at least 44 px high). */
export function SideRow({ href, icon, title, lines, aside }: {
  href: string;
  icon?: React.ReactNode;
  title: React.ReactNode;
  lines?: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <li>
      <Link href={href} className={cn("flex min-h-11 items-start gap-2.5 rounded-xl px-3 py-2.5 hover:bg-slate-50", focusRing)}>
        {icon}
        <span className="min-w-0 flex-1">
          <span className="block break-words text-base font-medium leading-6 text-slate-900 sm:text-sm sm:leading-5">{title}</span>
          {lines && <span className="mt-0.5 block text-sm leading-5 text-slate-600 sm:text-xs">{lines}</span>}
        </span>
        {aside && <span className="shrink-0 text-right text-base font-bold leading-6 text-slate-900 sm:leading-5">{aside}</span>}
      </Link>
    </li>
  );
}

function todoHref(coursesBase: string, r: HomeTodoOut): string {
  const base = `${coursesBase}/${r.course_id}`;
  if (r.attempt_id) return `${base}/attempts/${r.attempt_id}`;
  if (r.kind === "quiz" && r.assessment_id) return `${base}/assessments/${r.assessment_id}`;
  if (r.assignment_id) return `${base}/assignments/${r.assignment_id}`;
  return base;
}

function TodoDate({ r }: { r: HomeTodoOut }) {
  const { lang, t } = useTranslation();
  if (r.attempt_id) return <span className="block font-semibold text-brand-700">{t("home.todo.inProgress")}</span>;
  if (r.overdue) return <span className="block font-semibold text-danger-700">{t("home.todo.overdue")}</span>;
  const date = r.due_at ?? r.available_until;
  return date ? <span className="block">{t("home.todo.due", { date: fmtDayMonthTime(date, lang) })}</span> : null;
}

/** `showCourse` off inside a course, where the course name would repeat on every row. */
export function TodoRows({ rows, showCourse = true }: { rows: HomeTodoOut[]; showCourse?: boolean }) {
  const { lang, t } = useTranslation();
  return (
    <ul className="divide-y divide-slate-100">
      {rows.map((r) => (
        <SideRow key={r.attempt_id ?? r.assignment_id ?? r.assessment_id} href={todoHref(`/${lang}/courses`, r)}
          icon={<KindIcon kind={r.kind} className="mt-1 h-4 w-4 text-slate-500 sm:mt-0.5" />}
          title={pickLocalized(r.title, lang) || t("assessments.untitled")}
          lines={(
            <>
              {showCourse && <span className="block break-words">{pickLocalized(r.course_title, lang) || t("courses.list.untitled")}</span>}
              <TodoDate r={r} />
            </>
          )} />
      ))}
    </ul>
  );
}
