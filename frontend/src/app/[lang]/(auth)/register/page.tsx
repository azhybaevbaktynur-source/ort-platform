"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { AuthAlert, AuthSplit, AuthTitle } from "@/components/auth/AuthSplit";
import { AgeRow } from "@/components/auth/AgeRow";
import { ProviderButtons } from "@/components/auth/ProviderButtons";
import { Button } from "@/components/ui";
import { useAuth, RegisterResult } from "@/lib/auth-context";
import { safeRedirect } from "@/lib/safeRedirect";
import { chooseCoursesHref } from "@/lib/lms/chooseCourses";
import { useBackendWarmup, useSlowHint } from "@/lib/useBackendWarmup";
import { VerifyEmailStep, authErrorMessage } from "@/components/auth/VerifyEmailStep";
import { PolicyAcceptField, SignUpEmailInput, SignUpNameInput, SignUpPasswordInput, useOwnPolicies } from "@/components/auth/SignUpFields";
import { ownPolicyIds, type AgeBand } from "@/components/privacy/privacyApi";
import { ownPrivacyErrorText } from "@/components/privacy/privacyErrors";
import { ArrowRight } from "lucide-react";

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { lang, t } = useTranslation();
  const { signUp } = useAuth();

  const rawRedirect = searchParams.get("redirect");
  const safeParam = safeRedirect(rawRedirect, "");
  const redirectParam = safeParam || null;

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState(searchParams.get("email") || ""); // Phase 6 S4: prefilled from an invitation
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Step 2: the account is created but must be confirmed with the code emailed to the user
  const [registered, setRegistered] = useState<RegisterResult | null>(null);
  // Phase 11 S3 (PHASE_11_DESIGN 3.2, 4): the age comes first; a parent is an adult who goes on to `/parent`
  const [band, setBand] = useState<AgeBand | null>(null);
  const [asParent, setAsParent] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const needsPolicies = !!band && band !== "under_14";
  const policyState = useOwnPolicies(needsPolicies);
  const { policies } = policyState;

  useBackendWarmup();
  const slow = useSlowHint(loading);

  const goToApp = () => {
    if (band === "under_14") {
      router.push(`/${lang}/privacy`); // nothing else works until a parent consents
    } else if (asParent) {
      router.push(`/${lang}/parent`);
    } else if (redirectParam) {
      router.push(redirectParam);
    } else {
      // step 3a S4 (STUDENT_IA_DESIGN §4, decision N7): the skippable choose step; nothing is joined without a tap
      router.push(`${chooseCoursesHref(lang)}?first=1`);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      setRegistered(await signUp(email, password, displayName, undefined, {
        ageBand: band as AgeBand,
        policyVersionIds: needsPolicies ? ownPolicyIds(policies ?? []) : [],
      }));
    } catch (err) {
      setError(ownPrivacyErrorText(t, err) ?? authErrorMessage(err, t, "auth.registerError"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthSplit pose="hello">
      {registered ? (
        <VerifyEmailStep
          email={registered.email}
          password={password}
          resendAfterSeconds={registered.resendAfterSeconds}
          codeTtlMinutes={registered.codeTtlMinutes}
          reason="registered"
          onVerified={goToApp}
          onChangeEmail={() => setRegistered(null)}
        />
      ) : (
        <>
          <AuthTitle title={t("auth.signUpTitle")} subtitle={t("auth.signUpSubtitle")} />

          <ProviderButtons redirect={redirectParam} />

          {error && <AuthAlert>{error}</AuthAlert>}

          <form onSubmit={handleSubmit} className="space-y-4">
            <SignUpNameInput value={displayName} onChange={setDisplayName} />
            <SignUpEmailInput value={email} onChange={setEmail} />
            <SignUpPasswordInput value={password} onChange={setPassword} />

            <AgeRow value={band} onChoose={(b) => { setAsParent(false); setBand(b); if (b === "under_14") setAccepted(false); }} />

            {needsPolicies && <PolicyAcceptField state={policyState} checked={accepted} onChange={setAccepted} />}

            <Button type="submit" size="lg" fullWidth disabled={loading || !band || (needsPolicies && !policies)} loading={loading} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
              {loading ? t("auth.signingUp") : t("auth.signUpButton")}
            </Button>
            {slow && <p className="text-sm text-center text-slate-600">{t("auth.wakingServer")}</p>}
          </form>

          <div className="mt-3 text-center">
            <Button type="button" variant="link" onClick={() => { setAsParent(true); setBand("18_plus"); }}>{t("auth.parentCta")}</Button>
            {asParent && <p className="text-sm text-slate-600">{t("privacy.parentLink")}</p>}
          </div>

          <div className="mt-4 text-center text-sm text-slate-600">
            <span>{t("auth.haveAccount")} </span>
            <Link
              href={`/${lang}/login${redirectParam ? `?redirect=${encodeURIComponent(redirectParam)}` : ""}`}
              className="inline-flex min-h-11 items-center text-brand-700 font-bold hover:underline sm:min-h-0"
            >
              {t("auth.signInButton")}
            </Link>
          </div>
        </>
      )}
    </AuthSplit>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <RegisterForm />
    </Suspense>
  );
}

