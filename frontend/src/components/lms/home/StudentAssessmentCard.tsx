"use client";

import React, { useContext } from "react";
import { CourseContext } from "@/components/lms/CourseContext";
import Link from "next/link";
import { CalendarClock, CheckCircle2, Circle, Clock, Lock, PlayCircle, Star } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { AssessmentStudentSummaryOut } from "@/lib/lms/assessmentTypes";
import { Badge, LinkButton, cn, focusRing, type BadgeTone } from "@/components/ui";
import { fmtPoints } from "@/components/lms/assessments/format";
import { useGradeText } from "@/components/lms/results/GradeBadge";
import type { StudentAssessmentStatus, StudentAssessmentView } from "./assessmentStatus";
import { fmtDuration, fmtShortDateTime, isDueSoon } from "./format";

const STATUS: Record<StudentAssessmentStatus, { tone: BadgeTone; icon: React.ReactNode }> = {
  not_started: { tone: "neutral", icon: <Circle aria-hidden="true" /> },
  in_progress: { tone: "info", icon: <PlayCircle aria-hidden="true" /> },
  submitted: { tone: "info", icon: <CheckCircle2 aria-hidden="true" /> },
  graded: { tone: "success", icon: <Star aria-hidden="true" /> },
  closed: { tone: "neutral", icon: <Lock aria-hidden="true" /> },
};

export function StatusBadge({ status }: { status: StudentAssessmentStatus }) {
  const { t } = useTranslation();
  return <Badge tone={STATUS[status].tone} icon={STATUS[status].icon}>{t(`home.status.${status}`)}</Badge>;
}

/** Due date line: red with a clock when less than 24 hours are left (color is not the only signal: the text says so). */
export function DueText({ value, lang, className }: { value: string | null | undefined; lang: string; className?: string }) {
  const { t } = useTranslation();
  if (!value) return null;
  const soon = isDueSoon(value);
  return (
    <span className={cn("inline-flex items-center gap-1", soon ? "font-semibold text-danger-700" : "text-slate-700", className)}>
      {soon ? <Clock aria-hidden="true" className="h-4 w-4 shrink-0" /> : <CalendarClock aria-hidden="true" className="h-4 w-4 shrink-0" />}
      {t(soon ? "home.dueSoon" : "home.due", { date: fmtShortDateTime(value, lang) })}
    </span>
  );
}

/**
 * One assessment of a student: status badge, due date, duration, attempts left and one clear next action.
 * After the last attempt the card shows "No attempts left" and the way to the result (UX S1).
 */
export function StudentAssessmentCard({ a, v, href, primary, title, as = "li" }: {
  a: AssessmentStudentSummaryOut;
  v: StudentAssessmentView;
  /** course base: /{lang}/courses/{courseId} */
  href: string;
  /** this row carries the page's one primary button */
  primary: boolean;
  title: string;
  as?: "li" | "div";
}) {
  const { lang, t } = useTranslation();
  const gradeText = useGradeText();
  const Tag = as;
  const lobby = `${href}/assessments/${a.id}`;
  const duration = fmtDuration(a.time_limit_s, t);
  const variant = primary ? "primary" : "secondary";

  let result = "";
  if (v.grade && v.grade.state === "graded") result = gradeText(v.grade, v.grade.scheme_type ?? undefined, v.grade.labels);
  if (!result && a.last_result) result = t("home.scoreOf", { score: fmtPoints(a.last_result.raw_score), total: fmtPoints(a.last_result.points_possible) });

  const actions: React.ReactNode[] = [];
  // Phase 6b: an org/platform admin reading the course (no enrollment) gets no start/continue action
  const readOnly = !!useContext(CourseContext)?.course.my_enrollment.read_only;
  if (readOnly) {
    // read-only view: only the lobby link below
  } else if (a.in_progress_attempt_id) {
    actions.push(<LinkButton key="go" variant={variant} href={`${href}/attempts/${a.in_progress_attempt_id}`}>{t("home.action.continue")}</LinkButton>);
  } else if (v.canStart) {
    actions.push(<LinkButton key="go" variant={variant} href={lobby}>{t(a.attempts_used > 0 ? "home.action.again" : "home.action.start")}</LinkButton>);
  }
  if (v.resultAttemptId) {
    actions.push(<LinkButton key="res" variant="secondary" href={`${href}/attempts/${v.resultAttemptId}/result`}>{t("home.action.result")}</LinkButton>);
  } else if (readOnly || (!a.in_progress_attempt_id && !v.canStart)) {
    actions.push(<LinkButton key="open" variant="secondary" href={lobby}>{t(a.attempts_used > 0 ? "home.action.attempts" : "home.action.open")}</LinkButton>);
  }

  const attempts = v.attemptsLeft === null
    ? t("home.attemptsUnlimited")
    : v.noAttemptsLeft ? t("home.noAttemptsLeft") : t("home.attemptsLeft", { n: v.attemptsLeft });

  return (
    <Tag className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <Link href={lobby} className={cn("min-w-0 flex-1 basis-48 break-words rounded text-base font-semibold leading-6 text-slate-900 hover:text-brand-700", focusRing)}>
          {title}
        </Link>
        <StatusBadge status={v.status} />
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm leading-6 text-slate-600">
        {v.opensLater && a.available_from && <li>{t("home.opens", { date: fmtShortDateTime(a.available_from, lang) })}</li>}
        {a.due_at && !v.windowClosed && <li><DueText value={a.due_at} lang={lang} /></li>}
        {!a.due_at && a.available_until && !v.windowClosed && <li>{t("home.until", { date: fmtShortDateTime(a.available_until, lang) })}</li>}
        {v.windowClosed && a.available_until && <li>{t("home.closedOn", { date: fmtShortDateTime(a.available_until, lang) })}</li>}
        {duration && <li>{t("home.duration", { time: duration })}</li>}
        {a.item_count > 0 && <li>{t("home.questions", { n: a.item_count })}</li>}
        <li className={v.noAttemptsLeft ? "font-semibold text-slate-800" : undefined}>{attempts}</li>
      </ul>
      {result && <p className="mt-2 text-base font-semibold text-slate-900">{t("home.resultValue", { value: result })}</p>}
      {v.status === "submitted" && !result && <p className="mt-2 text-sm text-slate-600">{t("home.resultLater")}</p>}
      {actions.length > 0 && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap [&>*]:w-full sm:[&>*]:w-auto">{actions}</div>
      )}
    </Tag>
  );
}
