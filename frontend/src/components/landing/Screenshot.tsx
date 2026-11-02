"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";

export type LandingShot = "student-dashboard" | "exam-player" | "teacher-course";

/** A real screen of the platform in the current language (frontend/e2e/landing-screens.spec.ts records them, 1200x797). */
export function Screenshot({ name, alt }: { name: LandingShot; alt: string }) {
  const { lang } = useTranslation();
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10 sm:rounded-2xl">
      <img src={`/landing/${name}-${lang}.webp`} alt={alt} width={1200} height={797} loading="lazy" decoding="async" className="block h-auto w-full" />
    </div>
  );
}
