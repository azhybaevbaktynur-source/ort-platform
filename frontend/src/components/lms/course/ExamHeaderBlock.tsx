"use client";

// Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3.1, D9): the exam-course part of the full course header, the only
// template-specific part of the course pattern: the countdown tiles (exam date from the course settings; «Сегодня» on
// the day; nothing without a date or once the day has passed) and the goal line (latest released scaled score, the
// student's target, edited in place with the same `PUT /my/goal`). Data: the exam-prep page (SWR cache, shared with
// Обзор's next step and result blocks). The countdown is not `aria-live`.
import React, { useState } from "react";
import { Pencil } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { wholeNumber, type ExamGoalOut, type ExamPrepOut } from "@/lib/lms/examPrep";
import { putExamPrep } from "@/lib/lms/pageData";
import { Countdown, IconButton, Skeleton, cn, examDayStart } from "@/components/ui";
import { GoalEditor } from "@/components/lms/examPrep/GoalStrip";

const DAY = 86_400_000;

/** The countdown (right of the title on desktop, under it on phones); null without a date or after the exam day. */
export function ExamCountdown({ prep, className }: { prep: ExamPrepOut | null; className?: string }) {
  const { t } = useTranslation();
  if (!prep) return <Skeleton aria-hidden="true" className={cn("h-[4.25rem] w-full rounded-control sm:w-[17rem]", className)} />;
  if (!prep.exam_date) return null;
  const target = examDayStart(prep.exam_date);
  if (Date.now() - target.getTime() >= DAY) return null;
  return (
    <div className={cn("w-full sm:w-[17rem] sm:shrink-0", className)}>
      <p aria-hidden="true" className="mb-1.5 text-xs font-semibold uppercase leading-4 tracking-wide text-slate-600">{t("course.header.examIn")}</p>
      <Countdown target={target} label={t("course.header.examIn")} />
    </div>
  );
}

/** «Последний балл 132 из 245 · Цель 200 ✎» with the goal editor in place (`#goal`: the getting-started link). */
export function ExamGoalLine({ prep, courseId }: { prep: ExamPrepOut | null; courseId: string }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  if (!prep) return <Skeleton aria-hidden="true" className="h-5 w-56" />;
  const latest = wholeNumber(prep.latest?.value);
  const max = wholeNumber(prep.goal.scale_max);
  const target = prep.goal.target_score;
  const setGoal = (g: ExamGoalOut) => { putExamPrep(courseId, { ...prep, goal: g }); setEditing(false); };
  const value = "font-semibold tabular-nums text-slate-900";
  return (
    <div id="goal" className="min-w-0 scroll-mt-24" onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }}>
      <p className="flex flex-wrap items-center gap-x-2 text-sm leading-5 text-slate-700">
        <span className="whitespace-nowrap">
          {t("course.header.lastScore")}: <span className={value}>{latest ?? "—"}</span>
          {latest !== null && max !== null && <span className="text-slate-600"> {t("examPrep.goal.outOf", { max })}</span>}
        </span>
        <span aria-hidden="true" className="text-slate-400">·</span>
        <span className="inline-flex items-center gap-1 whitespace-nowrap">
          {t("course.header.target")}: <span className={value}>{target ?? "—"}</span>
          <IconButton icon={<Pencil />} aria-label={target === null ? t("examPrep.goal.setTarget") : t("examPrep.goal.edit")}
            onClick={() => setEditing((v) => !v)} aria-expanded={editing} className="text-brand-700" />
        </span>
      </p>
      {editing && (
        <GoalEditor courseId={courseId} goal={prep.goal} className="mt-2 rounded-card shadow-none sm:col-span-1"
          onDone={setGoal} onCancel={() => setEditing(false)} />
      )}
    </div>
  );
}
