"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import type { BankOut } from "@/lib/lms/contentTypes";

/** Bank title with a questions/passages tab switch. */
export function BankHeader({ courseId, bank, active }: { courseId: string; bank: BankOut | null; active: "questions" | "passages" }) {
  const { lang, t } = useTranslation();
  const base = `/${lang}/courses/${courseId}/bank`;
  const tab = (on: boolean) =>
    `rounded-lg px-3 py-1.5 text-sm font-semibold ${on ? "bg-brand-100 text-brand-800" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="mb-4 space-y-2">
      <Link href={base} className="text-sm font-medium text-brand-700 hover:underline">{t("bank.backToBanks")}</Link>
      <h2 className="text-xl font-bold text-slate-900">{bank?.title || "..."}</h2>
      {bank && (
        <div className="flex gap-1">
          <Link href={`${base}/${bank.id}`} aria-current={active === "questions" ? "page" : undefined} className={tab(active === "questions")}>
            {t("bank.questions.tab", { n: bank.question_count })}
          </Link>
          <Link href={`${base}/${bank.id}/passages`} aria-current={active === "passages" ? "page" : undefined} className={tab(active === "passages")}>
            {t("bank.passages.tab", { n: bank.passage_count })}
          </Link>
        </div>
      )}
    </div>
  );
}
