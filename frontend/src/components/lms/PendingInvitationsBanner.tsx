"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MailOpen } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { INVITATIONS_CHANGED_EVENT, listMyInvitations } from "@/lib/lms/invitations";

/**
 * Phase 6 S4b: "Invitations for you: N" after login (GET /me/invitations), linking to the list with
 * Accept buttons on /teacher-access. Navigation only: fails silently, hidden on that page itself.
 */
export function PendingInvitationsBanner({ enabled }: { enabled: boolean }) {
  const { lang, t } = useTranslation();
  const pathname = usePathname();
  const [count, setCount] = useState(0);

  const load = useCallback(() => {
    listMyInvitations().then((rows) => setCount(rows.length)).catch(() => setCount(0));
  }, []);
  useEffect(() => {
    if (!enabled) return;
    load();
    window.addEventListener(INVITATIONS_CHANGED_EVENT, load);
    return () => window.removeEventListener(INVITATIONS_CHANGED_EVENT, load);
  }, [enabled, load]);

  const href = `/${lang}/teacher-access`;
  if (count === 0 || pathname === href) return null;
  return (
    <div role="status" className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
      <MailOpen className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
      <p className="min-w-0 flex-1 font-medium">{t("invitations.mine.banner", { n: count })}</p>
      <Link href={href} className="inline-flex min-h-[44px] items-center rounded-xl border border-sky-300 bg-white px-4 text-sm font-semibold text-brand-700 hover:bg-sky-100">
        {t("invitations.mine.view")}
      </Link>
    </div>
  );
}
