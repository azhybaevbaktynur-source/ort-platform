"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Building2, UserPlus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import {
  INVITATIONS_CHANGED_EVENT, acceptInvitation, invitationTarget, listMyInvitations, type MyInvitationOut,
} from "@/lib/lms/invitations";
import { pickLocalized } from "@/lib/lms/localized";
import { fmtApiDate } from "@/lib/format";
import { TeacherRequestPanel } from "@/components/lms/TeacherRequestPanel";
import { OrgError } from "@/components/lms/org/OrgUi";
import { toast } from "@/components/ui/Toast";

/** "I am a teacher" (design §7): ask your school for an invitation, or apply as an independent teacher. */
export default function TeacherAccessPage() {
  const { lang, t } = useTranslation();
  const { me, reload: reloadMe } = useLmsMe();
  const router = useRouter();
  const [invitations, setInvitations] = useState<MyInvitationOut[]>([]);
  // --- Phase 6 S4b: accept by invitation id (same route as the emailed token) ---
  const [acceptingId, setAcceptingId] = useState<string | null>(null);
  const [acceptError, setAcceptError] = useState<{ id: string; error: unknown } | null>(null);

  useEffect(() => {
    let alive = true;
    listMyInvitations().then((r) => { if (alive) setInvitations(r); }).catch(() => { if (alive) setInvitations([]); });
    return () => { alive = false; };
  }, []);

  const accept = useCallback(async (i: MyInvitationOut) => {
    setAcceptingId(i.id);
    setAcceptError(null);
    try {
      const r = await acceptInvitation(i.id);
      toast.success(t("invitations.mine.accepted"));
      window.dispatchEvent(new Event(INVITATIONS_CHANGED_EVENT));
      await reloadMe();
      router.push(invitationTarget(lang, r));
    } catch (e) {
      setAcceptError({ id: i.id, error: e });
      setAcceptingId(null);
    }
  }, [lang, reloadMe, router, t]);

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
              {invitations.map((i) => {
                const course = pickLocalized(i.course_title, lang);
                const itemKey = i.role === "teacher" && course ? "teacherCourse" : i.role;
                return (
                  <li key={i.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
                    <div className="min-w-0 flex-1 basis-56">
                      <p className="font-medium">{t(`teacherAccess.pendingItem.${itemKey}`, { org: i.organization_name, course })}</p>
                      <p className="mt-0.5 text-xs">{t("teacherAccess.pendingHintAccept", { date: fmtApiDate(i.expires_at, lang) })}</p>
                    </div>
                    <button type="button" disabled={acceptingId !== null} onClick={() => void accept(i)}
                      className="inline-flex min-h-[44px] items-center rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
                      {acceptingId === i.id ? t("lms.common.loading") : t("invitations.mine.accept")}
                    </button>
                    {acceptError?.id === i.id && <OrgError error={acceptError.error} className="w-full" />}
                  </li>
                );
              })}
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
