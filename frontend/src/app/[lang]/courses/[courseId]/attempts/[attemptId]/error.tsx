"use client";

import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";

/** Render failures inside the exam player: answers are saved on the server and in this browser, so say so and offer a reload. */
export default function AttemptError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { lang, t } = useTranslation();
  const params = useParams<{ courseId: string }>();
  return (
    <div role="alert" className="mx-auto mt-10 max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
      <h1 className="text-lg font-bold text-slate-900">{t("player.crash.title")}</h1>
      <p className="mt-2 text-sm text-slate-600">{t("player.crash.body")}</p>
      <div className="mt-5 flex flex-wrap justify-center gap-3 text-sm font-semibold">
        <button type="button" onClick={() => reset()} className="rounded-xl bg-brand-600 px-4 py-2 text-white hover:bg-brand-700">
          {t("player.crash.reload")}
        </button>
        <Link href={`/${lang}/courses/${params.courseId}`} className="rounded-xl border border-slate-200 px-4 py-2 text-slate-700 hover:bg-slate-50">
          {t("player.backToCourse")}
        </Link>
      </div>
    </div>
  );
}
