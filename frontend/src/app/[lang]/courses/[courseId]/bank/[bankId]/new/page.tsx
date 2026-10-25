"use client";

import React from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { QUESTION_TYPES, type QuestionType } from "@/lib/lms/contentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { QuestionEditor } from "@/components/lms/content/QuestionEditor";
import { PageHeader } from "@/components/ui";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";

export default function NewQuestionPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { bankId } = useParams<{ bankId: string }>();
  const search = useSearchParams();
  const { course } = useCourse();
  const raw = search.get("type") as QuestionType | null;
  const type: QuestionType = raw && QUESTION_TYPES.includes(raw) ? raw : "single_choice";
  const base = `/${lang}/courses/${course.id}/bank`;
  const crumbs = useTabCrumbs("bank", [{ label: t("bank.backToQuestions"), href: `${base}/${bankId}` }, { label: t("bank.questions.newTitle") }], course.id);
  if (course.status === "concluded") return <p className="text-sm text-slate-600">{t("bank.concluded")}</p>;
  return (
    <div className="space-y-4">
      <PageHeader breadcrumbs={crumbs} title={t("bank.questions.newTitle")} description={t(`bank.types.${type}.name`)} className="mb-2" />
      <QuestionEditor courseId={course.id} bankId={bankId} courseLanguages={course.languages} defaultLanguage={course.default_language}
        createType={type} onSaved={(q) => router.push(`${base}/q/${q.id}`)} onConflict={() => {}} />
    </div>
  );
}
