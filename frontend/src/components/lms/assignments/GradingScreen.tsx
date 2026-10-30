"use client";

// Phase 7a S5: grading screen of one assignment (PHASE_7A_DESIGN 5): the roster with a status filter (Table; stacked
// cards on phones) and the grade panel for the chosen student (right on desktop, below on phones), next / previous
// student by button or Alt+Arrow keys, release / hide for everyone. Phase 8c S3 (PHASE_8C_DESIGN §5.1): the
// "Submissions and grading" tab of the assignment page (`embedded`: no header of its own; `filter` from `?filter=`,
// e.g. `to_grade` from the To do panel).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import {
  getStaffAssignment, listAssignmentSubmissions, releaseAssignmentGrades, unreleaseAssignmentGrades,
} from "@/lib/lms/assignments";
import type { AssignmentStaffOut, AssignmentSubmissionRowOut, AssignmentSubmissionStaffOut } from "@/lib/lms/assignmentTypes";
import { cellFromSubmission } from "@/components/lms/gradebook/gradebookModel";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { fmtShortDateTime } from "@/components/lms/home/format";
import {
  Badge, Button, ConfirmDialog, Dialog, EmptyState, LinkButton, LoadingState, PageHeader, Select, Table, toast, type TableColumn,
} from "@/components/ui";
import { AssignmentError, KindBadge, LateBadge, fmtPts, useAssignmentErrorText } from "./assignmentUi";
import { GradePanel, type GradePanelHandle } from "./GradePanel";

type Filter = "all" | "to_grade" | "graded" | "missing" | "resubmitted";
const FILTERS: Filter[] = ["all", "to_grade", "graded", "missing", "resubmitted"];
const asFilter = (v: string | null | undefined): Filter => (FILTERS as string[]).includes(v ?? "") ? (v as Filter) : "all";

function rowState(r: AssignmentSubmissionRowOut): Exclude<Filter, "all" | "resubmitted"> {
  const graded = r.cell && r.cell.state === "graded" && r.cell.raw_points !== null && r.cell.raw_points !== undefined;
  if (graded && !r.resubmitted) return "graded";
  if (r.hand_in_count > 0) return "to_grade";
  return graded ? "graded" : "missing";
}

export function GradingScreen({ assignmentId, filter: filterProp, onFilterChange, embedded = false }: {
  assignmentId: string;
  /** Initial status filter (`?filter=`); unknown values mean "all". */
  filter?: string | null;
  /** Called when the teacher changes the filter (the page keeps it in the URL). */
  onFilterChange?: (f: Filter) => void;
  /** Inside the assignment page: no page header (the page has it). */
  embedded?: boolean;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const params = useSearchParams();
  const errorText = useAssignmentErrorText();
  const role = course.my_enrollment.role;
  const canManage = (role === "teacher" || role === "assistant") && course.status !== "concluded";
  const base = `/${lang}/courses/${course.id}`;
  const [a, setA] = useState<AssignmentStaffOut | null>(null);
  const [rows, setRows] = useState<AssignmentSubmissionRowOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilterState] = useState<Filter>(() => asFilter(filterProp));
  useEffect(() => { setFilterState(asFilter(filterProp)); }, [filterProp]);
  const setFilter = (f: Filter) => { setFilterState(f); onFilterChange?.(f); };
  const [selected, setSelected] = useState<string | null>(params.get("enrollment"));
  const [bulk, setBulk] = useState<"release" | "unrelease" | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<unknown>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  // Phase 7a UX: an unsaved grade is never lost by switching student (ask: save and go / do not save / cancel)
  const gradeRef = useRef<GradePanelHandle>(null);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<{ id: string | null } | null>(null);
  const [leaving, setLeaving] = useState(false);
  const stayRef = useRef<HTMLButtonElement>(null);
  const live = useRef({ dirty, selected });
  live.current = { dirty, selected };
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const [asg, page] = await Promise.all([
        next ? Promise.resolve(null) : getStaffAssignment(course.id, assignmentId),
        listAssignmentSubmissions(course.id, assignmentId, { cursor: next, limit: 50 }),
      ]);
      if (asg) setA(asg);
      setRows((p) => (next ? [...p, ...page.rows] : page.rows));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, assignmentId]);
  useEffect(() => { void load(); }, [load]);

  const visible = useMemo(() => rows.filter((r) => filter === "all" || (filter === "resubmitted" ? r.resubmitted : rowState(r) === filter)), [rows, filter]);
  const index = visible.findIndex((r) => r.enrollment_id === selected);
  const current = rows.find((r) => r.enrollment_id === selected) ?? null;

  const go = useCallback((id: string | null) => {
    setSelected(id);
    if (id && typeof window !== "undefined" && window.matchMedia("(max-width: 1023px)").matches) {
      setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
    }
  }, []);
  const choose = useCallback((id: string | null) => {
    if (id === live.current.selected) return;
    if (live.current.dirty) { setPending({ id }); return; }
    go(id);
  }, [go]);
  const saveAndGo = async () => {
    if (!pending) return;
    setLeaving(true);
    const ok = (await gradeRef.current?.save()) ?? false;
    setLeaving(false);
    setPending(null);
    if (ok) go(pending.id); // not saved: stay, the panel shows why
  };
  const discardAndGo = () => {
    if (!pending) return;
    setPending(null);
    setDirty(false);
    go(pending.id);
  };
  const prev = index > 0 ? () => choose(visible[index - 1].enrollment_id) : undefined;
  const next = index >= 0 && index < visible.length - 1 ? () => choose(visible[index + 1].enrollment_id) : undefined;

  const nav = useRef({ prev, next });
  nav.current = { prev, next };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey) return;
      const { prev: p, next: n } = nav.current;
      if (e.key === "ArrowDown" && n) { e.preventDefault(); n(); }
      else if (e.key === "ArrowUp" && p) { e.preventDefault(); p(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onChanged = useCallback((sub: AssignmentSubmissionStaffOut | null) => {
    if (!selected) return;
    setRows((rs) => rs.map((r) => (r.enrollment_id === selected
      ? { ...r, cell: sub ? cellFromSubmission(sub) : null, resubmitted: sub ? !!sub.graded_item_id && sub.hand_ins.length > 0 && sub.graded_item_id !== [...sub.hand_ins].sort((x, y) => y.attempt_no - x.attempt_no)[0].id : r.resubmitted }
      : r)));
  }, [selected]);

  const runBulk = async () => {
    if (!bulk || !a) return;
    setBulkBusy(true);
    setBulkError(null);
    try {
      if (bulk === "release") {
        const r = await releaseAssignmentGrades(course.id, a.id);
        toast.success(t("assignments.list.releasedN", { n: r.released }));
      } else {
        const r = await unreleaseAssignmentGrades(course.id, a.id);
        toast.success(t("assignments.list.unreleasedN", { n: r.unreleased }));
      }
      setBulk(null);
      await load();
    } catch (e) {
      setBulkError(e);
    } finally {
      setBulkBusy(false);
    }
  };

  const title = a ? pickLocalized(a.title, lang, course.default_language) || t("assignments.untitled") : "";
  const crumbs = [
    { label: t("assignments.tab"), href: `${base}/assignments` },
    ...(a ? [{ label: title, href: `${base}/assignments/${a.id}` }] : []),
    { label: t("assignments.grade.title") },
  ];

  const statusBadge = (r: AssignmentSubmissionRowOut) => {
    const s = rowState(r);
    return (
      <span className="inline-flex flex-col items-start gap-1">
        {s === "graded" ? <Badge tone="success">{t("assignments.status.graded")}</Badge>
          : s === "to_grade" ? <Badge tone="info">{t("assignments.grade.needsGrading")}</Badge>
          : <Badge tone="neutral">{t("assignments.grade.notHandedIn")}</Badge>}
        {r.resubmitted && <Badge tone="warning">{t("assignments.grade.resubmitted")}</Badge>}
        {r.late && <LateBadge />}
      </span>
    );
  };

  const columns: TableColumn<AssignmentSubmissionRowOut>[] = [
    {
      key: "student", header: t("gradebook.student"), primary: true,
      cell: (r) => (
        // S6: the name is the one action of the row (a separate "Grade" column was cut off in the half-width table)
        <button type="button" onClick={() => choose(r.enrollment_id)} aria-current={r.enrollment_id === selected ? "true" : undefined}
          aria-label={`${t("assignments.grade.open")}: ${r.student_name || t("gradebook.unnamed")}`}
          className="min-h-11 break-words text-left font-semibold text-brand-700 underline-offset-2 hover:underline sm:min-h-0">
          {r.student_name || t("gradebook.unnamed")}
        </button>
      ),
    },
    { key: "status", header: t("assignments.grade.colStatus"), cell: statusBadge, mobilePriority: 0 },
    { key: "handedIn", header: t("assignments.grade.colHandedIn"), nowrap: true, mobilePriority: 1, cell: (r) => (r.latest_submitted_at ? fmtShortDateTime(r.latest_submitted_at, lang) : "—") },
    {
      key: "grade", header: t("assignments.grade.colGrade"), align: "right", nowrap: true, mobilePriority: 2,
      cell: (r) => r.cell && r.cell.raw_points !== null && r.cell.raw_points !== undefined
        ? `${fmtPts(r.cell.effective_points ?? r.cell.raw_points)} / ${fmtPts(r.cell.points_possible ?? a?.points_possible)}` : "—",
    },
  ];

  if (error && !a) {
    return (
      <div className="space-y-4">
        {!embedded && <PageHeader title={t("assignments.grade.title")} breadcrumbs={crumbs} />}
        <AssignmentError error={error} onRetry={() => void load()} />
      </div>
    );
  }
  if (!a) return <LoadingState rows={3} />;
  if (a.kind === "quiz") {
    return (
      <div className="space-y-4">
        {!embedded && <PageHeader title={title} breadcrumbs={crumbs} />}
        <EmptyState title={t("assignments.grade.quizTitle")} description={t("assignments.grade.quizBody")}
          action={<LinkButton href={`${base}/grades`}>{t("assignments.grade.toGradebook")}</LinkButton>} />
      </div>
    );
  }

  const counts = { to_grade: rows.filter((r) => rowState(r) === "to_grade").length };
  const bulkButtons = canManage && a.grade_release === "manual" ? (
    <>
      <Button variant="secondary" onClick={() => { setBulkError(null); setBulk("release"); }}>{t("assignments.list.release")}</Button>
      <Button variant="secondary" onClick={() => { setBulkError(null); setBulk("unrelease"); }}>{t("assignments.list.unrelease")}</Button>
    </>
  ) : undefined;
  return (
    <div className="space-y-4">
      {embedded ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <p className="text-sm text-slate-600">{t("assignments.grade.subtitle", { n: counts.to_grade })}</p>
          {bulkButtons && <div className="flex flex-wrap gap-2 [&>*]:flex-1 sm:[&>*]:flex-none">{bulkButtons}</div>}
        </div>
      ) : (
        <PageHeader title={title} breadcrumbs={crumbs} className="mb-2" badge={<KindBadge kind={a.kind} />}
          description={t("assignments.grade.subtitle", { n: counts.to_grade })} secondaryActions={bulkButtons} />
      )}
      {!canManage && course.status === "concluded" && <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("gradebook.readOnlyConcluded")}</p>}
      {a.grade_release === "manual" && <p className="text-sm text-slate-600">{t("assignments.grade.manualHint")}</p>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-start">
        <Table<AssignmentSubmissionRowOut>
          caption={t("assignments.grade.rosterCaption")}
          rows={visible}
          rowKey={(r) => r.enrollment_id}
          columns={columns}
          loading={loading}
          countText={t("ui.table.count", { count: visible.length })}
          rowClassName={(r) => (r.enrollment_id === selected ? "bg-brand-50" : undefined)}
          search={(
            <Select label={t("assignments.grade.filter")} value={filter} onChange={(e) => setFilter(e.target.value as Filter)} containerClassName="sm:max-w-xs"
              options={FILTERS.map((f) => ({ value: f, label: t(`assignments.grade.filters.${f}`) }))} />
          )}
          error={error ? <AssignmentError error={error} onRetry={() => void load()} /> : undefined}
          empty={<EmptyState variant="plain" title={filter === "all" ? t("assignments.grade.noStudents") : t("assignments.grade.noneInFilter")} />}
          pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }}
        />
        <div ref={panelRef} className="scroll-mt-4 lg:sticky lg:top-4">
          {current ? (
            <GradePanel key={current.enrollment_id} ref={gradeRef} courseId={course.id} assignment={a} row={current} defaultLanguage={course.default_language}
              canManage={canManage} onChanged={onChanged} onPrev={prev} onNext={next} onDirtyChange={setDirty} />
          ) : (
            <EmptyState title={t("assignments.grade.pickTitle")} description={t("assignments.grade.pickBody")} />
          )}
          {current && <p className="mt-2 hidden text-sm text-slate-600 lg:block">{t("assignments.grade.keysHint")}</p>}
        </div>
      </div>

      <ConfirmDialog open={!!bulk} tone={bulk === "unrelease" ? "danger" : "primary"} busy={bulkBusy}
        title={bulk === "release" ? t("assignments.grade.releaseAllTitle") : t("assignments.list.unreleaseTitle")} object={title}
        effect={bulk === "release" ? t("assignments.grade.releaseAllBody") : t("assignments.list.unreleaseBody")}
        confirmLabel={bulk === "release" ? t("assignments.list.release") : t("assignments.list.unrelease")}
        onConfirm={() => void runBulk()} onCancel={() => setBulk(null)} error={bulkError ? errorText(bulkError) : undefined} />
      <Dialog open={!!pending} onClose={() => setPending(null)} title={t("assignments.grade.unsavedTitle")} busy={leaving} size="md"
        role="alertdialog" closeOnBackdrop={false} initialFocusRef={stayRef}
        footer={(
          <>
            <Button ref={stayRef} variant="secondary" disabled={leaving} onClick={() => setPending(null)}>{t("ui.cancel")}</Button>
            <Button variant="secondary" disabled={leaving} onClick={discardAndGo}>{t("assignments.grade.discard")}</Button>
            <Button loading={leaving} onClick={() => void saveAndGo()}>{t("assignments.grade.saveAndGo")}</Button>
          </>
        )}>
        <p className="mb-3 break-words rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-semibold text-slate-900">{current?.student_name || t("gradebook.unnamed")}</p>
        <p className="text-slate-700">{t("assignments.grade.unsavedBody")}</p>
      </Dialog>
    </div>
  );
}
