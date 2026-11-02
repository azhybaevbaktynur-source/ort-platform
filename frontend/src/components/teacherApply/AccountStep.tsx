"use client";

import React, { useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { AuthError, useAuth, type RegisterResult } from "@/lib/auth-context";
import { useSlowHint } from "@/lib/useBackendWarmup";
import { Button, Checkbox, cn, focusRing } from "@/components/ui";
import { authErrorMessage } from "@/components/auth/VerifyEmailStep";
import { PolicyAcceptField, SignUpEmailInput, SignUpNameInput, SignUpPasswordInput, useOwnPolicies } from "@/components/auth/SignUpFields";
import { ownPolicyIds } from "@/components/privacy/privacyApi";
import { ownPrivacyErrorText } from "@/components/privacy/privacyErrors";
import { loginBackHref } from "./paths";

export interface AccountForm {
  name: string;
  email: string;
  password: string;
  adult: boolean;
  accepted: boolean;
}
export const EMPTY_ACCOUNT: AccountForm = { name: "", email: "", password: "", adult: false, accepted: false };

/** The register route's plain 400 for an email with a verified account. */
const isEmailTaken = (err: unknown) => err instanceof AuthError && err.status === 400 && !err.code;

/** Step 1: the same register call as `/register`, always as an adult. */
export function AccountStep({ form, onChange, onRegistered }: {
  form: AccountForm;
  onChange: (form: AccountForm) => void;
  onRegistered: (result: RegisterResult) => void;
}) {
  const { lang, t } = useTranslation();
  const { signUp } = useAuth();
  const policyState = useOwnPolicies(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const slow = useSlowHint(busy);
  const set = (patch: Partial<AccountForm>) => onChange({ ...form, ...patch });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setEmailTaken(false);
    setBusy(true);
    try {
      onRegistered(await signUp(form.email, form.password, form.name, undefined, {
        ageBand: "18_plus",
        policyVersionIds: ownPolicyIds(policyState.policies ?? []),
      }));
    } catch (err) {
      if (isEmailTaken(err)) setEmailTaken(true);
      else setError(ownPrivacyErrorText(t, err) ?? authErrorMessage(err, t, "auth.registerError"));
    } finally {
      setBusy(false);
    }
  };

  const alertBox = "mb-4 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800";
  const loginLink = cn("inline-flex min-h-11 items-center rounded-md font-semibold text-brand-700 underline-offset-4 hover:underline", focusRing);
  return (
    <div>
      <h2 className="mb-4 text-xl font-bold leading-7 text-slate-900">{t("teacherApply.account.title")}</h2>
      {error && (
        <div role="alert" className={alertBox}>
          <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
          <span className="min-w-0 break-words">{error}</span>
        </div>
      )}
      {emailTaken && (
        <div role="alert" className={alertBox}>
          <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
          <div className="min-w-0">
            <p>{t("teacherApply.account.emailTaken")}</p>
            <Link href={loginBackHref(lang)} className={loginLink}>{t("teacherApply.account.emailTakenLink")}</Link>
          </div>
        </div>
      )}
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <SignUpNameInput value={form.name} onChange={(name) => set({ name })} />
        <SignUpEmailInput value={form.email} onChange={(email) => set({ email })} />
        <SignUpPasswordInput value={form.password} onChange={(password) => set({ password })} />
        <div>
          <Checkbox label={t("teacherApply.age")} required checked={form.adult} onChange={(e) => set({ adult: e.target.checked })} />
          <PolicyAcceptField state={policyState} checked={form.accepted} onChange={(accepted) => set({ accepted })} />
        </div>
        <Button type="submit" size="lg" fullWidth disabled={busy || !policyState.policies} loading={busy}
          rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
          {busy ? t("auth.signingUp") : t("teacherApply.account.submit")}
        </Button>
        {slow && <p className="text-center text-sm text-slate-600">{t("auth.wakingServer")}</p>}
      </form>
      <div className="mt-4 text-center text-sm text-slate-600">
        <span>{t("auth.haveAccount")} </span>
        <Link href={loginBackHref(lang)} className={loginLink}>{t("auth.signInButton")}</Link>
      </div>
    </div>
  );
}
