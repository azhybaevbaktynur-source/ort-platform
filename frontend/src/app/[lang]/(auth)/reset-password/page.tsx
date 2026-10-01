"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { Lock, ArrowRight, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { lang, setLang, t } = useTranslation();

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
        lang === "ky"
          ? "Жараксыз шилтеме же токен табылган жок"
          : "Недействительная ссылка или токен не найден"
      );
      return;
    }

    if (newPassword !== confirmPassword) {
      setError(
        lang === "ky"
          ? "Сырсөздөр бири-бирине дал келбейт"
          : "Пароли не совпадают"
      );
      return;
    }

    if (newPassword.length < 6) {
      setError(
        lang === "ky"
          ? "Сырсөз кеминде 6 белгиден турушу керек"
          : "Пароль должен содержать не менее 6 символов"
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
        throw new Error(err.detail || "Failed to reset password");
      }

      setSuccess(true);
    } catch (err: any) {
      setError(err?.message || "Failed to reset password");
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
          <div className="mb-6 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">
              {t("auth.resetPasswordTitle")}
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              {t("auth.resetPasswordSubtitle")}
            </p>
          </div>

          {!token && (
            <div className="mb-5 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs font-medium flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>
                {lang === "ky"
                  ? "Сырсөздү калыбына келтирүү токени табылган жок. Шилтемени кайра сураңыз."
                  : "Токен сброса пароля отсутствует. Запросите новую ссылку для сброса."}
              </span>
            </div>
          )}

          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-2 text-rose-800 text-xs font-medium">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {success ? (
            <div className="space-y-4">
              <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium flex items-start gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-emerald-900 mb-1">
                    {lang === "ky" ? "Сырсөз жаңыртылды!" : "Пароль обновлен!"}
                  </p>
                  <p className="text-emerald-700 leading-relaxed">
                    {t("auth.passwordResetSuccess")}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => router.push(`/${lang}/login`)}
                className="w-full py-3 px-4 rounded-xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-sm transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                <span>{t("auth.signInButton")}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("auth.newPassword")}
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder={t("auth.passwordPlaceholder")}
                    className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-slate-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-200 text-sm outline-none transition-all"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("auth.confirmNewPassword")}
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder={t("auth.passwordPlaceholder")}
                    className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-slate-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-200 text-sm outline-none transition-all"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !token}
                className="w-full mt-2 py-3 px-4 rounded-xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-60 cursor-pointer"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{t("common.loading")}</span>
                  </>
                ) : (
                  <>
                    <span>{t("auth.resetPasswordButton")}</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>

              <div className="mt-4 text-center">
                <Link
                  href={`/${lang}/login`}
                  className="text-xs text-slate-500 hover:text-brand-600 font-semibold transition"
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

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}

