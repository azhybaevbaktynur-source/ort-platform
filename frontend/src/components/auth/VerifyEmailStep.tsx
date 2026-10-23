"use client";

import React, { useEffect, useState } from "react";
import { ArrowRight, AlertCircle, CheckCircle2, KeyRound, Loader2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { AuthError, useAuth } from "@/lib/auth-context";

type Translate = (key: string, params?: Record<string, string | number>) => string;

/** Turns an auth API error into a translated message (falls back to the server text). */
export function authErrorMessage(err: unknown, t: Translate, fallbackKey: string): string {
  if (err instanceof AuthError) {
    if (err.code) {
      const key = `auth.errors.${err.code}`;
      const params = Object.fromEntries(Object.entries(err.details).map(([k, v]) => [k, String(v)]));
      const translated = t(key, params);
      if (translated !== key) return translated;
    }
    return err.message || t(fallbackKey);
  }
  if (err instanceof TypeError) return t("auth.errors.network"); // fetch failed: server unreachable
  return (err as Error)?.message || t(fallbackKey);
}

interface VerifyEmailStepProps {
  email: string;
  password: string;
  resendAfterSeconds: number;
  codeTtlMinutes?: number;
  /** "registered": just signed up; "notVerified": tried to log in with an unverified account */
  reason: "registered" | "notVerified";
  onVerified: () => void;
  onChangeEmail: () => void;
}

export const VerifyEmailStep: React.FC<VerifyEmailStepProps> = ({
  email,
  password,
  resendAfterSeconds,
  codeTtlMinutes = 10,
  reason,
  onVerified,
  onChangeEmail,
}) => {
  const { t } = useTranslation();
  const { verifyEmail, resendCode } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [resending, setResending] = useState(false);
  const [cooldown, setCooldown] = useState(resendAfterSeconds);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setVerifying(true);
    try {
      await verifyEmail(email, password, code);
      onVerified();
    } catch (err) {
      setError(authErrorMessage(err, t, "auth.registerError"));
    } finally {
      setVerifying(false);
    }
  };

  const handleResend = async () => {
    setError(null);
    setInfo(null);
    setResending(true);
    try {
      const res = await resendCode(email);
      setCode("");
      setInfo(t("auth.verify.resent", { email }));
      setCooldown(res.resendAfterSeconds || 60);
    } catch (err) {
      if (err instanceof AuthError && typeof err.details.retryAfterSeconds === "number") {
        setCooldown(err.details.retryAfterSeconds);
      }
      setError(authErrorMessage(err, t, "auth.registerError"));
    } finally {
      setResending(false);
    }
  };

  return (
    <div>
      <div className="mb-6 text-center">
        <div className="w-12 h-12 mx-auto mb-3 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center">
          <KeyRound className="w-6 h-6" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-900">{t("auth.verify.title")}</h2>
        <p className="mt-1 text-xs text-slate-500">
          {reason === "registered" ? t("auth.verify.subtitle", { email }) : t("auth.verify.notVerifiedNotice", { email })}
        </p>
      </div>

      {error && (
        <div className="mb-5 p-3 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-2 text-rose-800 text-xs font-medium">
          <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {info && (
        <div className="mb-5 p-3 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center gap-2 text-emerald-800 text-xs font-medium">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{info}</span>
        </div>
      )}

      <form onSubmit={handleVerify} className="space-y-4">
        <div>
          <label htmlFor="email-code" className="block text-xs font-semibold text-slate-700 mb-1">
            {t("auth.verify.codeLabel")}
          </label>
          <input
            id="email-code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            required
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="000000"
            className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-200 text-center text-2xl font-bold tracking-[0.5em] outline-none transition-all"
          />
          <p className="mt-1.5 text-[11px] text-slate-500">{t("auth.verify.codeValidity", { minutes: codeTtlMinutes })}</p>
        </div>

        <button
          type="submit"
          disabled={verifying || code.length !== 6}
          className="w-full py-3 px-4 rounded-xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-700 shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-60"
        >
          {verifying ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{t("auth.verify.verifying")}</span>
            </>
          ) : (
            <>
              <span>{t("auth.verify.button")}</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>

      <div className="mt-5 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs">
        <button
          type="button"
          onClick={handleResend}
          disabled={cooldown > 0 || resending}
          className="font-semibold text-brand-600 hover:underline disabled:text-slate-400 disabled:no-underline"
        >
          {cooldown > 0 ? t("auth.verify.resendIn", { seconds: cooldown }) : t("auth.verify.resend")}
        </button>
        <button type="button" onClick={onChangeEmail} className="font-semibold text-slate-500 hover:underline">
          {t("auth.verify.changeEmail")}
        </button>
      </div>
    </div>
  );
};
