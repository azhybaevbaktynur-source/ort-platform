"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { AuthHeader } from "@/components/auth/AuthHeader";
import { Button, Input } from "@/components/ui";
import { AuthError, useAuth } from "@/lib/auth-context";
import { safeRedirect } from "@/lib/safeRedirect";
import { useBackendWarmup, useSlowHint } from "@/lib/useBackendWarmup";
import { VerifyEmailStep, authErrorMessage } from "@/components/auth/VerifyEmailStep";
import { Mail, Lock, ArrowRight, AlertCircle } from "lucide-react";

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

  useBackendWarmup();
  const slow = useSlowHint(loading);

  const handleNavigateAfterAuth = () => {
    router.push(redirectParam || `/${lang}/courses`);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await signIn(email, password);
      handleNavigateAfterAuth();
    } catch (err) {
      if (err instanceof AuthError && err.code === "email_not_verified" && err.details.codeSent === false) {
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
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <AuthHeader />

      <div className="sm:mx-auto sm:w-full sm:max-w-md px-4">
        <div className="bg-white py-8 px-6 sm:px-10 shadow-lg border border-slate-200/80 rounded-3xl">
          {pendingVerification ? (
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
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("auth.signInTitle")}
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              {t("auth.signInSubtitle")}
            </p>
          </div>

          {error && (
            <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
              <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input label={t("auth.email")} leading={<Mail className="h-4 w-4" />} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("auth.emailPlaceholder")} />

            <div>
              <Input label={t("auth.password")} leading={<Lock className="h-4 w-4" />} type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("auth.passwordPlaceholder")} />
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

          {/* Link to Register */}
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
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <LoginForm />
    </Suspense>
  );
}

