"use client";

// S4 email change (A9): the page of the link sent to the new address. The change happens on the button, not on load,
// so a mail scanner that opens links cannot use it up. Afterwards every session of the account has ended, so this
// browser signs out when it is signed in as that account (another account's session stays).
import React, { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, ArrowRight, CheckCircle2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { confirmEmailChange } from "@/lib/lms/emailChange";
import { AuthSplit, AuthTitle } from "@/components/auth/AuthSplit";
import { Button, buttonClasses } from "@/components/ui";
import { useApiErrorText } from "@/components/lms/org/OrgUi";

function ConfirmEmailForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { lang, t } = useTranslation();
  const { user, signOut } = useAuth();
  const errorText = useApiErrorText();
  const token = params.get("token") || "";
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await confirmEmailChange(token);
      if (user && user.uid === res.user_id) await signOut(); // only this account's sessions ended
      setDone(res.email);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthSplit pose={done ? "celebrating" : "thinking"}>
        <div>
          <AuthTitle title={t(done ? "auth.confirmEmail.successTitle" : "auth.confirmEmail.title")} subtitle={done ? undefined : t("auth.confirmEmail.subtitle")} />
          {!token && !done && (
            <div className="mb-5 flex items-center gap-2 rounded-xl border border-warning-200 bg-warning-50 p-3 text-sm font-medium text-warning-900">
              <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0 text-warning-700" />
              <span>{t("auth.confirmEmail.missing")}</span>
            </div>
          )}
          {error && (
            <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
              <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-danger-700" />
              <span>{error}</span>
            </div>
          )}
          {done ? (
            <div className="space-y-4">
              <div className="flex items-start gap-3 rounded-2xl border border-success-200 bg-success-50 p-4 text-sm text-success-800">
                <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-success-700" />
                <p className="break-words leading-relaxed">{t("auth.confirmEmail.successBody", { email: done })}</p>
              </div>
              <button type="button" onClick={() => router.push(`/${lang}/login`)} className={buttonClasses({ size: "lg", fullWidth: true })}>
                <span>{t("auth.signInButton")}</span>
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <Button size="lg" fullWidth loading={busy} disabled={busy || !token} onClick={() => void confirm()}>
                {t("auth.confirmEmail.button")}
              </Button>
              <div className="text-center">
                <Link href={`/${lang}/login`} className="inline-flex min-h-11 items-center text-sm font-semibold text-slate-600 transition hover:text-brand-700">
                  ← {t("auth.backToLogin")}
                </Link>
              </div>
            </div>
          )}
        </div>
    </AuthSplit>
  );
}

function LoadingFallback() {
  const { t } = useTranslation();
  return <div className="flex min-h-screen items-center justify-center">{t("common.loading")}</div>;
}

export default function ConfirmEmailPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <ConfirmEmailForm />
    </Suspense>
  );
}
