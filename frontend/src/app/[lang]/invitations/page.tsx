"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MailOpen } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { hidesLearning } from "@/lib/lms/shellKind";
import {
  INVITATIONS_CHANGED_EVENT, acceptInvitation, invitationTarget, listMyInvitations, rememberAccepted, type MyInvitationOut,
} from "@/lib/lms/invitations";
import { pickLocalized } from "@/lib/lms/localized";
import { fmtApiDate } from "@/lib/format";
import { LoadError, OrgError } from "@/components/lms/org/OrgUi";
import { Button, EmptyState, LinkButton, LoadingState, PageHeader } from "@/components/ui";

/** Invitations for my email, with Accept (the same route as the emailed link). `PendingInvitationsBanner` links here. */
export default function MyInvitationsPage() {
  const { lang, t } = useTranslation();
  const { me, reload: reloadMe } = useLmsMe();
  // step 3a S7: people who learn go back to the hub (no learner /courses page), people who teach to their list
  const backHref = `/${lang}/${hidesLearning(me) ? "courses" : "home"}`;
  const router = useRouter();
  const [invitations, setInvitations] = useState<MyInvitationOut[] | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [acceptingId, setAcceptingId] = useState<string | null>(null);
  const [acceptError, setAcceptError] = useState<{ id: string; error: unknown } | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setInvitations(await listMyInvitations());
    } catch (e) {
      setLoadError(e);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const accept = useCallback(async (i: MyInvitationOut) => {
    setAcceptingId(i.id);
    setAcceptError(null);
    try {
      const r = await acceptInvitation(i.id);
      // The target page shows "You joined ..." once.
      const dest = invitationTarget(lang, r);
      rememberAccepted(dest, r, i.course_title ? pickLocalized(i.course_title, lang) : null);
      window.dispatchEvent(new Event(INVITATIONS_CHANGED_EVENT));
      await reloadMe();
      router.push(dest);
    } catch (e) {
      setAcceptError({ id: i.id, error: e });
      setAcceptingId(null);
    }
  }, [lang, reloadMe, router]);

  return (
    <div className="max-w-3xl">
      <PageHeader title={t("invitations.mine.title")} />
      {loadError ? <LoadError error={loadError} onRetry={() => void load()} />
        : !invitations ? <LoadingState label={t("lms.common.loading")} />
        : invitations.length === 0 ? (
          <EmptyState mascot="hello" title={t("invitations.mine.empty")} description={t("invitations.mine.emptyBody")}
            action={<LinkButton variant="secondary" href={backHref}>{t("teacherOnly.back")}</LinkButton>} />
        ) : (
          <ul className="space-y-3">
            {invitations.map((i) => {
              const course = pickLocalized(i.course_title, lang);
              const itemKey = i.role === "teacher" && course ? "teacherCourse" : i.role;
              return (
                <li key={i.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4">
                  <MailOpen aria-hidden="true" className="h-5 w-5 shrink-0 text-brand-600" />
                  <div className="min-w-0 flex-1 basis-56">
                    <p className="break-words text-base font-medium leading-6 text-slate-900 sm:text-sm">{t(`invitations.mine.item.${itemKey}`, { org: i.organization_name, course })}</p>
                    <p className="mt-0.5 text-sm leading-5 text-slate-600">{t("invitations.mine.validUntil", { date: fmtApiDate(i.expires_at, lang) })}</p>
                  </div>
                  <Button className="w-full sm:w-auto" loading={acceptingId === i.id} disabled={acceptingId !== null && acceptingId !== i.id} onClick={() => void accept(i)}>
                    {t("invitations.mine.accept")}
                  </Button>
                  {acceptError?.id === i.id && <OrgError error={acceptError.error} className="w-full" />}
                </li>
              );
            })}
          </ul>
        )}
    </div>
  );
}
