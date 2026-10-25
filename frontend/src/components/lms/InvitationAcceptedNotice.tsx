"use client";

import React, { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { CheckCircle2, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { takeAccepted, type AcceptedNoticeData } from "@/lib/lms/invitations";

/** Phase 6 S8 (UX S1): "You joined «org» as a teacher" once, on the page an invitation accept redirected to. */
export function InvitationAcceptedNotice() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const [data, setData] = useState<AcceptedNoticeData | null>(null);

  useEffect(() => {
    const d = takeAccepted(pathname);
    if (d) setData(d);
  }, [pathname]);

  if (!data) return null;
  const text = data.course
    ? t(data.role === "assistant" ? "invitationAccepted.courseAssistant" : "invitationAccepted.courseTeacher", { course: data.course })
    : t(data.role === "org_admin" ? "invitationAccepted.orgAdmin" : "invitationAccepted.orgTeacher", { org: data.org });
  return (
    <div role="status" className="mb-6 flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
      <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
      <p className="min-w-0 flex-1 break-words font-medium">{text}</p>
      <button type="button" onClick={() => setData(null)} aria-label={t("invitationAccepted.dismiss")}
        className="-my-2 -mr-2 inline-flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl text-emerald-800 hover:bg-emerald-100">
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
