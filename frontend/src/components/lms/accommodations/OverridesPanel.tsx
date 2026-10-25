"use client";

// Phase 7a S5: exceptions of one assignment (teacher only; PHASE_7A_DESIGN 4.4): a list with Edit / Remove and
// "Add exception". The server recomputes that student's grade when the due date changes (section 3.4).
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { clearOverride, listOverrides, type OverrideOut } from "@/lib/lms/accommodations";
import { Button, Card, ConfirmDialog, LoadingState, Table, type TableColumn } from "@/components/ui";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { AssignmentError, useAssignmentErrorText } from "@/components/lms/assignments/assignmentUi";
import { OverrideDialog } from "./OverrideDialog";
import { useStudents } from "./useStudents";

export function OverridesPanel({ courseId, assignmentId, isQuiz, ortTimeLocked, canEdit }: {
  courseId: string;
  assignmentId: string;
  isQuiz: boolean;
  ortTimeLocked: boolean;
  canEdit: boolean;
}) {
  const { lang, t } = useTranslation();
  const errorText = useAssignmentErrorText();
  const [items, setItems] = useState<OverrideOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState<OverrideOut | null | "new">(null);
  const [removing, setRemoving] = useState<OverrideOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [removeError, setRemoveError] = useState<unknown>(null);
  const students = useStudents(courseId, editing === "new");

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await listOverrides(courseId, assignmentId));
    } catch (e) {
      setError(e);
    }
  }, [courseId, assignmentId]);
  useEffect(() => { void load(); }, [load]);

  const remove = async () => {
    if (!removing) return;
    setBusy(true);
    setRemoveError(null);
    try {
      await clearOverride(courseId, assignmentId, removing.enrollment_id);
      setRemoving(null);
      await load();
    } catch (e) {
      setRemoveError(e);
    } finally {
      setBusy(false);
    }
  };

  const summary = (o: OverrideOut) => {
    const parts: string[] = [];
    if (o.due_at) parts.push(t("accommodations.override.dueTo", { date: fmtShortDateTime(o.due_at, lang) }));
    if (o.available_from) parts.push(t("accommodations.override.fromTo", { date: fmtShortDateTime(o.available_from, lang) }));
    if (o.available_until) parts.push(t("accommodations.override.untilTo", { date: fmtShortDateTime(o.available_until, lang) }));
    if (o.extra_time_percent) parts.push(t("accommodations.badge.percent", { n: o.extra_time_percent }));
    if (o.extra_time_s) parts.push(t("accommodations.badge.minutes", { n: Math.round(o.extra_time_s / 60) }));
    if (o.extra_attempts) parts.push(t("accommodations.badge.attempts", { n: o.extra_attempts }));
    return parts.join(" · ") || "—";
  };

  const columns: TableColumn<OverrideOut>[] = [
    { key: "student", header: t("accommodations.override.student"), primary: true, cell: (o) => o.student_name || "—" },
    { key: "what", header: t("accommodations.override.changes"), cell: (o) => summary(o) },
    ...(canEdit ? [{
      key: "actions", header: "", actions: true, align: "right" as const,
      cell: (o: OverrideOut) => (
        <span className="inline-flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => setEditing(o)}>{t("accommodations.override.edit")}<span className="sr-only">: {o.student_name}</span></Button>
          <Button variant="secondary" size="sm" onClick={() => { setRemoveError(null); setRemoving(o); }}>{t("accommodations.override.remove")}<span className="sr-only">: {o.student_name}</span></Button>
        </span>
      ),
    }] : []),
  ];

  return (
    <Card title={t("accommodations.override.title")} description={t("accommodations.override.panelHint")}
      actions={canEdit ? <Button variant="secondary" onClick={() => setEditing("new")}>{t("accommodations.override.add")}</Button> : undefined}>
      {error ? <AssignmentError error={error} onRetry={() => void load()} /> : !items ? <LoadingState rows={1} /> : (
        <Table<OverrideOut> caption={t("accommodations.override.title")} rows={items} rowKey={(o) => o.id || o.enrollment_id} columns={columns}
          empty={<p className="rounded-xl border border-dashed border-slate-300 p-4 text-center text-sm text-slate-600">{t("accommodations.override.empty")}</p>} />
      )}
      <OverrideDialog open={editing !== null} courseId={courseId} assignmentId={assignmentId}
        existing={editing && editing !== "new" ? editing : null} students={students.rows} studentsError={students.error}
        isQuiz={isQuiz} ortTimeLocked={ortTimeLocked}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} />
      <ConfirmDialog open={!!removing} tone="danger" busy={busy} title={t("accommodations.override.removeTitle")}
        object={removing?.student_name || undefined} effect={t("accommodations.override.removeBody")}
        confirmLabel={t("accommodations.override.remove")} onConfirm={() => void remove()} onCancel={() => setRemoving(null)}
        error={removeError ? errorText(removeError) : undefined} />
    </Card>
  );
}
