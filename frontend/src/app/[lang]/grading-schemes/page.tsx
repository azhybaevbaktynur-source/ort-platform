"use client";

import React from "react";
import { LinkButton } from "@/components/ui";
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
        <p className="mt-2 text-base leading-6 text-slate-600 sm:text-sm">{t("teacherAccess.schemesNoAccess.body")}</p>
        {/* Phase 6b S11b (UX 5): design-system link buttons. */}
        <div className="mt-6 flex flex-col-reverse justify-center gap-3 sm:flex-row">
          <LinkButton variant="secondary" href={`/${lang}/teacher-access`}>{t("teacherAccess.navLink")}</LinkButton>
          <LinkButton href={`/${lang}/courses`}>{t("teacherAccess.schemesNoAccess.back")}</LinkButton>
        </div>
      </div>
    );
  }
  return <SchemeLibrary />;
}
