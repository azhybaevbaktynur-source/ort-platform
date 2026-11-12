"use client";

import React, { useState } from "react";
import Link from "next/link";
import { CircleAlert, CircleCheck, Clock, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDateTimeShort, parseApiDate } from "@/lib/format";
import { dismissTeacherApplication } from "@/lib/lms/home";
import type { HomeTeacherApplicationOut } from "@/lib/lms/homeTypes";
import { cn, focusRing, IconButton } from "@/components/ui";

const LOOK = {
  pending: { box: "border-warning-200 bg-warning-50 text-warning-900", Icon: Clock },
  approved: { box: "border-success-200 bg-success-50 text-success-900", Icon: CircleCheck },
  rejected: { box: "border-danger-200 bg-danger-50 text-danger-900", Icon: CircleAlert },
  revoked: { box: "border-danger-200 bg-danger-50 text-danger-900", Icon: CircleAlert },
} as const;

/**
 * One line about the person's teacher application (`/me/home.teacher_application`); also the Teaching list's notice for a
 * revoked teacher (`dismissible={false}`: it explains the read-only list). Fix round 2026-11-12 1c: a decision can be
 * closed for good (stored on the server, so no other device or cached answer brings it back).
 */
export function TeacherApplicationNotice({ application, dismissible = true }: {
  application: Pick<HomeTeacherApplicationOut, "status"> & Partial<HomeTeacherApplicationOut>;
  dismissible?: boolean;
}) {
  const { lang, t } = useTranslation();
  const [hidden, setHidden] = useState(false);
  const { status, reason, reapply_available_at: reapplyAt } = application;
  const apply = `/${lang}/for-teachers/apply`;
  const { box, Icon } = LOOK[status];
  const reapply = parseApiDate(reapplyAt);
  const waiting = status === "rejected" && !!reapply && reapply.getTime() > Date.now();

  // Fix round 2026-11-12 1c: no link for "approved" (the person is already in Teaching; the link went nowhere)
  const link = status === "revoked" || (status === "rejected" && !waiting)
    ? { href: apply, label: t("home.teacherApplication.applyLink") } : null;
  const canDismiss = dismissible && status !== "pending";

  const dismiss = async () => {
    setHidden(true); // optimistic: the server call only makes it stick
    try {
      await dismissTeacherApplication();
    } catch {
      setHidden(false);
    }
  };

  if (hidden) return null;
  return (
    <div role="status" className={cn("flex items-start gap-x-3 rounded-2xl border py-3 pl-4 text-sm leading-6", canDismiss ? "pr-1.5" : "pr-4", box)}>
      <Icon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-56">
          <p className="font-medium">{t(`home.teacherApplication.${status}`)}</p>
          {status === "rejected" && reason && <p className="break-words"><strong>{t("teacherRequest.reason")}:</strong> {reason}</p>}
          {waiting && <p>{t("home.teacherApplication.rejectedWait", { date: fmtApiDateTimeShort(reapplyAt, lang) })}</p>}
        </div>
        {link && (
          <Link href={link.href} className={cn("inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-300 bg-white px-4 font-semibold text-brand-700 hover:bg-slate-50 sm:w-auto", focusRing)}>
            {link.label}
          </Link>
        )}
      </div>
      {canDismiss && (
        <IconButton aria-label={t("home.teacherApplication.dismiss")} icon={<X />} onClick={() => void dismiss()}
          className="-my-2 text-current hover:bg-black/5 hover:text-current" />
      )}
    </div>
  );
}
