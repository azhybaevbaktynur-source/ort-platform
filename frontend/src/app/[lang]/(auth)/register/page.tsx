"use client";

import React, { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { AuthHeader } from "@/components/auth/AuthHeader";
import { Button, Input } from "@/components/ui";
import { useAuth, RegisterResult } from "@/lib/auth-context";
import { safeRedirect } from "@/lib/safeRedirect";
import { useBackendWarmup, useSlowHint } from "@/lib/useBackendWarmup";
import { VerifyEmailStep, authErrorMessage } from "@/components/auth/VerifyEmailStep";
import { AgeButtons } from "@/components/privacy/AgeButtons";
import { PolicyAccept } from "@/components/privacy/PolicyAccept";
import { getPolicies, ownPolicyIds, type AgeBand, type PolicyOut } from "@/components/privacy/privacyApi";
import { PrivacyError, ownPrivacyErrorText } from "@/components/privacy/privacyErrors";
import { Mail, Lock, User, Phone, ArrowRight, AlertCircle } from "lucide-react";

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { lang, t } = useTranslation();
  const { signUp } = useAuth();

  const rawRedirect = searchParams.get("redirect");
  const safeParam = safeRedirect(rawRedirect, "");
  const redirectParam = safeParam || null;

  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
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
  const [policies, setPolicies] = useState<PolicyOut[] | null>(null);
  const [policiesError, setPoliciesError] = useState<unknown>(null);
  const needsPolicies = !!band && band !== "under_14";

  const loadPolicies = () => {
    setPoliciesError(null);
    getPolicies(lang).then(setPolicies).catch(setPoliciesError);
  };
  useEffect(() => {
    if (needsPolicies && !policies) loadPolicies();
  }, [needsPolicies]); // eslint-disable-line react-hooks/exhaustive-deps

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
      router.push(`/${lang}/courses`);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      setRegistered(await signUp(email, password, displayName, phone, {
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
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <AuthHeader />

      <div className="sm:mx-auto sm:w-full sm:max-w-md px-4">
        <div className="bg-white py-8 px-6 sm:px-10 shadow-lg border border-slate-200/80 rounded-3xl">
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
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("auth.signUpTitle")}
            </h1>
            {band && (
              <p className="mt-1 text-sm text-slate-600">
                {t("auth.signUpSubtitle")}
              </p>
            )}
          </div>

          {!band ? (
            <>
              <AgeButtons onChoose={(b) => { setAsParent(false); setBand(b); }} />
              <div className="mt-3 text-center">
                <Button type="button" variant="link" onClick={() => { setAsParent(true); setBand("18_plus"); }}>{t("privacy.parentLink")}</Button>
              </div>
            </>
          ) : (
          <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-100 px-3 py-1">
            <span className="min-w-0 break-words text-sm font-medium text-slate-800">
              {asParent ? t("privacy.parentLink") : `${t("privacy.age.label")}: ${t(`privacy.age.${band}`)}`}
            </span>
            <Button type="button" variant="link" size="sm" onClick={() => { setBand(null); setAccepted(false); setError(null); }}>{t("privacy.age.change")}</Button>
          </div>

          {error && (
            <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
              <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input label={t("auth.displayName")} leading={<User className="h-4 w-4" />} type="text" required value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder={t("auth.displayNamePlaceholder")} />

            <Input label={t("auth.phone")} leading={<Phone className="h-4 w-4" />} type="tel" required value={phone} onChange={(e) => setPhone(e.target.value)} placeholder={t("auth.phonePlaceholder")} />

            <Input label={t("auth.email")} leading={<Mail className="h-4 w-4" />} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("auth.emailPlaceholder")} />

            <Input label={t("auth.password")} leading={<Lock className="h-4 w-4" />} type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("auth.passwordPlaceholder")} />

            {needsPolicies && <PolicyAccept checked={accepted} onChange={setAccepted} required />}
            {needsPolicies && policiesError ? (
              <div className="space-y-2">
                <PrivacyError error={policiesError} />
                <Button type="button" variant="secondary" size="sm" onClick={loadPolicies}>{t("lms.common.retry")}</Button>
              </div>
            ) : null}

            <Button type="submit" size="lg" fullWidth disabled={loading || (needsPolicies && !policies)} loading={loading} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
              {loading ? t("auth.signingUp") : t("auth.signUpButton")}
            </Button>
            {slow && <p className="text-sm text-center text-slate-600">{t("auth.wakingServer")}</p>}
          </form>
          </>
          )}

          {/* Link to Login */}
          <div className="mt-6 text-center text-sm text-slate-600">
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
        </div>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <RegisterForm />
    </Suspense>
  );
}

