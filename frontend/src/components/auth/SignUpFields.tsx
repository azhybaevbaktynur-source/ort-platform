"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Lock, Mail, User } from "lucide-react";
import { Button, Input } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { PolicyAccept } from "@/components/privacy/PolicyAccept";
import { PrivacyError } from "@/components/privacy/privacyErrors";
import { getPolicies, type PolicyOut } from "@/components/privacy/privacyApi";

/** The API's own limit (`UserRegisterRequest.password`). */
export const PASSWORD_MIN_LENGTH = 6;

type TextProps = { value: string; onChange: (value: string) => void };

/** The account fields of every sign-up page (`/register`, `/for-teachers/apply`), one rule set. */
export function SignUpNameInput({ value, onChange }: TextProps) {
  const { t } = useTranslation();
  return <Input label={t("auth.displayName")} leading={<User className="h-4 w-4" />} type="text" required autoComplete="name" value={value} onChange={(e) => onChange(e.target.value)} placeholder={t("auth.displayNamePlaceholder")} />;
}

export function SignUpEmailInput({ value, onChange }: TextProps) {
  const { t } = useTranslation();
  return <Input label={t("auth.email")} leading={<Mail className="h-4 w-4" />} type="email" required autoComplete="email" value={value} onChange={(e) => onChange(e.target.value)} placeholder={t("auth.emailPlaceholder")} />;
}

export function SignUpPasswordInput({ value, onChange }: TextProps) {
  const { t } = useTranslation();
  return <Input label={t("auth.password")} leading={<Lock className="h-4 w-4" />} type="password" required minLength={PASSWORD_MIN_LENGTH} autoComplete="new-password" value={value} onChange={(e) => onChange(e.target.value)} placeholder={t("auth.passwordPlaceholder")} />;
}

export interface OwnPolicies {
  policies: PolicyOut[] | null;
  error: unknown;
  reload: () => void;
}

/** The current privacy and terms versions, once `needed`. */
export function useOwnPolicies(needed: boolean): OwnPolicies {
  const { lang } = useTranslation();
  const [policies, setPolicies] = useState<PolicyOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const reload = useCallback(() => {
    setError(null);
    getPolicies(lang).then(setPolicies).catch(setError);
  }, [lang]);
  useEffect(() => {
    if (needed && !policies) reload();
  }, [needed]); // eslint-disable-line react-hooks/exhaustive-deps
  return { policies, error, reload };
}

/** "I accept the privacy policy and terms of use", and a retry when the versions could not be loaded. */
export function PolicyAcceptField({ state, checked, onChange, error, id }: {
  state: OwnPolicies;
  checked: boolean;
  onChange: (value: boolean) => void;
  error?: React.ReactNode;
  id?: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      <PolicyAccept checked={checked} onChange={onChange} required error={error} id={id} />
      {state.error ? (
        <div className="space-y-2">
          <PrivacyError error={state.error} />
          <Button type="button" variant="secondary" size="sm" onClick={state.reload}>{t("lms.common.retry")}</Button>
        </div>
      ) : null}
    </>
  );
}
