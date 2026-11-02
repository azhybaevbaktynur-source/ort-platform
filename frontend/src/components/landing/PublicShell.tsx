"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Mascot, cn, focusRing, type MascotPose } from "@/components/ui";
import { LANDING_INNER } from "./roles";
import { PublicHeader } from "./PublicHeader";
import { PublicFooter } from "./PublicFooter";

/** Header, main and footer of every public page. */
export function PublicShell({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-800">
      <a href="#main" className={cn("sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-40 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-700 focus:shadow", focusRing)}>
        {t("shell.skipToContent")}
      </a>
      <PublicHeader />
      <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">{children}</main>
      <PublicFooter />
    </div>
  );
}

/** The heading band of the short public pages (about, help, contacts, for teachers). */
export function PublicPageHeading({ title, intro, pose }: { title: string; intro?: string; pose: MascotPose }) {
  return (
    <section className="bg-brand-50">
      {/* Phone: the title beside the mascot, the intro under both at full width. From `sm` up: the mascot beside both. */}
      <div className={cn(LANDING_INNER, "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 py-8 sm:py-12")}>
        <h1 className={cn("col-start-1 row-start-1 max-w-2xl text-3xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-4xl lg:text-5xl", intro && "sm:self-end")}>{title}</h1>
        {intro && <p className="col-span-2 col-start-1 row-start-2 mt-3 max-w-2xl text-base leading-7 text-slate-600 sm:col-span-1 sm:mt-4 sm:self-start sm:text-lg">{intro}</p>}
        <div className={cn("col-start-2 row-start-1", intro && "sm:row-span-2")}>
          <Mascot pose={pose} size={400} className="h-20 w-auto sm:h-40 lg:h-52" />
        </div>
      </div>
    </section>
  );
}
