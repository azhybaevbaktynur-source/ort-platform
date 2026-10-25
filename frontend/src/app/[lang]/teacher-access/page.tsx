"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, UserPlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { listMyInvitations, type MyInvitationOut } from "@/lib/lms/invitations";
import { fmtApiDate } from "@/lib/format";
import { TeacherRequestPanel } from "@/components/lms/TeacherRequestPanel";

/** "I am a teacher" (design §7): ask your school for an invitation, or apply as an independent teacher. */
export default function TeacherAccessPage() {
  const { lang, t } = useTranslation();
  const { me } = useLmsMe();
  const [invitations, setInvitations] = useState<MyInvitationOut[]>([]);

  useEffect(() => {
    let alive = true;
    listMyInvitations().then((r) => { if (alive) setInvitations(r); }).catch(() => { if (alive) setInvitations([]); });
    return () => { alive = false; };
  }, []);

  return (
    <div className="mx-auto max-w-2xl">
      <Link href={`/${lang}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("teacherRequest.back")}</Link>
      <h1 className="mb-2 mt-2 text-2xl font-bold text-slate-900">{t("teacherAccess.title")}</h1>
      <p className="mb-6 text-sm text-slate-600">{t("teacherAccess.intro")}</p>

      {me?.can_create_courses && (
        <div role="status" className="mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          {t("teacherAccess.canCreate")}{" "}
          <Link href={`/${lang}/courses/new`} className="font-semibold underline">{t("teacherRequest.createCourse")}</Link>
        </div>
      )}

      <section aria-labelledby="ta-school" className="mb-6 rounded-2xl border border-slate-200 bg-white p-5">
        <h2 id="ta-school" className="flex items-center gap-2 text-lg font-semibold text-slate-900">
          <Building2 className="h-5 w-5 text-brand-600" aria-hidden="true" />{t("teacherAccess.schoolTitle")}
        </h2>
        <p className="mt-1 text-sm text-slate-600">{t("teacherAccess.schoolBody")}</p>
        {invitations.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-slate-900">{t("teacherAccess.pendingTitle", { n: invitations.length })}</h3>
            <ul className="mt-2 space-y-2">
              {invitations.map((i) => (
                <li key={i.id} className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
                  <p className="font-medium">
                    {t(`teacherAccess.pendingItem.${i.role}`, { org: i.organization_name, course: i.course_title || "" })}
                  </p>
                  <p className="mt-0.5 text-xs">{t("teacherAccess.pendingHint", { date: fmtApiDate(i.expires_at, lang) })}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section aria-labelledby="ta-independent" className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 id="ta-independent" className="mb-2 flex items-center gap-2 text-lg font-semibold text-slate-900">
          <UserPlus className="h-5 w-5 text-brand-600" aria-hidden="true" />{t("teacherAccess.independentTitle")}
        </h2>
        <TeacherRequestPanel />
      </section>
    </div>
  );
}
