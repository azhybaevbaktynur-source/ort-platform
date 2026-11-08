"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MailOpen } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { INVITATIONS_CHANGED_EVENT, listMyInvitations } from "@/lib/lms/invitations";
import { BOOTSTRAP_KEY, BOOTSTRAP_OPTIONS, fetchBootstrap, reloadBootstrap, type BootstrapOut } from "@/lib/lms/bootstrap";
import { useCached } from "@/lib/lms/swr";
import { useInLmsShell } from "@/lib/lms/useLmsMe";

/**
 * Phase 6 S4b: "Invitations for you: N" after login (GET /me/invitations), linking to the list with
 * Accept buttons on /invitations. Navigation only: fails silently, hidden on that page itself.
 * PERFORMANCE_AUDIT S2: inside LmsShell the count comes from the shell's bootstrap (no request of its own); a change
 * asks the bootstrap again. Outside the shell it keeps its own request.
 */
export function PendingInvitationsBanner({ enabled }: { enabled: boolean }) {
  const { lang, t } = useTranslation();
  const pathname = usePathname();
  const inShell = useInLmsShell();
  const [ownCount, setOwnCount] = useState(0);
  const boot = useCached<BootstrapOut>(enabled && inShell ? BOOTSTRAP_KEY : null, fetchBootstrap, BOOTSTRAP_OPTIONS);

  const load = useCallback(() => {
    if (inShell) {
      void reloadBootstrap().catch(() => undefined);
      return;
    }
    listMyInvitations().then((rows) => setOwnCount(rows.length)).catch(() => setOwnCount(0));
  }, [inShell]);
  useEffect(() => {
    if (!enabled) return;
    if (!inShell) load();
    window.addEventListener(INVITATIONS_CHANGED_EVENT, load);
    return () => window.removeEventListener(INVITATIONS_CHANGED_EVENT, load);
  }, [enabled, inShell, load]);
  const count = !enabled ? 0 : inShell ? boot.data?.pending_invitations ?? 0 : ownCount;

  const href = `/${lang}/invitations`;
  if (count === 0 || pathname === href) return null;
  return (
    <div role="status" className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
      <MailOpen className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
      <p className="min-w-0 flex-1 font-medium">{t("invitations.mine.banner", { n: count })}</p>
      {/* Phase 6 S8 (UX S2): on a phone the button takes its own full-width row under the text. */}
      <Link href={href} className="inline-flex min-h-[44px] w-full basis-full items-center justify-center rounded-xl border border-sky-300 bg-white px-4 text-sm font-semibold text-brand-700 hover:bg-sky-100 sm:w-auto sm:basis-auto">
        {t("invitations.mine.view")}
      </Link>
    </div>
  );
}
