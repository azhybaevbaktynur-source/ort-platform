"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { AuthHeader } from "@/components/auth/AuthHeader";
import { Button, Input, buttonClasses } from "@/components/ui";
import { useBackendWarmup } from "@/lib/useBackendWarmup";
import { Mail, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";

function ForgotPasswordForm() {
  const { lang, t } = useTranslation();

  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useBackendWarmup();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), lang }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || t("auth.forgotFailed"));
      }

      setSuccess(true);
    } catch (err: any) {
      setError(err?.message || t("auth.forgotFailed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <AuthHeader />

      <div className="sm:mx-auto sm:w-full sm:max-w-md px-4">
        <div className="bg-white py-8 px-6 sm:px-10 shadow-lg border border-slate-200/80 rounded-3xl">
          <div className="mb-6 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("auth.forgotPasswordTitle")}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {t("auth.forgotPasswordSubtitle")}
            </p>
          </div>

          {error && (
            <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
              <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
              <span>{error}</span>
            </div>
          )}

          {success ? (
            <div className="space-y-4">
              <div className="p-4 rounded-2xl bg-success-50 border border-success-200 text-success-800 text-sm font-medium flex items-start gap-3">
                <CheckCircle2 aria-hidden="true" className="w-5 h-5 text-success-700 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-success-900 mb-1">
                    {t("auth.resetLinkSentTitle")}
                  </p>
                  <p className="text-success-800 leading-relaxed">
                    {t("auth.resetLinkSent")}
                  </p>
                </div>
              </div>

              <Link
                href={`/${lang}/login`}
                className={buttonClasses({ size: "lg", fullWidth: true })}
              >
                <span>{t("auth.backToLogin")}</span>
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input label={t("auth.email")} leading={<Mail className="h-4 w-4" />} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("auth.emailPlaceholder")} />

              <Button type="submit" size="lg" fullWidth disabled={loading} loading={loading} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
              {loading ? t("common.loading") : t("auth.sendResetLink")}
            </Button>

              <div className="mt-4 text-center">
                <Link
                  href={`/${lang}/login`}
                  className="inline-flex min-h-11 items-center text-sm text-slate-600 hover:text-brand-700 font-semibold transition"
                >
                  ← {t("auth.backToLogin")}
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

function LoadingFallback() {
  const { t } = useTranslation();
  return <div className="min-h-screen flex items-center justify-center">{t("common.loading")}</div>;
}

export default function ForgotPasswordPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <ForgotPasswordForm />
    </Suspense>
  );
}

