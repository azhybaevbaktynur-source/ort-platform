"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { AuthHeader } from "@/components/auth/AuthHeader";
import { Button, Input, buttonClasses } from "@/components/ui";
import { Lock, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { lang, t } = useTranslation();

  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!token) {
      setError(
        t("auth.resetInvalidToken")
      );
      return;
    }

    if (newPassword !== confirmPassword) {
      setError(
        t("auth.passwordsMismatch")
      );
      return;
    }

    if (newPassword.length < 6) {
      setError(
        t("auth.passwordTooShort")
      );
      return;
    }

    setLoading(true);

    try {
      const res = await fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          new_password: newPassword,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || t("auth.resetFailed"));
      }

      setSuccess(true);
    } catch (err: any) {
      setError(err?.message || t("auth.resetFailed"));
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
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("auth.resetPasswordTitle")}
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              {t("auth.resetPasswordSubtitle")}
            </p>
          </div>

          {!token && (
            <div className="mb-5 p-3 rounded-xl bg-warning-50 border border-warning-200 text-warning-900 text-sm font-medium flex items-center gap-2">
              <AlertCircle aria-hidden="true" className="w-4 h-4 text-warning-700 shrink-0" />
              <span>
                {t("auth.resetTokenMissing")}
              </span>
            </div>
          )}

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
                    {t("auth.passwordUpdated")}
                  </p>
                  <p className="text-success-800 leading-relaxed">
                    {t("auth.passwordResetSuccess")}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => router.push(`/${lang}/login`)}
                className={buttonClasses({ size: "lg", fullWidth: true })}
              >
                <span>{t("auth.signInButton")}</span>
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input label={t("auth.newPassword")} leading={<Lock className="h-4 w-4" />} type="password" required minLength={6} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder={t("auth.passwordPlaceholder")} />

              <Input label={t("auth.confirmNewPassword")} leading={<Lock className="h-4 w-4" />} type="password" required minLength={6} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder={t("auth.passwordPlaceholder")} />

              <Button type="submit" size="lg" fullWidth disabled={loading || !token} loading={loading} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
              {loading ? t("common.loading") : t("auth.resetPasswordButton")}
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

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <ResetPasswordForm />
    </Suspense>
  );
}

