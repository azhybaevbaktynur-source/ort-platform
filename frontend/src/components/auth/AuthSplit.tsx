"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Brand } from "@/components/ui/AppHeader";
import { UiLanguageSwitcher } from "@/components/auth/AuthHeader";
import { AuthIllustration } from "@/components/auth/AuthIllustration";
import type { MascotPose } from "@/components/ui/Mascot";

/**
 * The shared layout of the auth screens (AUTH_SOCIAL_DESIGN 8.1). Desktop: form column (max 440 px) left, scene right.
 * Phone: the scene is a 140 px band above the form. Light theme only.
 */
export function AuthSplit({ pose, children }: { pose: MascotPose; children: React.ReactNode }) {
  const { lang } = useTranslation();
  return (
    <div className="min-h-screen bg-white lg:grid lg:grid-cols-2">
      <div className="flex min-w-0 flex-col">
        <div className="flex items-center justify-between gap-3 px-4 py-4 sm:px-8 lg:px-10">
          <Brand href={`/${lang}`} tagline />
          <UiLanguageSwitcher />
        </div>
        <AuthIllustration pose={pose} variant="band" />
        <main className="flex flex-1 flex-col justify-center px-4 py-8 sm:px-8 lg:py-10">
          <div className="mx-auto w-full max-w-[440px]">{children}</div>
        </main>
      </div>
      <AuthIllustration pose={pose} variant="panel" />
    </div>
  );
}

/** Title + subtitle block of a form column. */
export function AuthTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
      {subtitle && <p className="mt-2 text-sm text-slate-600">{subtitle}</p>}
    </div>
  );
}

/** The red alert used by every auth form. */
export function AuthAlert({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
      <span>{children}</span>
    </div>
  );
}
