"use client";

import React from "react";
import Link from "next/link";
import { CircleAlert, CircleCheck, Clock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDate, parseApiDate } from "@/lib/format";
import type { HomeTeacherApplicationOut } from "@/lib/lms/homeTypes";
import { cn, focusRing } from "@/components/ui";

const LOOK = {
  pending: { box: "border-warning-200 bg-warning-50 text-warning-900", Icon: Clock },
  approved: { box: "border-success-200 bg-success-50 text-success-900", Icon: CircleCheck },
  rejected: { box: "border-danger-200 bg-danger-50 text-danger-900", Icon: CircleAlert },
  revoked: { box: "border-danger-200 bg-danger-50 text-danger-900", Icon: CircleAlert },
} as const;

/** One line about the person's teacher application (`/me/home.teacher_application`); also the Teaching list's notice for a revoked teacher. */
export function TeacherApplicationNotice({ application }: { application: Pick<HomeTeacherApplicationOut, "status"> & Partial<HomeTeacherApplicationOut> }) {
  const { lang, t } = useTranslation();
  const { status, reason, reapply_available_at: reapplyAt } = application;
  const apply = `/${lang}/for-teachers/apply`;
  const { box, Icon } = LOOK[status];
  const reapply = parseApiDate(reapplyAt);
  const waiting = status === "rejected" && !!reapply && reapply.getTime() > Date.now();

  let link: { href: string; label: string } | null = null;
  if (status === "approved") link = { href: `/${lang}/courses?view=teaching`, label: t("home.teacherApplication.approvedLink") };
  if (status === "revoked" || (status === "rejected" && !waiting)) link = { href: apply, label: t("home.teacherApplication.applyLink") };

  return (
    <div role="status" className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border px-4 py-3 text-sm leading-6", box)}>
      <Icon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 self-start" />
      <div className="min-w-0 flex-1 basis-56">
        <p className="font-medium">{t(`home.teacherApplication.${status}`)}</p>
        {status === "rejected" && reason && <p className="break-words"><strong>{t("teacherRequest.reason")}:</strong> {reason}</p>}
        {waiting && <p>{t("home.teacherApplication.rejectedWait", { date: fmtApiDate(reapplyAt, lang) })}</p>}
      </div>
      {link && (
        <Link href={link.href} className={cn("inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-300 bg-white px-4 font-semibold text-brand-700 hover:bg-slate-50 sm:w-auto", focusRing)}>
          {link.label}
        </Link>
      )}
    </div>
  );
}
