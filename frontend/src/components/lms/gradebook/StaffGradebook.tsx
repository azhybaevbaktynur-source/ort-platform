"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Columns3, MoreHorizontal, RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getGradebook } from "@/lib/lms/grading";
import type { CellOut, GbAssignmentOut, GbRowOut } from "@/lib/lms/gradingTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { fmtNum } from "@/components/lms/grading/schemes/params";
import { Button, EmptyState, LoadingState, PageHeader, Table, type TableColumn } from "@/components/ui"; // Phase 6b S5c
import { KindIcon } from "@/components/lms/assignments/assignmentUi"; // Phase 7a S5
import { useCategories } from "@/components/lms/assignments/useCategories"; // Phase 7a S5
import { cellView, fmtPercent, mergeRows, patchCell } from "./gradebookModel";
import { CellBody, useCellDescription } from "./GradeCell";
import { GradebookLegend } from "./GradebookLegend";
import { AssessmentActionsDialog } from "./AssessmentActionsDialog";
import { ColumnFilterDialog, type ColumnOption } from "./ColumnFilterDialog";
import { SubmissionPanel, type PanelTarget } from "./SubmissionPanel";
import { useWarningText } from "./warnings";

const LIMIT = 50;

/**
 * Staff gradebook (PHASE_4_DESIGN.md section 6; Phase 7a S5: one column per assignment, PHASE_7A_DESIGN 4.3 and 5).
 * Students (cursor-paged, 50 per page) x published assignments on the design-system Table; the student column is
 * sticky and the table scrolls inside its box on phones. A cell opens the submission panel (quiz: attempts as before;
 * other kinds: hand-ins, rubric and feedback); a column header opens the assignment's grade actions. An empty cell of
 * a non-quiz assignment leads to its grading screen. The cells and numbers are the Phase 4 ones (ORT: one column,
 * same cells). The server decides every permission.
 */
export function StaffGradebook() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const labelText = useSchemeLabel();
  const describe = useCellDescription();
  const warningText = useWarningText();
  const role = course.my_enrollment.role;
  const canManage = (role === "teacher" || role === "assistant") && course.status !== "concluded";
  const courseId = course.id;
  const categories = useCategories(courseId);
  const base = `/${lang}/courses/${courseId}`;

  const [rows, setRows] = useState<GbRowOut[]>([]);
  const [columns, setColumns] = useState<GbAssignmentOut[]>([]);
  const [allColumns, setAllColumns] = useState<GbAssignmentOut[]>([]);
  const [selected, setSelected] = useState<string[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [totalsStale, setTotalsStale] = useState(false);
  const [panel, setPanel] = useState<PanelTarget | null>(null);
  const [actionsFor, setActionsFor] = useState<string | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const seq = useRef(0);

  const title = useCallback(
    (a: Pick<GbAssignmentOut, "title">) => pickLocalized(a.title, lang, course.default_language) || t("gradebook.untitled"),
    [lang, course.default_language, t],
  );

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const page = await getGradebook(courseId, { limit: LIMIT, assignment_ids: selected ?? undefined });
      if (my !== seq.current) return;
      const cols = page.assignments ?? [];
      setRows(page.rows);
      setColumns(cols);
      if (!selected) setAllColumns(cols);
      setNext(page.next_cursor);
      setTotalsStale(false);
      setError(null);
    } catch (e) {
      if (my === seq.current) setError(e);
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [courseId, selected]);
  useEffect(() => { void load(); }, [load]);

  async function loadMore() {
    if (!next) return;
    const my = seq.current;
    setMore(true);
    try {
      const page = await getGradebook(courseId, { cursor: next, limit: LIMIT, assignment_ids: selected ?? undefined });
      if (my !== seq.current) return;
      setRows((r) => mergeRows(r, page.rows));
      setNext(page.next_cursor);
    } catch (e) {
      if (my === seq.current) setError(e);
    } finally {
      setMore(false);
    }
  }

  const onCell = useCallback((enrollmentId: string, assignmentId: string, cell: CellOut | null) => {
    setRows((r) => patchCell(r, enrollmentId, assignmentId, cell));
    setTotalsStale(true);
  }, []);
  const closePanel = useCallback(() => setPanel(null), []);

  const options: ColumnOption[] = useMemo(
    () => allColumns.map((a) => ({ id: a.id, title: title(a), kind: a.kind, categoryId: a.category_id })),
    [allColumns, title],
  );
  const actionsAssignment = columns.find((a) => a.id === actionsFor) ?? null;
  const now = Date.now();

  const header = (a: GbAssignmentOut) => {
    const name = title(a);
    const possible = fmtNum(a.points_possible);
    return (
      <button type="button" onClick={() => setActionsFor(a.id)} aria-label={t("gradebook.header.actionsFor", { title: name })}
        className="-mx-2 flex w-[calc(100%+1rem)] min-w-[8rem] max-w-[12rem] flex-col items-start gap-0.5 rounded-lg px-2 py-1 text-left hover:bg-slate-200/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600">
        <span className="flex w-full items-start justify-between gap-1">
          <span className="flex min-w-0 items-start gap-1">
            <KindIcon kind={a.kind} className="mt-0.5 h-3.5 w-3.5 text-slate-500" />
            <span className="line-clamp-2 break-words">{name}</span>
          </span>
          <MoreHorizontal className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-slate-400" aria-hidden="true" />
        </span>
        <span className="font-normal text-slate-500">
          {a.scheme && fmtNum(a.scheme.scale_min) && fmtNum(a.scheme.scale_max)
            ? `${fmtNum(a.scheme.scale_min)}–${fmtNum(a.scheme.scale_max)}`
            : possible ? t("gradebook.header.outOf", { n: possible }) : ""}
        </span>
        <span className="flex flex-wrap gap-1 font-normal">
          {a.grade_release === "manual" && (
            <span className="rounded bg-slate-200 px-1 text-[10px] text-slate-700">
              {t("gradebook.header.releasedN", { n: a.released_count, total: a.submission_count })}
            </span>
          )}
          {a.stale_count > 0 && (
            <span className="rounded bg-amber-100 px-1 text-[10px] font-semibold text-amber-900">{t("gradebook.header.staleN", { n: a.stale_count })}</span>
          )}
          {a.omit_from_total && <span className="rounded bg-slate-200 px-1 text-[10px] text-slate-700">{t("gradebook.header.omitted")}</span>}
          {a.warnings.length > 0 && <AlertTriangle className="h-3 w-3 text-amber-600" aria-label={a.warnings.map(warningText).join(" ")} />}
        </span>
      </button>
    );
  };

  const cellFor = (r: GbRowOut, a: GbAssignmentOut, student: string) => {
    const cell = r.cells[a.id];
    const v = cellView(cell, a, now);
    const desc = describe(v);
    if (cell) {
      return (
        <button type="button" title={desc} aria-label={t("gradebook.cell.open", { student, title: title(a), state: desc })}
          onClick={() => setPanel({
            submissionId: cell.submission_id, enrollmentId: r.enrollment_id, assessmentId: a.id,
            studentName: student, assessmentTitle: title(a), dueAt: a.due_at,
            gradeRelease: a.grade_release, labels: a.scheme?.labels ?? null,
            kind: a.kind, quizAssessmentId: a.assessment_id,
          })}
          className="-mx-2 -my-1 block min-h-11 w-[calc(100%+1rem)] rounded-lg px-2 py-1 text-left hover:bg-brand-50 focus:bg-brand-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 sm:min-h-0">
          <CellBody v={v} />
        </button>
      );
    }
    if (a.kind !== "quiz" && canManage) {
      return (
        <Link href={`${base}/assignments/${a.id}/grade?enrollment=${encodeURIComponent(r.enrollment_id)}`} title={desc}
          aria-label={t("assignments.gradebook.gradeCell", { student, title: title(a), state: desc })}
          className="-mx-2 -my-1 block min-h-11 rounded-lg px-2 py-1 hover:bg-brand-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 sm:min-h-0">
          <span aria-hidden="true"><CellBody v={v} /></span>
        </Link>
      );
    }
    return (
      <div title={desc}>
        <span className="sr-only">{desc}</span>
        <span aria-hidden="true"><CellBody v={v} /></span>
      </div>
    );
  };

  const tableColumns: TableColumn<GbRowOut>[] = [
    {
      key: "student", header: t("gradebook.student"), primary: true,
      headerClassName: "sticky left-0 z-20 min-w-[9rem] max-w-[12rem] border-r border-slate-200 bg-slate-50 text-xs",
      className: "sticky left-0 z-10 min-w-[9rem] max-w-[12rem] border-r border-slate-100 bg-white align-top",
      cell: (r) => <span className="line-clamp-2 break-words">{r.student_name || t("gradebook.unnamed")}</span>,
    },
    ...columns.map((a): TableColumn<GbRowOut> => ({
      key: a.id, header: header(a), label: title(a),
      headerClassName: "min-w-[8rem] max-w-[12rem] align-top text-xs",
      className: "align-top",
      cell: (r) => cellFor(r, a, r.student_name || t("gradebook.unnamed")),
    })),
    {
      key: "total", label: t("gradebook.total.title"),
      header: <span className="block">{t("gradebook.total.title")}<span className="block font-normal text-slate-500">{t("gradebook.total.hint")}</span></span>,
      headerClassName: "min-w-[7rem] border-l border-slate-200 align-top text-xs",
      className: "border-l border-slate-100 align-top",
      cell: (r) => {
        const cur = fmtPercent(r.total.current_percent);
        const fin = fmtPercent(r.total.final_percent);
        const totalMain = fmtNum(r.total.display_value) || (r.total.label ? labelText(r.total.label) : "") || cur || "—";
        return (
          <span className="flex flex-col leading-tight">
            <span className="flex items-center gap-1 font-semibold text-slate-900">
              {totalMain}
              {r.total.warnings.length > 0 && (
                <AlertTriangle className="h-3 w-3 text-amber-600" aria-label={r.total.warnings.map(warningText).join(" ")} />
              )}
            </span>
            {(fmtNum(r.total.display_value) || r.total.label) && cur && <span className="text-[11px] text-slate-500">{cur}</span>}
            {fin && <span className="text-[11px] text-slate-500">{t("gradebook.total.final", { value: fin })}</span>}
          </span>
        );
      },
    },
  ];

  return (
    <div className="min-w-0 space-y-4">
      {/* Phase 6b S5c: design-system PageHeader (the page's h1). */}
      <PageHeader title={t("gradebook.title")} description={t("gradebook.subtitle")} className="mb-2"
        secondaryActions={<>
          {allColumns.length > 0 && (
            <Button variant="secondary" onClick={() => setFilterOpen(true)} leftIcon={<Columns3 className="h-4 w-4" aria-hidden="true" />}>
              {selected ? t("gradebook.columns.countOf", { shown: columns.length, total: allColumns.length }) : t("gradebook.columns.button")}
            </Button>
          )}
          <Button variant="secondary" onClick={() => void load()} disabled={loading} leftIcon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}>
            {t("gradebook.refresh")}
          </Button>
        </>} />

      {!canManage && course.status === "concluded" && (
        <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("gradebook.readOnlyConcluded")}</p>
      )}
      {totalsStale && (
        <p role="status" className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span>{t("gradebook.totalsStale")}</span>
          <Button variant="link" onClick={() => void load()}>{t("gradebook.refresh")}</Button>
        </p>
      )}
      <SchemeError error={error} onRetry={() => void load()} />

      {loading && rows.length === 0 && !error ? (
        <LoadingState rows={2} />
      ) : !error && columns.length === 0 ? (
        <EmptyState title={t("assignments.gradebook.noAssignments")} description={t("assignments.gradebook.noAssignmentsHint")} />
      ) : !error && rows.length === 0 ? (
        <EmptyState title={t("gradebook.noStudents")} />
      ) : rows.length > 0 ? (
        <>
          <GradebookLegend />
          <div className={loading ? "opacity-60" : undefined}>
            <Table<GbRowOut>
              caption={t("gradebook.title")}
              rows={rows}
              rowKey={(r) => r.enrollment_id}
              columns={tableColumns}
              mobile="scroll"
              countText={t("assignments.gradebook.countLine", { students: rows.length, columns: columns.length })}
              pagination={{ nextCursor: next, loading: more, onLoadMore: () => void loadMore() }}
            />
          </div>
        </>
      ) : null}

      <ColumnFilterDialog open={filterOpen} options={options} selected={selected} categories={categories} defaultLanguage={course.default_language}
        onClose={() => setFilterOpen(false)}
        onApply={(ids) => { setFilterOpen(false); setPanel(null); setSelected(ids); }} />
      <AssessmentActionsDialog open={!!actionsAssignment} courseId={courseId} assessment={actionsAssignment}
        title={actionsAssignment ? title(actionsAssignment) : ""} defaultLanguage={course.default_language} canManage={canManage}
        onClose={() => setActionsFor(null)} onChanged={() => void load()} />
      {panel && <SubmissionPanel courseId={courseId} target={panel} canManage={canManage} onClose={closePanel} onCell={onCell} />}
    </div>
  );
}
