"use client";

// Exam prep S2: the one suggested step, with the page's only primary button and its reason in one line: resume an open
// attempt, else the first test not taken yet, else practice of the weakest section, else the test taken longest ago.
import React from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { ExamNextOut } from "@/lib/lms/examPrep";
import { LinkButton, cn } from "@/components/ui";

/** `accent` (Student UI colour §1.1, the student home only): the button in the violet accent, the screen's one main call. */
export function NextCard({ next, courseId, accent = false, className }: { next: ExamNextOut | null; courseId: string; accent?: boolean; className?: string }) {
  const { lang, t } = useTranslation();
  const base = `/${lang}/courses/${courseId}`;
  if (!next) {
    return (
      <section aria-labelledby="exam-next" className={cn("rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5", className)}>
        <h2 id="exam-next" className="text-base font-semibold leading-6 text-slate-900">{t("examPrep.next.title")}</h2>
        <p className="mt-2 flex items-start gap-2 text-base leading-6 text-slate-700">
          <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-success-700" />
          {t("examPrep.next.none")}
        </p>
      </section>
    );
  }
  const section = next.section ? t(`sections.${next.section}`) : "";
  const title = next.kind === "practice"
    ? t("examPrep.next.practiceTitle", { section })
    : next.kind === "unlock" ? t("examPrep.next.unlockTitle") // S3: only paid tests remain
      : pickLocalized(next.title, lang) || t("assessments.untitled");
  const href = next.kind === "resume" && next.attempt_id ? `${base}/attempts/${next.attempt_id}`
    : next.kind === "practice" ? `${base}/practice`
      : next.kind === "unlock" ? `/${lang}/unlock`
        : `${base}/assessments/${next.assessment_id}`;
  return (
    <section aria-labelledby="exam-next"
      className={cn("flex flex-col gap-4 rounded-2xl border border-brand-200 bg-brand-50 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-5", className)}>
      <div className="min-w-0">
        <h2 id="exam-next" className="text-sm font-semibold uppercase leading-5 tracking-wide text-brand-800">{t("examPrep.next.title")}</h2>
        <p className="mt-1 break-words text-xl font-bold leading-7 text-slate-900">{title}</p>
        <p className="mt-1 text-base leading-6 text-slate-700 sm:text-sm sm:leading-5">{t(`examPrep.next.reason.${next.kind}`, { section })}</p>
      </div>
      <LinkButton href={href} size="lg" rightIcon={<ArrowRight aria-hidden="true" className="h-5 w-5" />}
        className={cn("w-full shrink-0 sm:w-auto", accent && next.kind !== "unlock" && "bg-accent-600 hover:bg-accent-700 active:bg-accent-800 focus-visible:ring-accent-600")}>
        {t(`examPrep.next.action.${next.kind}`)}
      </LinkButton>
    </section>
  );
}
