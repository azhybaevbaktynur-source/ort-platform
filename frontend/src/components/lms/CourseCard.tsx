"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { CourseCard as CourseCardDto } from "@/lib/lms/types";

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

export function CourseCard({ course, action }: { course: CourseCardDto; action?: React.ReactNode }) {
  const { lang, t } = useTranslation();
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const inner = (
    <>
      <div className="mb-3 flex items-center justify-between gap-2">
        <StatusBadge status={course.status} />
        {course.my_role && <span className="text-xs font-medium text-slate-500">{t(`courses.roles.${course.my_role}`)}</span>}
      </div>
      <h3 className="line-clamp-2 text-base font-bold text-slate-900">{title}</h3>
      {course.owner_display_name && (
        <p className="mt-1 text-sm text-slate-500">{t("courses.list.owner", { name: course.owner_display_name })}</p>
      )}
      <p className="mt-3 text-xs text-slate-400">{course.languages.map((l) => l.toUpperCase()).join(" / ")}</p>
    </>
  );
  const box = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";
  return (
    <div className={`${box} transition hover:shadow-md`}>
      {course.deleted_at ? <div>{inner}</div> : <Link href={`/${lang}/courses/${course.id}`} className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400">{inner}</Link>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
