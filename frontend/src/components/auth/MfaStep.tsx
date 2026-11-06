"use client";

import React, { useState } from "react";
import { AlertCircle, ArrowRight, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { AuthError, useAuth } from "@/lib/auth-context";
import { authErrorMessage } from "@/components/auth/VerifyEmailStep";

interface MfaStepProps {
  /** From the `mfa_required` answer of the password step. */
  challenge: string;
  onDone: () => void;
  /** The step expired or was refused: back to the password, with this message. */
  onRestart: (message: string) => void;
}

/** S1 admin security: the second sign-in step (authenticator app code, or a one-time recovery code). */
export function MfaStep({ challenge, onDone, onRestart }: MfaStepProps) {
  const { t } = useTranslation();
  const { completeMfa } = useAuth();
  const [recovery, setRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ready = recovery ? code.replace(/[^a-z0-9]/gi, "").length === 10 : code.length === 6;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await completeMfa(challenge, code);
      onDone();
    } catch (err) {
      const message = authErrorMessage(err, t, "auth.loginError");
      if (err instanceof AuthError && err.code === "mfa_challenge_invalid") onRestart(message);
      else {
        setError(message);
        setCode("");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-6 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
          <ShieldCheck aria-hidden="true" className="h-6 w-6" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{t("auth.mfa.title")}</h1>
        <p className="mt-1 text-sm text-slate-600">{recovery ? t("auth.mfa.recoverySubtitle") : t("auth.mfa.subtitle")}</p>
      </div>

      {error && (
        <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
          <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor="mfa-code" className="mb-1 block text-sm font-medium text-slate-800">
            {recovery ? t("auth.mfa.recoveryLabel") : t("auth.mfa.codeLabel")}
          </label>
          <input
            id="mfa-code"
            key={recovery ? "recovery" : "totp"}
            type="text"
            inputMode={recovery ? "text" : "numeric"}
            autoComplete="one-time-code"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={recovery ? 11 : 6}
            required
            autoFocus
            value={code}
            onChange={(e) => setCode(recovery ? e.target.value.slice(0, 11) : e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder={recovery ? "xxxxx-xxxxx" : "000000"}
            className="w-full rounded-xl border border-slate-300 px-4 py-3 text-center text-2xl font-bold tracking-[0.3em] outline-none transition-all focus:border-brand-600 focus:ring-2 focus:ring-brand-600/30"
          />
        </div>
        <Button type="submit" size="lg" fullWidth disabled={busy || !ready} loading={busy} rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
          {t("auth.mfa.button")}
        </Button>
      </form>

      <div className="mt-5 flex flex-col items-center justify-between gap-1 text-sm sm:flex-row">
        <button type="button" onClick={() => { setRecovery(!recovery); setCode(""); setError(null); }}
          className="inline-flex min-h-11 items-center font-semibold text-brand-700 hover:underline">
          {recovery ? t("auth.mfa.useApp") : t("auth.mfa.useRecovery")}
        </button>
        <button type="button" onClick={() => onRestart("")} className="inline-flex min-h-11 items-center font-semibold text-slate-600 hover:underline">
          {t("auth.mfa.back")}
        </button>
      </div>
    </div>
  );
}
