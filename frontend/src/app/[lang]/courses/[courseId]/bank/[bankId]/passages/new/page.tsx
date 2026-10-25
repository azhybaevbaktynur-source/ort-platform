"use client";

import React from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { PassageEditor } from "@/components/lms/content/PassageEditor";
import { PageHeader } from "@/components/ui";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";

export default function NewPassagePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { bankId } = useParams<{ bankId: string }>();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}/bank`;
  const crumbs = useTabCrumbs("bank", [{ label: t("bank.passages.back"), href: `${base}/${bankId}/passages` }, { label: t("bank.passages.new") }], course.id);
  if (course.status === "concluded") return <p className="text-sm text-slate-600">{t("bank.concluded")}</p>;
  return (
    <div className="space-y-4">
      <PageHeader breadcrumbs={crumbs} title={t("bank.passages.new")} className="mb-2" />
      <PassageEditor courseId={course.id} bankId={bankId} courseLanguages={course.languages} defaultLanguage={course.default_language}
        onSaved={(p) => router.push(`${base}/p/${p.id}`)} onConflict={() => {}} />
    </div>
  );
}
