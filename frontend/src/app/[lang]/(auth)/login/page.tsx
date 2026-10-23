"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { AuthError, useAuth } from "@/lib/auth-context";
import { safeRedirect } from "@/lib/safeRedirect";
import { useBackendWarmup, useSlowHint } from "@/lib/useBackendWarmup";
import { VerifyEmailStep, authErrorMessage } from "@/components/auth/VerifyEmailStep";
import { Mail, Lock, ArrowRight, AlertCircle, Loader2 } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { lang, setLang, t } = useTranslation();
  const { signIn } = useAuth();

  const rawRedirect = searchParams.get("redirect");
  const safeParam = safeRedirect(rawRedirect, "");
  const redirectParam = safeParam || null;

  const [email, setEmail] = useState("");
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
      {/* Top Header with App Logo & Lang Switcher */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md px-4 flex items-center justify-between mb-8">
        <Link href={`/${lang}`} className="flex items-center space-x-3 group">
          <div className="w-10 h-10 rounded-xl bg-brand-600 flex items-center justify-center text-white font-bold text-lg shadow-sm shadow-brand-500/30">
            ОРТ
          </div>
          <div>
            <span className="font-bold text-lg tracking-tight text-slate-900 block leading-tight">
              {t("common.appName")}
            </span>
            <span className="text-xs text-slate-500 block">
              ЖРТ / ОРТ 2026
            </span>
          </div>
        </Link>

        <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs">
          <button
            onClick={() => setLang("ky")}
            className={`px-2 py-0.5 rounded font-semibold transition-all ${
              lang === "ky" ? "bg-white text-brand-600 shadow-2xs" : "text-slate-600"
            }`}
          >
            Кыргызча
          </button>
          <button
            onClick={() => setLang("ru")}
            className={`px-2 py-0.5 rounded font-semibold transition-all ${
              lang === "ru" ? "bg-white text-brand-600 shadow-2xs" : "text-slate-600"
            }`}
          >
            Русский
          </button>
        </div>
      </div>

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
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("auth.signInTitle")}
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              {t("auth.signInSubtitle")}
            </p>
          </div>

          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-2 text-rose-800 text-xs font-medium">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t("auth.email")}
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("auth.emailPlaceholder")}
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-slate-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-200 text-sm outline-none transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t("auth.password")}
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("auth.passwordPlaceholder")}
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-slate-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-200 text-sm outline-none transition-all"
                />
              </div>
              <div className="flex justify-end mt-1.5">
                <Link
                  href={`/${lang}/forgot-password`}
                  className="text-xs text-brand-600 hover:text-brand-700 font-semibold hover:underline"
                >
                  {t("auth.forgotPassword")}
                </Link>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-3 px-4 rounded-xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{t("auth.signingIn")}</span>
                </>
              ) : (
                <>
                  <span>{t("auth.signInButton")}</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
            {slow && <p className="text-[11px] text-center text-slate-500">{t("auth.wakingServer")}</p>}
          </form>

          {/* Link to Register */}
          <div className="mt-6 text-center text-xs text-slate-500">
            <span>{t("auth.noAccount")} </span>
            <Link
              href={`/${lang}/register${redirectParam ? `?redirect=${encodeURIComponent(redirectParam)}` : ""}`}
              className="text-brand-600 font-bold hover:underline"
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

