"use client";

import React, { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { AuthAlert, AuthSplit, AuthTitle } from "@/components/auth/AuthSplit";
import { ProviderButtons } from "@/components/auth/ProviderButtons";
import { Button, Input } from "@/components/ui";
import { AuthError, storedSessionProfile, useAuth } from "@/lib/auth-context";
import { prefetchBootstrap } from "@/lib/lms/bootstrap";
import { safeRedirect } from "@/lib/safeRedirect";
import { useBackendWarmup, useSlowHint } from "@/lib/useBackendWarmup";
import { VerifyEmailStep, authErrorMessage } from "@/components/auth/VerifyEmailStep";
import { MfaStep } from "@/components/auth/MfaStep";
import { Mail, Lock, ArrowRight } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { lang, t } = useTranslation();
  const { signIn } = useAuth();

  const rawRedirect = searchParams.get("redirect");
  const safeParam = safeRedirect(rawRedirect, "");
  const redirectParam = safeParam || null;

  const [email, setEmail] = useState(searchParams.get("email") || ""); // Phase 6 S4: prefilled from an invitation
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Set when the account exists but its email has not been confirmed with the emailed code yet
  const [pendingVerification, setPendingVerification] = useState<{ email: string; resendAfterSeconds: number } | null>(null);
  // S1: the password was right and the account has two-step login: the challenge for the code step
  const [mfaChallenge, setMfaChallenge] = useState<string | null>(null);

  // Social sign-in refused: the backend sent us back with ?oauth_error=<code>; shown once, then removed from the URL
  useEffect(() => {
    const code = searchParams.get("oauth_error");
    if (!code) return;
    const key = `auth.errors.${code}`;
    const text = t(key);
    setError(text !== key ? text : t("auth.loginError"));
    const url = new URL(window.location.href);
    url.searchParams.delete("oauth_error");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useBackendWarmup();
  const slow = useSlowHint(loading);

  const handleNavigateAfterAuth = () => {
    const dest = redirectParam || `/${lang}/courses`;
    // PERFORMANCE_AUDIT P3: the token is stored; the first page's bootstrap starts now, alongside the route change
    prefetchBootstrap(dest, !!storedSessionProfile()?.is_platform_admin);
    router.push(dest);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await signIn(email, password);
      handleNavigateAfterAuth();
    } catch (err) {
      if (err instanceof AuthError && err.code === "mfa_required" && typeof err.details.challenge === "string") {
        setMfaChallenge(err.details.challenge);
      } else if (err instanceof AuthError && err.code === "email_not_verified" && err.details.codeSent === false) {
        // Account not verified and the new code could not be emailed: say so instead of waiting for a code
        setError(t("auth.errors.email_send_failed"));
      } else if (err instanceof AuthError && err.code === "email_not_verified") {
        const wait = err.details.resendAfterSeconds;
        setPendingVerification({
          email: String(err.details.email || email.trim().toLowerCase()),
          resendAfterSeconds: typeof wait === "number" ? wait : 60,
        });
      } else {
        setError(authErrorMessage(err, t, "auth.loginError"));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthSplit pose="reading">
      {mfaChallenge ? (
        <MfaStep
          challenge={mfaChallenge}
          onDone={handleNavigateAfterAuth}
          onRestart={(message) => { setMfaChallenge(null); setPassword(""); setError(message || null); }}
        />
      ) : pendingVerification ? (
        <VerifyEmailStep
          email={pendingVerification.email}
          password={password}
          resendAfterSeconds={pendingVerification.resendAfterSeconds}
          reason="notVerified"
          onVerified={handleNavigateAfterAuth}
          onChangeEmail={() => setPendingVerification(null)}
        />
      ) : (
        <>
          <AuthTitle title={t("auth.signInTitle")} subtitle={t("auth.signInSubtitle")} />

          <ProviderButtons redirect={redirectParam} />

          {error && <AuthAlert>{error}</AuthAlert>}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input label={t("auth.email")} leading={<Mail className="h-4 w-4" />} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("auth.emailPlaceholder")} />

            <div>
              <Input label={t("auth.password")} leading={<Lock className="h-4 w-4" />} type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("auth.passwordPlaceholder")} />
              <div className="flex justify-end mt-1.5">
                <Link
                  href={`/${lang}/forgot-password`}
                  className="inline-flex min-h-11 items-center text-sm text-brand-700 hover:text-brand-800 font-semibold hover:underline sm:min-h-0"
                >
                  {t("auth.forgotPassword")}
                </Link>
              </div>
            </div>

            <Button type="submit" size="lg" fullWidth disabled={loading} loading={loading} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
              {loading ? t("auth.signingIn") : t("auth.signInButton")}
            </Button>
            {slow && <p className="text-sm text-center text-slate-600">{t("auth.wakingServer")}</p>}
          </form>

          <div className="mt-6 text-center text-sm text-slate-600">
            <span>{t("auth.noAccount")} </span>
            <Link
              href={`/${lang}/register${redirectParam ? `?redirect=${encodeURIComponent(redirectParam)}` : ""}`}
              className="inline-flex min-h-11 items-center text-brand-700 font-bold hover:underline sm:min-h-0"
            >
              {t("auth.signUpButton")}
            </Link>
          </div>
        </>
      )}
    </AuthSplit>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <LoginForm />
    </Suspense>
  );
}

