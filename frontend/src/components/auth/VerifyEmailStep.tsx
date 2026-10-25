"use client";

import React, { useEffect, useState } from "react";
import { ArrowRight, AlertCircle, CheckCircle2, KeyRound } from "lucide-react";
import { Button } from "@/components/ui";
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
        <p className="mt-1 text-sm text-slate-600">
          {reason === "registered" ? t("auth.verify.subtitle", { email }) : t("auth.verify.notVerifiedNotice", { email })}
        </p>
      </div>

      {error && (
        <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
          <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
          <span>{error}</span>
        </div>
      )}
      {info && (
        <div role="status" className="mb-5 flex items-start gap-2 rounded-xl border border-success-200 bg-success-50 p-3 text-sm font-medium text-success-800">
          <CheckCircle2 aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-success-700" />
          <span>{info}</span>
        </div>
      )}

      <form onSubmit={handleVerify} className="space-y-4">
        <div>
          <label htmlFor="email-code" className="mb-1 block text-sm font-medium text-slate-800">
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
            className="w-full rounded-xl border border-slate-300 px-4 py-3 text-center text-2xl font-bold tracking-[0.5em] outline-none transition-all focus:border-brand-600 focus:ring-2 focus:ring-brand-600/30"
          />
          <p className="mt-1.5 text-sm text-slate-600">{t("auth.verify.codeValidity", { minutes: codeTtlMinutes })}</p>
        </div>

        <Button type="submit" size="lg" fullWidth disabled={verifying || code.length !== 6} loading={verifying} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
          {verifying ? t("auth.verify.verifying") : t("auth.verify.button")}
        </Button>
      </form>

      <div className="mt-5 flex flex-col items-center justify-between gap-1 text-sm sm:flex-row">
        <button
          type="button"
          onClick={handleResend}
          disabled={cooldown > 0 || resending}
          className="inline-flex min-h-11 items-center font-semibold text-brand-700 hover:underline disabled:text-slate-500 disabled:no-underline"
        >
          {cooldown > 0 ? t("auth.verify.resendIn", { seconds: cooldown }) : t("auth.verify.resend")}
        </button>
        <button type="button" onClick={onChangeEmail} className="inline-flex min-h-11 items-center font-semibold text-slate-600 hover:underline">
          {t("auth.verify.changeEmail")}
        </button>
      </div>
    </div>
  );
};
