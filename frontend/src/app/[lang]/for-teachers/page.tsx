"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { LinkButton, cn, focusRing } from "@/components/ui";
import { PublicPageHeading, PublicShell } from "@/components/landing/PublicShell";
import { LANDING_INNER } from "@/components/landing/roles";
import { loginBackHref } from "@/components/teacherApply/paths";

const STEPS = ["step1", "step2", "step3"] as const;

/** How teachers join (public): the application page, the platform admin approves; or an organization invites. */
export default function ForTeachersPage() {
  const { lang, t } = useTranslation();
  const { user } = useAuth();
  const applyHref = `/${lang}/for-teachers/apply`;
  return (
    <PublicShell>
      <PublicPageHeading title={t("landing.forTeachers.title")} intro={t("landing.forTeachers.intro")} pose="working" />
      <div className={cn(LANDING_INNER, "grid gap-10 py-10 sm:py-14 lg:grid-cols-12 lg:gap-14")}>
        <section aria-labelledby="teachers-apply" className="lg:col-span-7">
          <h2 id="teachers-apply" className="text-xl font-bold leading-7 text-slate-900 sm:text-2xl">{t("landing.forTeachers.applyTitle")}</h2>
          <ol className="mt-5 space-y-6">
            {STEPS.map((step, i) => (
              <li key={step} className="flex gap-4">
                <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-bold text-brand-800">{i + 1}</span>
                <div className="min-w-0">
                  <h3 className="text-base font-semibold leading-6 text-slate-900">{t(`landing.forTeachers.${step}Title`)}</h3>
                  <p className="mt-1 text-base leading-7 text-slate-600">
                    {t(`landing.forTeachers.${step}Text`)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-5">
            <LinkButton size="lg" href={applyHref} className="w-full sm:w-auto">{t("landing.forTeachers.apply")}</LinkButton>
            {!user && (
              <Link href={loginBackHref(lang)} className={cn("inline-flex min-h-11 items-center justify-center rounded-md text-base font-semibold text-brand-700 underline-offset-4 hover:underline", focusRing)}>
                {t("landing.forTeachers.haveAccount")}
              </Link>
            )}
          </div>
        </section>
        <section aria-labelledby="teachers-invite" className="self-start rounded-2xl border border-slate-200 bg-slate-50 p-5 sm:p-6 lg:col-span-5">
          <h2 id="teachers-invite" className="text-xl font-bold leading-7 text-slate-900">{t("landing.forTeachers.inviteTitle")}</h2>
          <p className="mt-2 text-base leading-7 text-slate-600">{t("landing.forTeachers.inviteText")}</p>
        </section>
      </div>
    </PublicShell>
  );
}
