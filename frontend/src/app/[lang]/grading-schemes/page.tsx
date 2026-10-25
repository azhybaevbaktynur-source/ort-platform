"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { SchemeLibrary } from "@/components/lms/grading/schemes/SchemeLibrary";

export default function GradingSchemesPage() {
  const { lang, t } = useTranslation();
  const { me, loading } = useLmsMe();
  // Phase 6 S4 (audit S8): the scheme library is for people who create courses and for admins.
  if (loading && !me) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  if (me && !me.can_create_courses && !me.is_platform_admin) {
    return (
      <div role="alert" className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="text-xl font-bold text-slate-900">{t("teacherAccess.schemesNoAccess.title")}</h1>
        <p className="mt-2 text-sm text-slate-600">{t("teacherAccess.schemesNoAccess.body")}</p>
        <div className="mt-4 flex flex-wrap justify-center gap-3 text-sm font-medium">
          <Link href={`/${lang}/courses`} className="rounded-xl bg-brand-600 px-4 py-2 text-white hover:bg-brand-700">{t("teacherAccess.schemesNoAccess.back")}</Link>
          <Link href={`/${lang}/teacher-access`} className="rounded-xl border border-slate-200 px-4 py-2 text-slate-700 hover:bg-slate-50">{t("teacherAccess.navLink")}</Link>
        </div>
      </div>
    );
  }
  return <SchemeLibrary />;
}
