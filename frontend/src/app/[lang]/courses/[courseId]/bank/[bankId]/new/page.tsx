"use client";

import React from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { QUESTION_TYPES, type QuestionType } from "@/lib/lms/contentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { QuestionEditor } from "@/components/lms/content/QuestionEditor";

export default function NewQuestionPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { bankId } = useParams<{ bankId: string }>();
  const search = useSearchParams();
  const { course } = useCourse();
  const raw = search.get("type") as QuestionType | null;
  const type: QuestionType = raw && QUESTION_TYPES.includes(raw) ? raw : "single_choice";
  const base = `/${lang}/courses/${course.id}/bank`;
  if (course.status === "concluded") return <p className="text-sm text-slate-600">{t("bank.concluded")}</p>;
  return (
    <div className="space-y-4">
      <Link href={`${base}/${bankId}`} className="text-sm font-medium text-brand-700 hover:underline">{t("bank.backToQuestions")}</Link>
      <h2 className="text-xl font-bold text-slate-900">{t("bank.questions.newTitle")}</h2>
      <QuestionEditor courseId={course.id} bankId={bankId} courseLanguages={course.languages} defaultLanguage={course.default_language}
        createType={type} onSaved={(q) => router.push(`${base}/q/${q.id}`)} onConflict={() => {}} />
    </div>
  );
}
