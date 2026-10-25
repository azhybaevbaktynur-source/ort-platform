"use client";

// Phase 7a S5: one assignment of a student (PHASE_7A_DESIGN 5): title, kind icon + text, due date, status badge and
// one clear action: "Start" (quiz -> the existing lobby), "Continue", "Hand in" or "Open".
import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import type { AssignmentStudentOut } from "@/lib/lms/assignmentTypes";
import { LinkButton, cn, focusRing } from "@/components/ui";
import { DueText } from "@/components/lms/home/StudentAssessmentCard";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { AssignmentStatusBadge, KindIcon, fmtPts } from "./assignmentUi";
import { assignmentHref, type StudentAssignmentView } from "./studentAssignment";

export function StudentAssignmentCard({ a, v, base, primary, title, ort = false, as = "li" }: {
  a: AssignmentStudentOut;
  v: StudentAssignmentView;
  /** /{lang}/courses/{courseId} */
  base: string;
  primary: boolean;
  title: string;
  /** quiz of an ORT course: say "exam" */
  ort?: boolean;
  as?: "li" | "div";
}) {
  const { lang, t } = useTranslation();
  const Tag = as;
  const href = assignmentHref(base, a);
  const variant = primary ? "primary" : "secondary";
  let action: React.ReactNode = null;
  if (v.action === "continue") {
    // the lobby resumes the open attempt
    action = <LinkButton variant={variant} href={href}>{t("assignments.student.continue")}</LinkButton>;
  } else if (v.action === "start") {
    action = <LinkButton variant={variant} href={href}>{t("assignments.student.start")}</LinkButton>;
  } else if (v.action === "hand_in") {
    action = <LinkButton variant={variant} href={href}>{t("assignments.student.handIn")}</LinkButton>;
  } else {
    action = <LinkButton variant="secondary" href={href}>{a.status === "graded" ? t("assignments.student.seeGrade") : t("assignments.student.open")}</LinkButton>;
  }
  const kindText = a.kind === "quiz" && ort ? t("assignments.kinds.ortExam") : t(`assignments.kinds.${a.kind}`);
  const points = fmtPts(a.points_possible);
  return (
    <Tag className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <Link href={href} className={cn("min-w-0 flex-1 basis-48 break-words rounded text-base font-semibold leading-6 text-slate-900 hover:text-brand-700", focusRing)}>
          {title}
        </Link>
        {a.status && <AssignmentStatusBadge status={a.status} />}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm leading-6 text-slate-600">
        <li className="inline-flex items-center gap-1"><KindIcon kind={a.kind} />{kindText}</li>
        {v.opensLater && a.available_from && <li>{t("home.opens", { date: fmtShortDateTime(a.available_from, lang) })}</li>}
        {a.due_at && !v.windowClosed && <li><DueText value={a.due_at} lang={lang} /></li>}
        {!a.due_at && a.available_until && !v.windowClosed && <li>{t("home.until", { date: fmtShortDateTime(a.available_until, lang) })}</li>}
        {v.windowClosed && a.available_until && <li>{t("home.closedOn", { date: fmtShortDateTime(a.available_until, lang) })}</li>}
        {points && a.kind !== "quiz" && <li>{t("assignments.student.points", { n: points })}</li>}
        {a.kind === "quiz" && a.attempts_left !== undefined && (
          <li className={v.noAttemptsLeft ? "font-semibold text-slate-800" : undefined}>
            {a.attempts_left === null ? t("home.attemptsUnlimited") : v.noAttemptsLeft ? t("home.noAttemptsLeft") : t("home.attemptsLeft", { n: a.attempts_left })}
          </li>
        )}
      </ul>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap [&>*]:w-full sm:[&>*]:w-auto">{action}</div>
    </Tag>
  );
}
