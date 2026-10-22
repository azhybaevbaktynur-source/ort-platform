"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { ImportPanel } from "@/components/lms/content/import/ImportPanel";
import { useCanEditContent } from "@/components/lms/content/StaffGate";

export default function BankImportPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  return (
    <div className="space-y-4">
      <Link href={`/${lang}/courses/${course.id}/bank`} className="text-sm font-medium text-brand-700 hover:underline">
        {t("bank.backToBanks")}
      </Link>
      <h1 className="text-xl font-bold text-slate-900">{t("bank.import.title")}</h1>
      {canEdit ? (
        <ImportPanel />
      ) : (
        <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{t("bank.concluded")}</p>
      )}
    </div>
  );
}
