"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useAdminSummary } from "@/components/lms/admin/AdminShell";

export default function AdminOverviewPage() {
  const { lang, t } = useTranslation();
  const { pending } = useAdminSummary();
  const card = "rounded-2xl border border-slate-200 bg-white p-5 hover:border-brand-400";
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-slate-900">{t("platformAdmin.overview.title")}</h1>
      <div className="grid gap-4 sm:grid-cols-2">
        <Link href={`/${lang}/admin/teacher-requests`} className={card}>
          <p className="text-3xl font-bold text-slate-900">{pending ?? "—"}</p>
          <p className="mt-1 text-sm text-slate-600">{t("platformAdmin.overview.pendingRequests")}</p>
        </Link>
        <Link href={`/${lang}/admin/users`} className={card}><p className="font-semibold text-slate-900">{t("platformAdmin.nav.users")}</p><p className="mt-1 text-sm text-slate-600">{t("platformAdmin.overview.usersHint")}</p></Link>
        <Link href={`/${lang}/admin/courses`} className={card}><p className="font-semibold text-slate-900">{t("platformAdmin.nav.courses")}</p><p className="mt-1 text-sm text-slate-600">{t("platformAdmin.overview.coursesHint")}</p></Link>
        <Link href={`/${lang}/admin/audit-log`} className={card}><p className="font-semibold text-slate-900">{t("platformAdmin.nav.auditLog")}</p><p className="mt-1 text-sm text-slate-600">{t("platformAdmin.overview.auditHint")}</p></Link>
      </div>
    </div>
  );
}
