"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { OrgCourseOut } from "@/lib/lms/organizations";
import { StatusBadge } from "@/components/lms/CourseCard";
import { templateTitle } from "@/lib/lms/templates";

/** Course rows (title, owner, status, students) for the org admin and platform admin organization pages. */
export function OrgCourseList({ courses, hrefFor }: { courses: OrgCourseOut[]; hrefFor: (c: OrgCourseOut) => string }) {
  const { lang, t } = useTranslation();
  return (
    <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
      {courses.map((c) => (
        <li key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <div className="min-w-0 flex-1 basis-56">
            <Link href={hrefFor(c)} className="font-medium text-brand-700 hover:underline">
              {pickLocalized(c.title, lang) || c.id}
            </Link>
            <p className="truncate text-xs text-slate-500">
              {t("organizations.courses.owner")}: {c.owner.display_name || c.owner.email}
              {c.template_key ? ` · ${templateTitle(t, c.template_key)}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={c.status} />
            <span className="text-xs text-slate-600">{t("organizations.courses.students", { n: c.active_student_count })}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
