"use client";

// Exam prep S2: days to the exam (hidden without a date or once it has passed), the student's target (set and changed
// inline, inside the exam's scale) and the latest released scaled score. Phones: two tiles per row, the latest score
// on its own row; the target editor takes a full row while open.
import React, { useState } from "react";
import { Trophy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { daysUntil, deleteExamGoal, putExamGoal, wholeNumber, type ExamGoalOut, type ExamPrepOut } from "@/lib/lms/examPrep";
import { Badge, Button, Input, cn } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";

const tile = "flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm";
const label = "text-sm font-medium leading-5 text-slate-600";
const big = "text-4xl font-bold leading-10 tabular-nums text-slate-900";

export function fmtExamDate(iso: string, lang: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, (m || 1) - 1, d || 1));
  try {
    return date.toLocaleDateString(lang === "en" ? "en-GB" : lang, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  } catch {
    return iso;
  }
}

function GoalEditor({ courseId, goal, onDone, onCancel }: {
  courseId: string; goal: ExamGoalOut; onDone: (g: ExamGoalOut) => void; onCancel: () => void;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const min = wholeNumber(goal.scale_min) ?? 0;
  const max = wholeNumber(goal.scale_max) ?? 0;
  const [text, setText] = useState(goal.target_score === null ? "" : String(goal.target_score));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = Number(text);
  const valid = text.trim() !== "" && Number.isInteger(n) && n >= min && n <= max;

  const save = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!valid) { setError(t("examPrep.goal.invalid", { min, max })); return; }
    setBusy(true);
    setError(null);
    try {
      onDone(await putExamGoal(courseId, n));
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteExamGoal(courseId);
      onDone({ ...goal, target_score: null });
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  };
  return (
    <form onSubmit={save} noValidate className={cn(tile, "col-span-2 gap-3 sm:col-span-3")}>
      <Input label={t("examPrep.goal.inputLabel", { min, max })} containerClassName="max-w-xs" inputMode="numeric"
        autoFocus value={text} error={error ?? undefined}
        onChange={(e) => setText(e.target.value.replace(/[^0-9]/g, "").slice(0, 4))} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" variant="secondary" loading={busy}>{t("examPrep.goal.save")}</Button>
        <Button variant="link" onClick={onCancel} disabled={busy}>{t("examPrep.goal.cancel")}</Button>
        {goal.target_score !== null && (
          <Button variant="link" className="text-danger-700" onClick={() => void remove()} disabled={busy}>{t("examPrep.goal.remove")}</Button>
        )}
      </div>
    </form>
  );
}

export function GoalStrip({ data, courseId, onGoal, className }: {
  data: ExamPrepOut; courseId: string; onGoal: (g: ExamGoalOut) => void; className?: string;
}) {
  const { lang, t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const days = data.exam_date ? daysUntil(data.exam_date) : null;
  const showDays = days !== null && days >= 0;
  const target = data.goal.target_score;
  const latest = wholeNumber(data.latest?.value);
  const max = wholeNumber(data.goal.scale_max);
  const gap = target !== null && latest !== null ? target - latest : null;

  return (
    <section aria-labelledby="exam-goal" className={cn("grid grid-cols-2 gap-3", showDays ? "sm:grid-cols-3" : "sm:grid-cols-2", className)}>
      <h2 id="exam-goal" className="sr-only">{t("examPrep.goal.targetLabel")}</h2>
      {showDays && data.exam_date && (
        <div className={tile}>
          <p className={label}>{t("examPrep.goal.daysLabel")}</p>
          {days === 0
            ? <p className={cn(big, "mt-1 text-3xl")}>{t("examPrep.goal.today")}</p>
            : (
              <p className="mt-1 flex flex-wrap items-baseline gap-x-2">
                <span className={big}>{days}</span>
                <span className="text-base font-medium text-slate-700">{t("examPrep.goal.daysUnit", { count: days })}</span>
              </p>
            )}
          <p className="mt-auto pt-1 text-sm leading-5 text-slate-600">{t("examPrep.goal.examOn", { date: fmtExamDate(data.exam_date, lang) })}</p>
        </div>
      )}
      <div className={tile}>
        <p className={label}>{t("examPrep.goal.targetLabel")}</p>
        {target !== null ? (
          <>
            <p className={cn(big, "mt-1")}>{target}</p>
            <div className="mt-auto pt-1">
              <Button variant="link" onClick={() => setEditing(true)} aria-expanded={editing}>{t("examPrep.goal.edit")}</Button>
            </div>
          </>
        ) : (
          <>
            <p className="mt-1 text-sm leading-5 text-slate-600">{t("examPrep.goal.noTarget")}</p>
            <div className="mt-auto pt-2">
              <Button variant="secondary" size="sm" onClick={() => setEditing(true)} aria-expanded={editing}>{t("examPrep.goal.setTarget")}</Button>
            </div>
          </>
        )}
      </div>
      <div className={cn(tile, showDays ? "col-span-2 sm:col-span-1" : "")}>
        <p className={label}>{t("examPrep.goal.latestLabel")}</p>
        {latest !== null ? (
          <>
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2">
              <span className={big}>{latest}</span>
              {max !== null && <span className="text-base font-medium text-slate-700">{t("examPrep.goal.outOf", { max })}</span>}
            </p>
            {gap !== null && (
              <div className="mt-auto pt-1">
                {gap <= 0
                  ? <Badge icon={<Trophy aria-hidden="true" />} className="border-gold-300 bg-gold-100 text-gold-900">{t("examPrep.goal.reached")}</Badge>
                  : <p className="text-sm leading-5 text-slate-600">{t("examPrep.goal.toTarget", { count: gap })}</p>}
              </div>
            )}
          </>
        ) : (
          <p className="mt-1 text-sm leading-5 text-slate-600">{t("examPrep.goal.noScore")}</p>
        )}
      </div>
      {editing && (
        <GoalEditor courseId={courseId} goal={data.goal}
          onDone={(g) => { onGoal(g); setEditing(false); }} onCancel={() => setEditing(false)} />
      )}
    </section>
  );
}
