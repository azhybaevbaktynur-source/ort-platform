"use client";

// Phase 7a S5: an exception for one student on one assignment (PHASE_7A_DESIGN 2.5, A5): other dates, extra time,
// extra attempts and a staff-only note. Empty fields fall back to the student's accommodation, then the assignment.
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  EXTRA_ATTEMPTS_MAX, EXTRA_TIME_PERCENT_MAX, EXTRA_TIME_S_MAX, NOTE_MAX, setOverride, type AccommodationRowOut, type OverrideOut,
} from "@/lib/lms/accommodations";
import { fromLocalInput, toLocalInput } from "@/components/lms/assessments/format";
import { Button, Dialog, Input, Select, Textarea } from "@/components/ui";
import { AssignmentError } from "@/components/lms/assignments/assignmentUi";
import { isBad, parseWhole, wholeText } from "./fields";

export function OverrideDialog({
  open, courseId, assignmentId, existing, students, studentsError, isQuiz, ortTimeLocked, onClose, onSaved,
}: {
  open: boolean;
  courseId: string;
  assignmentId: string;
  /** edit this exception (student fixed); null = new */
  existing: OverrideOut | null;
  students: AccommodationRowOut[] | null;
  studentsError?: unknown;
  /** extra time and attempts apply to quizzes only */
  isQuiz: boolean;
  /** ORT exam: extra time is stored but not applied yet (owner question Q1) */
  ortTimeLocked: boolean;
  onClose: () => void;
  onSaved: (o: OverrideOut) => void;
}) {
  const { t } = useTranslation();
  const [student, setStudent] = useState("");
  const [due, setDue] = useState("");
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const [percent, setPercent] = useState("");
  const [minutes, setMinutes] = useState("");
  const [attempts, setAttempts] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (!open) return;
    const o = existing;
    setStudent(o?.enrollment_id ?? "");
    setDue(toLocalInput(o?.due_at)); setFrom(toLocalInput(o?.available_from)); setUntil(toLocalInput(o?.available_until));
    setPercent(wholeText(o?.extra_time_percent));
    setMinutes(o?.extra_time_s === null || o?.extra_time_s === undefined ? "" : String(Math.round(o.extra_time_s / 60)));
    setAttempts(wholeText(o?.extra_attempts)); setNote(o?.note ?? "");
    setError(null); setTouched(false);
  }, [open, existing]);

  const p = parseWhole(percent, EXTRA_TIME_PERCENT_MAX);
  const m = parseWhole(minutes, Math.floor(EXTRA_TIME_S_MAX / 60));
  const a = parseWhole(attempts, EXTRA_ATTEMPTS_MAX);
  const fromIso = fromLocalInput(from);
  const untilIso = fromLocalInput(until);
  const windowBad = !!fromIso && !!untilIso && Date.parse(fromIso) >= Date.parse(untilIso);
  const valid = !!student && !isBad(p) && !isBad(m) && !isBad(a) && !windowBad && note.length <= NOTE_MAX;

  const options = useMemo(() => (students ?? []).map((s) => ({ value: s.enrollment_id, label: s.student_name || s.email || "—" })), [students]);

  const save = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setTouched(true);
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      const out = await setOverride(courseId, assignmentId, student, {
        due_at: fromLocalInput(due), available_from: fromIso, available_until: untilIso,
        extra_time_percent: isQuiz ? p : null, extra_time_s: isQuiz && m !== null ? m * 60 : null,
        extra_attempts: isQuiz ? a : null, note: note.trim() || null,
      });
      onSaved(out);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const formId = "override-form";
  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="lg"
      title={existing ? t("accommodations.override.editTitle") : t("accommodations.override.addTitle")}
      description={t("accommodations.override.subtitle")}
      footer={(
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>{t("ui.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy}>{t("accommodations.override.save")}</Button>
        </>
      )}>
      <form id={formId} className="space-y-4" onSubmit={(e) => void save(e)}>
        {existing ? (
          <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-900">{existing.student_name || "—"}</p>
        ) : (
          <>
            <Select label={t("accommodations.override.student")} value={student} onChange={(e) => setStudent(e.target.value)}
              placeholder={students ? t("accommodations.override.pickStudent") : t("ui.loading")} options={options}
              disabled={!students} error={touched && !student ? t("accommodations.override.studentRequired") : undefined} />
            <AssignmentError error={studentsError} />
          </>
        )}
        <div className="grid gap-4 sm:grid-cols-3">
          <Input type="datetime-local" label={t("assignments.fields.due")} optional value={due} onChange={(e) => setDue(e.target.value)} />
          <Input type="datetime-local" label={t("assignments.fields.availableFrom")} optional value={from} onChange={(e) => setFrom(e.target.value)} />
          <Input type="datetime-local" label={t("assignments.fields.availableUntil")} optional value={until} onChange={(e) => setUntil(e.target.value)}
            error={windowBad ? t("assignments.fields.windowInvalid") : undefined} />
        </div>
        {isQuiz && (
          <div className="space-y-2">
            <div className="grid gap-4 sm:grid-cols-3">
              <Input label={t("accommodations.fields.extraPercent")} optional inputMode="numeric" value={percent} onChange={(e) => setPercent(e.target.value)}
                error={isBad(p) ? t("accommodations.fields.percentInvalid", { max: EXTRA_TIME_PERCENT_MAX }) : undefined} />
              <Input label={t("accommodations.fields.extraMinutes")} optional inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)}
                error={isBad(m) ? t("accommodations.fields.minutesInvalid", { max: Math.floor(EXTRA_TIME_S_MAX / 60) }) : undefined} />
              <Input label={t("accommodations.fields.extraAttempts")} optional inputMode="numeric" value={attempts} onChange={(e) => setAttempts(e.target.value)}
                error={isBad(a) ? t("accommodations.fields.attemptsInvalid", { max: EXTRA_ATTEMPTS_MAX }) : undefined} />
            </div>
            {ortTimeLocked && <p className="rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm text-warning-900">{t("accommodations.ortTimePending")}</p>}
          </div>
        )}
        <Textarea label={t("accommodations.fields.note")} optional hint={t("accommodations.fields.noteHint")} maxLength={NOTE_MAX}
          value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        <p className="text-sm text-slate-600">{t("accommodations.override.fallback")}</p>
        <AssignmentError error={error} />
      </form>
    </Dialog>
  );
}
