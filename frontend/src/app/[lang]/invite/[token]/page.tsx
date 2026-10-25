"use client";

import React, { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2, MailOpen } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { acceptInvitation, getInvitation, invitationTarget, rememberAccepted, type InvitationAcceptOut, type InvitationPublicOut } from "@/lib/lms/invitations";
import { fmtApiDate } from "@/lib/format";
import { pickLocalized } from "@/lib/lms/localized";
import { AuthHeader } from "@/components/auth/AuthHeader";
import { OrgError } from "@/components/lms/org/OrgUi";
import { Button, LinkButton, LoadingState } from "@/components/ui";

const card = "rounded-3xl border border-slate-200/80 bg-white px-6 py-8 shadow-lg sm:px-10";

/** Invitation accept page (design §7): works signed out; signed in, it accepts automatically. */
function InviteAccept() {
  const { lang, t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, loading: authLoading, signOut } = useAuth();
  const [inv, setInv] = useState<InvitationPublicOut | null>(null);
  const [lookupError, setLookupError] = useState<unknown>(null);
  const [accepting, setAccepting] = useState(false);
  const [acceptError, setAcceptError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const tried = useRef(false);

  const lookup = useCallback(async () => {
    setLookupError(null);
    try {
      setInv(await getInvitation(token));
    } catch (e) {
      setLookupError(e);
    }
  }, [token]);
  useEffect(() => { void lookup(); }, [lookup]);

  const target = (r: InvitationAcceptOut) => invitationTarget(lang, r);

  const accept = useCallback(async () => {
    setAccepting(true);
    setAcceptError(null);
    try {
      const r = await acceptInvitation(token);
      setDone(true);
      // Phase 6 S8 (UX S1): the target page shows "You joined ..." once.
      const dest = target(r);
      rememberAccepted(dest, r, inv?.course_title ? pickLocalized(inv.course_title, lang) : null);
      router.replace(dest);
    } catch (e) {
      setAcceptError(e);
    } finally {
      setAccepting(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, lang, router, inv]);

  useEffect(() => {
    if (inv && user && !authLoading && !tried.current) {
      tried.current = true;
      void accept();
    }
  }, [inv, user, authLoading, accept]);

  const here = `/${lang}/invite/${encodeURIComponent(token)}`;
  const email = searchParams.get("email");
  const authQs = `redirect=${encodeURIComponent(here)}${email ? `&email=${encodeURIComponent(email)}` : ""}`;
  const status = (lookupError as { status?: number } | null)?.status;
  const mismatch = (acceptError as { code?: string } | null)?.code === "invitation_email_mismatch";

  let body: React.ReactNode;
  if (lookupError && status === 404) {
    body = (
      <div className="text-center">
        <h1 className="text-xl font-bold text-slate-900">{t("invitations.accept.invalidTitle")}</h1>
        <p className="mt-2 text-base text-slate-600 sm:text-sm">{t("invitations.accept.invalidBody")}</p>
        <LinkButton href={`/${lang}`} variant="secondary" fullWidth className="mt-6">{t("invitations.accept.home")}</LinkButton>
      </div>
    );
  } else if (lookupError) {
    body = <OrgError error={lookupError} onRetry={lookup} />;
  } else if (!inv || authLoading) {
    body = <LoadingState label={t("lms.common.loading")} rows={1} />;
  } else {
    const roleText = t(`invitations.roles.${inv.role}`);
    body = (
      <div>
        <div className="mb-5 flex justify-center"><MailOpen className="h-10 w-10 text-brand-600" aria-hidden="true" /></div>
        <h1 className="text-center text-xl font-bold text-slate-900">{t("invitations.accept.title", { org: inv.organization_name })}</h1>
        <dl className="mt-5 space-y-2 rounded-2xl bg-slate-50 p-4 text-sm">
          <div className="flex flex-wrap justify-between gap-2"><dt className="text-slate-600">{t("invitations.accept.organization")}</dt><dd className="font-medium text-slate-900">{inv.organization_name}</dd></div>
          <div className="flex flex-wrap justify-between gap-2"><dt className="text-slate-600">{t("invitations.accept.role")}</dt><dd className="font-medium text-slate-900">{roleText}</dd></div>
          {inv.course_title && <div className="flex flex-wrap justify-between gap-2"><dt className="text-slate-600">{t("invitations.accept.course")}</dt><dd className="font-medium text-slate-900">{pickLocalized(inv.course_title, lang)}</dd></div>}
          <div className="flex flex-wrap justify-between gap-2"><dt className="text-slate-600">{t("invitations.accept.email")}</dt><dd className="font-medium text-slate-900">{inv.masked_email}</dd></div>
          <div className="flex flex-wrap justify-between gap-2"><dt className="text-slate-600">{t("invitations.accept.expires")}</dt><dd className="font-medium text-slate-900">{fmtApiDate(inv.expires_at, lang)}</dd></div>
        </dl>
        {!user && (
          <div className="mt-6 space-y-3">
            <p className="text-sm text-slate-600">{t("invitations.accept.signedOutHint", { email: inv.masked_email })}</p>
            <LinkButton href={`/${lang}/login?${authQs}`} fullWidth>{t("invitations.accept.login")}</LinkButton>
            <LinkButton href={`/${lang}/register?${authQs}`} variant="secondary" fullWidth>{t("invitations.accept.register")}</LinkButton>
          </div>
        )}
        {user && (accepting || done) && (
          <p role="status" className="mt-6 flex items-center justify-center gap-2 text-sm text-slate-600">
            {done ? <CheckCircle2 className="h-4 w-4 text-success-700" aria-hidden="true" /> : <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {done ? t("invitations.accept.done") : t("invitations.accept.accepting")}
          </p>
        )}
        {user && mismatch && (
          <div role="alert" className="mt-6 space-y-3 rounded-2xl border border-warning-200 bg-warning-50 p-4 text-sm text-warning-900">
            <p>{t("invitations.accept.mismatch", { invited: inv.masked_email, current: user.email })}</p>
            <Button variant="secondary" fullWidth onClick={() => { tried.current = false; void signOut(); }}>
              {t("invitations.accept.switchAccount")}
            </Button>
          </div>
        )}
        {user && acceptError && !mismatch ? (
          <div className="mt-6 space-y-3">
            <OrgError error={acceptError} />
            <Button fullWidth loading={accepting} onClick={() => void accept()}>{t("invitations.accept.retry")}</Button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col justify-center bg-gradient-to-b from-slate-50 via-white to-slate-100 py-12 sm:px-6 lg:px-8">
      <AuthHeader />
      <div className="px-4 sm:mx-auto sm:w-full sm:max-w-md">
        <div className={card}>{body}</div>
      </div>
    </div>
  );
}

function PageLoading() {
  const { t } = useTranslation();
  return <div role="status" className="flex min-h-screen items-center justify-center text-sm text-slate-600">{t("lms.common.loading")}</div>;
}

export default function InvitePage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <InviteAccept />
    </Suspense>
  );
}
