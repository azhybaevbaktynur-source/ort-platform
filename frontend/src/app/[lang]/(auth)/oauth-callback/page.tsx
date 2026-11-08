"use client";

import React, { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { AuthError, useAuth } from "@/lib/auth-context";
import { safeRedirect } from "@/lib/safeRedirect";
import { AuthAlert, AuthSplit, AuthTitle } from "@/components/auth/AuthSplit";
import { AgeRow } from "@/components/auth/AgeRow";
import { MfaStep } from "@/components/auth/MfaStep";
import { authErrorMessage } from "@/components/auth/VerifyEmailStep";
import { PolicyAcceptField, SignUpNameInput, useOwnPolicies } from "@/components/auth/SignUpFields";
import { Button } from "@/components/ui";
import { ownPolicyIds, type AgeBand } from "@/components/privacy/privacyApi";
import { ownPrivacyErrorText } from "@/components/privacy/privacyErrors";

type Step = "working" | "profile" | "mfa" | "error";

/** Display-only read of the ticket payload (name and email for the "Almost done" step); the server verifies it. */
function readTicket(ticket: string): { email: string; name: string } {
  try {
    const part = ticket.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(part + "=".repeat((4 - (part.length % 4)) % 4)), (c) => c.charCodeAt(0));
    const json = JSON.parse(new TextDecoder().decode(bytes));
    return { email: String(json.email || ""), name: String(json.name || "") };
  } catch {
    return { email: "", name: "" };
  }
}

function OAuthCallback() {
  const router = useRouter();
  const { lang, t } = useTranslation();
  const { completeOAuth } = useAuth();

  const ticketRef = useRef<string | null>(null);
  const redirectRef = useRef<string>("");
  const started = useRef(false);

  const [step, setStep] = useState<Step>("working");
  const [error, setError] = useState<string | null>(null);
  const [challenge, setChallenge] = useState<string | null>(null);
  const [who, setWho] = useState({ email: "", name: "" });
  const [displayName, setDisplayName] = useState("");
  const [band, setBand] = useState<AgeBand | null>(null);
  const [asParent, setAsParent] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const needsPolicies = !!band && band !== "under_14";
  const policyState = useOwnPolicies(needsPolicies);
  const { policies } = policyState;

  const goOn = (ageBand?: AgeBand | null, parent = false) => {
    if (ageBand === "under_14") router.replace(`/${lang}/privacy`);
    else if (parent) router.replace(`/${lang}/parent`);
    else router.replace(redirectRef.current || `/${lang}/courses`);
  };

  const fail = (err: unknown) => {
    setError(ownPrivacyErrorText(t, err) ?? authErrorMessage(err, t, "auth.loginError"));
    setStep("error");
  };

  useEffect(() => {
    if (started.current) return; // React strict mode runs effects twice in dev; the fragment is read once
    started.current = true;
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    // the ticket must not stay in the address bar or the history
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    const ticket = params.get("t");
    if (!ticket) {
      router.replace(`/${lang}/login`);
      return;
    }
    ticketRef.current = ticket;
    redirectRef.current = safeRedirect(params.get("r"), "");
    const info = readTicket(ticket);
    setWho(info);
    setDisplayName(info.name || info.email.split("@")[0]);
    (async () => {
      try {
        await completeOAuth(ticket);
        goOn();
      } catch (err) {
        if (err instanceof AuthError && err.code === "oauth_profile_required") setStep("profile");
        else if (err instanceof AuthError && err.code === "mfa_required" && typeof err.details.challenge === "string") {
          setChallenge(err.details.challenge);
          setStep("mfa");
        } else fail(err);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!band || !ticketRef.current) return;
    setError(null);
    setBusy(true);
    try {
      await completeOAuth(ticketRef.current, {
        ageBand: band,
        policyVersionIds: needsPolicies ? ownPolicyIds(policies ?? []) : [],
        displayName: displayName.trim(),
      });
      goOn(band, asParent);
    } catch (err) {
      if (err instanceof AuthError && err.code === "mfa_required" && typeof err.details.challenge === "string") {
        setChallenge(err.details.challenge);
        setStep("mfa");
      } else if (err instanceof AuthError && err.code === "oauth_ticket_invalid") {
        fail(err);
      } else {
        setError(ownPrivacyErrorText(t, err) ?? authErrorMessage(err, t, "auth.loginError"));
      }
    } finally {
      setBusy(false);
    }
  };

  if (step === "mfa" && challenge) {
    return (
      <AuthSplit pose="reading">
        <MfaStep challenge={challenge} onDone={() => goOn()} onRestart={(message) => { setError(message || null); setStep("error"); }} />
      </AuthSplit>
    );
  }

  if (step === "profile") {
    return (
      <AuthSplit pose="encouraging">
        <AuthTitle title={t("auth.oauth.completeTitle")} subtitle={t("auth.oauth.completeSubtitle")} />
        <p className="mb-5 break-words rounded-xl bg-brand-50 px-3 py-2 text-sm text-slate-800">
          {t("auth.oauth.signedInAs", { email: who.email })}
        </p>
        {error && <AuthAlert>{error}</AuthAlert>}
        <form onSubmit={submitProfile} className="space-y-4">
          <SignUpNameInput value={displayName} onChange={setDisplayName} />
          <AgeRow value={band} onChoose={(b) => { setAsParent(false); setBand(b); if (b === "under_14") setAccepted(false); }} />
          {needsPolicies && <PolicyAcceptField state={policyState} checked={accepted} onChange={setAccepted} />}
          <Button type="submit" size="lg" fullWidth loading={busy} disabled={busy || !band || !displayName.trim() || (needsPolicies && !policies)} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
            {t("auth.oauth.completeButton")}
          </Button>
        </form>
        <div className="mt-3 text-center">
          <Button type="button" variant="link" onClick={() => { setAsParent(true); setBand("18_plus"); }}>{t("auth.parentCta")}</Button>
        </div>
        <div className="mt-2 text-center">
          <Link href={`/${lang}/login`} className="inline-flex min-h-11 items-center text-sm font-semibold text-slate-600 hover:text-brand-700">
            {t("auth.oauth.useAnotherAccount")}
          </Link>
        </div>
      </AuthSplit>
    );
  }

  if (step === "error") {
    return (
      <AuthSplit pose="thinking">
        <AuthTitle title={t("auth.signInTitle")} />
        {error && <AuthAlert>{error}</AuthAlert>}
        <Link href={`/${lang}/login`} className="inline-flex min-h-11 items-center text-sm font-bold text-brand-700 hover:underline">
          {t("auth.oauth.backToLogin")}
        </Link>
      </AuthSplit>
    );
  }

  return (
    <AuthSplit pose="hello">
      <AuthTitle title={t("auth.oauth.finishing")} />
      <div role="status" aria-live="polite" className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-brand-600" />
      </div>
    </AuthSplit>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <OAuthCallback />
    </Suspense>
  );
}
