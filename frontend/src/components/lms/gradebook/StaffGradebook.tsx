"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Columns3, MoreHorizontal, RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { getGradebook } from "@/lib/lms/grading";
import type { CellOut, GbAssessmentOut, GbRowOut } from "@/lib/lms/gradingTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { Pager } from "@/components/lms/Pager";
import { SchemeError } from "@/components/lms/grading/schemes/SchemeError";
import { useSchemeLabel } from "@/components/lms/grading/schemes/labels";
import { fmtNum } from "@/components/lms/grading/schemes/params";
import { btnSecondary } from "@/components/lms/content/ui";
import { cellView, fmtPercent, mergeRows, patchCell } from "./gradebookModel";
import { CellBody, useCellDescription } from "./GradeCell";
import { GradebookLegend } from "./GradebookLegend";
import { AssessmentActionsDialog } from "./AssessmentActionsDialog";
import { ColumnFilterDialog, type ColumnOption } from "./ColumnFilterDialog";
import { SubmissionPanel, type PanelTarget } from "./SubmissionPanel";
import { useWarningText } from "./warnings";

const LIMIT = 50;

/**
 * Staff gradebook (PHASE_4_DESIGN.md section 6): students (cursor-paged, 50 per page) x published assessments.
 * The first column is sticky; only the table scrolls horizontally. Cell click opens the submission panel,
 * a column header opens the per-assessment actions (release, hide, regrade). The server decides every permission.
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

  const [rows, setRows] = useState<GbRowOut[]>([]);
  const [columns, setColumns] = useState<GbAssessmentOut[]>([]);
  const [allColumns, setAllColumns] = useState<GbAssessmentOut[]>([]);
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
    (a: Pick<GbAssessmentOut, "title">) => pickLocalized(a.title, lang, course.default_language) || t("gradebook.untitled"),
    [lang, course.default_language, t],
  );

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const page = await getGradebook(courseId, { limit: LIMIT, assessment_ids: selected ?? undefined });
      if (my !== seq.current) return;
      setRows(page.rows);
      setColumns(page.assessments);
      if (!selected) setAllColumns(page.assessments);
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
      const page = await getGradebook(courseId, { cursor: next, limit: LIMIT, assessment_ids: selected ?? undefined });
      if (my !== seq.current) return;
      setRows((r) => mergeRows(r, page.rows));
      setNext(page.next_cursor);
    } catch (e) {
      if (my === seq.current) setError(e);
    } finally {
      setMore(false);
    }
  }

  const onCell = useCallback((enrollmentId: string, assessmentId: string, cell: CellOut | null) => {
    setRows((r) => patchCell(r, enrollmentId, assessmentId, cell));
    setTotalsStale(true);
  }, []);
  const closePanel = useCallback(() => setPanel(null), []);

  const options: ColumnOption[] = useMemo(() => allColumns.map((a) => ({ id: a.id, title: title(a) })), [allColumns, title]);
  const actionsAssessment = columns.find((a) => a.id === actionsFor) ?? null;
  const now = Date.now();

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl font-bold text-slate-900">{t("gradebook.title")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t("gradebook.subtitle")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {allColumns.length > 0 && (
            <button type="button" onClick={() => setFilterOpen(true)} className={`${btnSecondary} inline-flex items-center gap-1.5`}>
              <Columns3 className="h-4 w-4" aria-hidden="true" />
              {selected ? t("gradebook.columns.countOf", { shown: columns.length, total: allColumns.length }) : t("gradebook.columns.button")}
            </button>
          )}
          <button type="button" onClick={() => void load()} disabled={loading} className={`${btnSecondary} inline-flex items-center gap-1.5`}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />{t("gradebook.refresh")}
          </button>
        </div>
      </div>

      {!canManage && course.status === "concluded" && (
        <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("gradebook.readOnlyConcluded")}</p>
      )}
      {totalsStale && (
        <p role="status" className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span>{t("gradebook.totalsStale")}</span>
          <button type="button" onClick={() => void load()} className="font-semibold underline">{t("gradebook.refresh")}</button>
        </p>
      )}
      <SchemeError error={error} onRetry={() => void load()} />

      {loading && rows.length === 0 ? (
        <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>
      ) : !error && columns.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("gradebook.noAssessments")}</p>
      ) : !error && rows.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("gradebook.noStudents")}</p>
      ) : rows.length > 0 ? (
        <>
          <GradebookLegend />
          <div className={`max-h-[70vh] w-full max-w-full overflow-auto rounded-2xl border border-slate-200 bg-white ${loading ? "opacity-60" : ""}`}
            role="region" aria-label={t("gradebook.title")} tabIndex={0}>
            <table className="min-w-full border-separate border-spacing-0 text-sm">
              <thead>
                <tr>
                  <th scope="col" className="sticky left-0 top-0 z-30 min-w-[9rem] max-w-[12rem] border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-semibold text-slate-600">
                    {t("gradebook.student")}
                  </th>
                  {columns.map((a) => {
                    const name = title(a);
                    const possible = fmtNum(a.points_possible);
                    return (
                      <th key={a.id} scope="col" className="sticky top-0 z-20 min-w-[8rem] max-w-[11rem] border-b border-slate-200 bg-slate-50 p-0 text-left align-top text-xs font-semibold text-slate-700">
                        <button type="button" onClick={() => setActionsFor(a.id)} aria-label={t("gradebook.header.actionsFor", { title: name })}
                          className="flex h-full w-full flex-col items-start gap-0.5 px-3 py-2 text-left hover:bg-slate-100">
                          <span className="flex w-full items-start justify-between gap-1">
                            <span className="line-clamp-2 break-words">{name}</span>
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
                      </th>
                    );
                  })}
                  <th scope="col" className="sticky top-0 z-20 min-w-[7rem] border-b border-l border-slate-200 bg-slate-50 px-3 py-2 text-left align-top text-xs font-semibold text-slate-700">
                    {t("gradebook.total.title")}
                    <span className="block font-normal text-slate-500">{t("gradebook.total.hint")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const student = r.student_name || t("gradebook.unnamed");
                  const cur = fmtPercent(r.total.current_percent);
                  const fin = fmtPercent(r.total.final_percent);
                  const totalMain = fmtNum(r.total.display_value) || (r.total.label ? labelText(r.total.label) : "") || cur || "—";
                  return (
                    <tr key={r.enrollment_id} className="group">
                      <th scope="row" className="sticky left-0 z-10 min-w-[9rem] max-w-[12rem] border-b border-r border-slate-100 bg-white px-3 py-2 text-left font-medium text-slate-900 group-hover:bg-slate-50">
                        <span className="line-clamp-2 break-words">{student}</span>
                      </th>
                      {columns.map((a) => {
                        const cell = r.cells[a.id];
                        const v = cellView(cell, a, now);
                        const desc = describe(v);
                        return (
                          <td key={a.id} className="border-b border-slate-100 p-0 align-top group-hover:bg-slate-50">
                            {cell ? (
                              <button type="button" title={desc} aria-label={t("gradebook.cell.open", { student, title: title(a), state: desc })}
                                onClick={() => setPanel({
                                  submissionId: cell.submission_id, enrollmentId: r.enrollment_id, assessmentId: a.id,
                                  studentName: student, assessmentTitle: title(a), dueAt: a.due_at,
                                  gradeRelease: a.grade_release,
                                })}
                                className="block h-full w-full px-3 py-2 text-left hover:bg-brand-50 focus:bg-brand-50 focus:outline-none">
                                <CellBody v={v} />
                              </button>
                            ) : (
                              <div className="px-3 py-2" title={desc}>
                                <span className="sr-only">{desc}</span>
                                <span aria-hidden="true"><CellBody v={v} /></span>
                              </div>
                            )}
                          </td>
                        );
                      })}
                      <td className="border-b border-l border-slate-100 px-3 py-2 align-top group-hover:bg-slate-50">
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
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pager nextCursor={next} loading={more} onMore={() => void loadMore()} />
        </>
      ) : null}

      <ColumnFilterDialog open={filterOpen} options={options} selected={selected} onClose={() => setFilterOpen(false)}
        onApply={(ids) => { setFilterOpen(false); setPanel(null); setSelected(ids); }} />
      <AssessmentActionsDialog open={!!actionsAssessment} courseId={courseId} assessment={actionsAssessment}
        title={actionsAssessment ? title(actionsAssessment) : ""} defaultLanguage={course.default_language} canManage={canManage}
        onClose={() => setActionsFor(null)} onChanged={() => void load()} />
      {panel && <SubmissionPanel courseId={courseId} target={panel} canManage={canManage} onClose={closePanel} onCell={onCell} />}
    </div>
  );
}
