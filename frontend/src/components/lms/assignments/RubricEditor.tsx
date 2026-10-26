"use client";

// Phase 7a S5: simple rubric (criteria x points, PHASE_7A_DESIGN 2.6): rows with a title and points, add / remove,
// the total compared with the assignment's points (a warning, not an error). Saved as a full replace.
import React, { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { putRubric } from "@/lib/lms/assignments";
import { RUBRIC_MAX_CRITERIA, type AssignmentStaffOut, type RubricCriterionOut } from "@/lib/lms/assignmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { Button, Card, IconButton, Input, toast } from "@/components/ui";
import { AssignmentError, fmtPts, parsePoints } from "./assignmentUi";

interface Row {
  key: string;
  id?: string;
  title: string;
  /** other languages of the title, kept unchanged */
  rest: Record<string, string>;
  points: string;
}

let seq = 0;
const newKey = () => `r${++seq}`;

function toRows(rubric: RubricCriterionOut[], lang: Lang, defaultLanguage: Lang): Row[] {
  return [...rubric].sort((a, b) => a.position - b.position).map((c) => {
    const rest: Record<string, string> = {};
    for (const [k, v] of Object.entries(c.title ?? {})) if (k !== defaultLanguage && v) rest[k] = v;
    return { key: newKey(), id: c.id, title: c.title?.[defaultLanguage] ?? pickLocalized(c.title, lang, defaultLanguage), rest, points: fmtPts(c.points) };
  });
}

export function RubricEditor({ courseId, assignment, defaultLanguage, canEdit, onSaved }: {
  courseId: string;
  assignment: AssignmentStaffOut;
  defaultLanguage: Lang;
  canEdit: boolean;
  onSaved: (rubric: RubricCriterionOut[]) => void;
}) {
  const { lang, t } = useTranslation();
  const [rows, setRows] = useState<Row[]>(() => toRows(assignment.rubric ?? [], lang, defaultLanguage));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);

  useEffect(() => { setRows(toRows(assignment.rubric ?? [], lang, defaultLanguage)); }, [assignment.rubric, lang, defaultLanguage]);

  const parsed = rows.map((r) => parsePoints(r.points));
  const bad = rows.map((r, i) => !r.title.trim() || parsed[i] === null || Number.isNaN(parsed[i]!) || parsed[i]! < 0 || parsed[i]! > 1000);
  const total = parsed.reduce<number>((s, p) => s + (p && !Number.isNaN(p) ? p : 0), 0);
  const possible = Number(assignment.points_possible ?? 0);
  const mismatch = rows.length > 0 && Math.abs(total - possible) > 0.001;

  const set = (key: string, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const save = async () => {
    setTouched(true);
    if (bad.some(Boolean)) return;
    setBusy(true);
    setError(null);
    try {
      const out = await putRubric(courseId, assignment.id, rows.map((r, i) => ({
        ...(r.id ? { id: r.id } : {}),
        title: { ...r.rest, [defaultLanguage]: r.title.trim() },
        points: parsed[i] as number,
      })));
      onSaved(out.rubric);
      toast.success(t("assignments.rubric.saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={t("assignments.rubric.title")} description={t("assignments.rubric.subtitle")}>
      {rows.length === 0 ? (
        <p className="text-base leading-6 text-slate-600 sm:text-sm">{t("assignments.rubric.empty")}</p>
      ) : (
        <ol className="space-y-3">
          {rows.map((r, i) => (
            <li key={r.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2 rounded-xl border border-slate-200 p-3 sm:grid-cols-[minmax(0,1fr)_8rem_auto]">
              <Input label={t("assignments.rubric.criterion", { n: i + 1 })} value={r.title} maxLength={200} disabled={!canEdit}
                onChange={(e) => set(r.key, { title: e.target.value })}
                error={touched && !r.title.trim() ? t("assignments.rubric.titleRequired") : undefined}
                containerClassName="col-span-2 sm:col-span-1" />
              <Input label={t("assignments.rubric.points")} inputMode="decimal" value={r.points} disabled={!canEdit}
                onChange={(e) => set(r.key, { points: e.target.value })}
                error={touched && bad[i] && r.title.trim() ? t("assignments.rubric.pointsInvalid") : undefined} />
              {canEdit && (
                <IconButton className="mt-7" aria-label={t("assignments.rubric.remove", { n: i + 1 })} icon={<X />}
                  onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} />
              )}
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-sm font-medium text-slate-800" aria-live="polite">
        {t("assignments.rubric.total", { total: fmtPts(total), possible: fmtPts(possible) })}
      </p>
      {mismatch && <p role="status" className="mt-1 rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm text-warning-900">{t("assignments.rubric.mismatch")}</p>}
      <AssignmentError error={error} className="mt-3" />
      {canEdit && (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row [&>*]:w-full sm:[&>*]:w-auto">
          <Button variant="secondary" leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} disabled={rows.length >= RUBRIC_MAX_CRITERIA}
            onClick={() => setRows((rs) => [...rs, { key: newKey(), title: "", rest: {}, points: "" }])}>
            {t("assignments.rubric.add")}
          </Button>
          <Button variant="secondary" loading={busy} onClick={() => void save()}>{t("assignments.rubric.save")}</Button>
        </div>
      )}
    </Card>
  );
}
