"use client";

import React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { PassageEditor } from "@/components/lms/content/PassageEditor";

export default function NewPassagePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { bankId } = useParams<{ bankId: string }>();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}/bank`;
  if (course.status === "concluded") return <p className="text-sm text-slate-600">{t("bank.concluded")}</p>;
  return (
    <div className="space-y-4">
      <Link href={`${base}/${bankId}/passages`} className="text-sm font-medium text-brand-700 hover:underline">{t("bank.passages.back")}</Link>
      <h2 className="text-xl font-bold text-slate-900">{t("bank.passages.new")}</h2>
      <PassageEditor courseId={course.id} bankId={bankId} courseLanguages={course.languages} defaultLanguage={course.default_language}
        onSaved={(p) => router.push(`${base}/p/${p.id}`)} onConflict={() => {}} />
    </div>
  );
}
