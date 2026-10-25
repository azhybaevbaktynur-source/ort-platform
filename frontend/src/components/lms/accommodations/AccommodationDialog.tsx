"use client";

// Phase 7a S5: accommodations of one student for the whole course (A5; teacher only): extra time in percent and/or
// minutes, extra attempts and a staff-only note. In an ORT course the time fields carry the pending note (Q1).
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  EXTRA_ATTEMPTS_MAX, EXTRA_TIME_PERCENT_MAX, EXTRA_TIME_S_MAX, NOTE_MAX, clearAccommodation, setAccommodation,
  type AccommodationOut, type AccommodationRowOut,
} from "@/lib/lms/accommodations";
import { Button, Dialog, Input, Textarea } from "@/components/ui";
import { AssignmentError } from "@/components/lms/assignments/assignmentUi";
import { isBad, parseWhole } from "./fields";

export function AccommodationDialog({ open, courseId, row, ortCourse, onClose, onSaved }: {
  open: boolean;
  courseId: string;
  row: AccommodationRowOut | null;
  ortCourse: boolean;
  onClose: () => void;
  onSaved: (enrollmentId: string, a: AccommodationOut | null) => void;
}) {
  const { t } = useTranslation();
  const [percent, setPercent] = useState("");
  const [minutes, setMinutes] = useState("");
  const [attempts, setAttempts] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "clear">("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!open) return;
    const a = row?.accommodation;
    setPercent(a?.extra_time_percent ? String(a.extra_time_percent) : "");
    setMinutes(a?.extra_time_s ? String(Math.round(a.extra_time_s / 60)) : "");
    setAttempts(a?.extra_attempts ? String(a.extra_attempts) : "");
    setNote(a?.note ?? "");
    setError(null);
  }, [open, row]);

  const p = parseWhole(percent, EXTRA_TIME_PERCENT_MAX);
  const m = parseWhole(minutes, Math.floor(EXTRA_TIME_S_MAX / 60));
  const a = parseWhole(attempts, EXTRA_ATTEMPTS_MAX);
  const valid = !isBad(p) && !isBad(m) && !isBad(a) && note.length <= NOTE_MAX;

  const save = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!row || !valid) return;
    setBusy("save");
    setError(null);
    try {
      const out = await setAccommodation(courseId, row.enrollment_id, {
        extra_time_percent: p ?? 0, extra_time_s: (m ?? 0) * 60, extra_attempts: a ?? 0, note: note.trim() || null,
      });
      onSaved(row.enrollment_id, out ?? { extra_time_percent: p ?? 0, extra_time_s: (m ?? 0) * 60, extra_attempts: a ?? 0, note: note.trim() || null });
    } catch (err) {
      setError(err);
    } finally {
      setBusy("");
    }
  };

  const clear = async () => {
    if (!row) return;
    setBusy("clear");
    setError(null);
    try {
      await clearAccommodation(courseId, row.enrollment_id);
      onSaved(row.enrollment_id, null);
    } catch (err) {
      setError(err);
    } finally {
      setBusy("");
    }
  };

  const formId = "accommodation-form";
  return (
    <Dialog open={open} onClose={onClose} busy={!!busy} size="md" title={t("accommodations.dialog.title")}
      description={t("accommodations.dialog.subtitle")}
      footer={(
        <>
          {row?.accommodation && <Button variant="secondary" loading={busy === "clear"} disabled={!!busy} onClick={() => void clear()}>{t("accommodations.dialog.clear")}</Button>}
          <Button variant="secondary" disabled={!!busy} onClick={onClose}>{t("ui.cancel")}</Button>
          <Button type="submit" form={formId} loading={busy === "save"} disabled={!!busy && busy !== "save"}>{t("accommodations.dialog.save")}</Button>
        </>
      )}>
      <form id={formId} className="space-y-4" onSubmit={(e) => void save(e)}>
        <p className="break-words rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-900">{row?.student_name || row?.email || "—"}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label={t("accommodations.fields.extraPercent")} optional inputMode="numeric" value={percent} onChange={(e) => setPercent(e.target.value)}
            hint={t("accommodations.fields.percentHint")} error={isBad(p) ? t("accommodations.fields.percentInvalid", { max: EXTRA_TIME_PERCENT_MAX }) : undefined} />
          <Input label={t("accommodations.fields.extraMinutes")} optional inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)}
            error={isBad(m) ? t("accommodations.fields.minutesInvalid", { max: Math.floor(EXTRA_TIME_S_MAX / 60) }) : undefined} />
        </div>
        {ortCourse && <p className="rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm text-warning-900">{t("accommodations.ortTimePending")}</p>}
        <Input label={t("accommodations.fields.extraAttempts")} optional inputMode="numeric" value={attempts} onChange={(e) => setAttempts(e.target.value)}
          hint={t("accommodations.fields.attemptsHint")} error={isBad(a) ? t("accommodations.fields.attemptsInvalid", { max: EXTRA_ATTEMPTS_MAX }) : undefined}
          containerClassName="sm:max-w-[50%]" />
        <Textarea label={t("accommodations.fields.note")} optional hint={t("accommodations.fields.noteHint")} maxLength={NOTE_MAX} rows={2}
          value={note} onChange={(e) => setNote(e.target.value)} />
        <AssignmentError error={error} />
      </form>
    </Dialog>
  );
}
