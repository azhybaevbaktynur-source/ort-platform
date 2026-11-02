"use client";

import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth, type RegisterResult } from "@/lib/auth-context";
import { useBackendWarmup } from "@/lib/useBackendWarmup";
import { LoadingState, Mascot, cn } from "@/components/ui";
import { PublicShell } from "@/components/landing/PublicShell";
import { LANDING_INNER } from "@/components/landing/roles";
import { VerifyEmailStep } from "@/components/auth/VerifyEmailStep";
import { AccountStep, EMPTY_ACCOUNT, type AccountForm } from "@/components/teacherApply/AccountStep";
import { ApplicationStep } from "@/components/teacherApply/ApplicationStep";
import { ApplySteps, type ApplyStepKey } from "@/components/teacherApply/ApplySteps";

/**
 * "I'm a teacher" (docs/phases/ACCOUNTS.md D). Signed out: account, emailed code, application, on one page; the form
 * stays in this component's state, never in the URL or browser storage. Signed in: straight to the application.
 * Someone who leaves after the code has a normal account and continues here after logging in.
 */
export default function TeacherApplyPage() {
  const { t } = useTranslation();
  const { user, loading } = useAuth();
  const [account, setAccount] = useState<AccountForm>(EMPTY_ACCOUNT);
  const [registered, setRegistered] = useState<RegisterResult | null>(null);
  const [walking, setWalking] = useState(false); // came through the steps on this page: the stepper stays
  useBackendWarmup();

  const step: ApplyStepKey = user ? "application" : registered ? "email" : "account";
  const showSteps = !loading && (!user || walking);

  return (
    <PublicShell>
      <div className={cn(LANDING_INNER, "py-4 sm:py-10 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,36rem)] lg:gap-14 lg:py-14")}>
        <div className="lg:pt-2">
          <div className="flex items-center justify-between gap-3 lg:block">
            <h1 className="min-w-0 text-2xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-3xl lg:text-4xl">{t("teacherApply.title")}</h1>
            <Mascot pose="working" size={200} eager className="h-14 w-auto sm:h-20 lg:mt-6 lg:h-44" />
          </div>
          <p className="mt-1 hidden text-base leading-7 text-slate-600 sm:block lg:mt-4">{t(user ? "teacherApply.introSignedIn" : "teacherApply.intro")}</p>
          {showSteps && <ApplySteps current={step} className="mt-2 sm:mt-4 lg:mt-8" />}
        </div>
        <div className="mt-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:mt-6 sm:p-6 lg:mt-0 lg:self-start">
          {loading ? <LoadingState label={t("lms.common.loading")} />
            : user ? <ApplicationStep onSubmitted={() => setWalking(false)} />
            : registered ? (
              <VerifyEmailStep
                email={registered.email}
                password={account.password}
                resendAfterSeconds={registered.resendAfterSeconds}
                codeTtlMinutes={registered.codeTtlMinutes}
                reason="registered"
                headingLevel={2}
                onVerified={() => { setWalking(true); setAccount(EMPTY_ACCOUNT); setRegistered(null); }}
                onChangeEmail={() => setRegistered(null)}
              />
            ) : <AccountStep form={account} onChange={setAccount} onRegistered={setRegistered} />}
        </div>
      </div>
    </PublicShell>
  );
}
