"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { EyeOff } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getAssessment } from "@/lib/lms/assessments";
import { pickLocalized } from "@/lib/lms/localized";
import { listStaffAttempts, type AttemptStaffSummaryOut } from "@/lib/lms/staffAttempts";
import type { AttemptStatus } from "@/lib/lms/attemptTypes";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { fmtDateTime, fmtPoints } from "@/components/lms/assessments/format";
import { useListCount, useTabCrumbs } from "@/components/lms/course/StaffCourseUi";
import { useTemplateUi } from "@/lib/lms/templates";
import { Badge, type BadgeTone, Checkbox, EmptyState, PageHeader, SearchInput, Select, Table, type TableColumn, buttonClasses } from "@/components/ui";
import { useGradeText } from "./GradeBadge";

const STATUSES: AttemptStatus[] = ["in_progress", "needs_review", "graded", "void"];
const LIMIT = 50;
const STATUS_TONE: Record<string, BadgeTone> = { in_progress: "info", needs_review: "warning", graded: "success", submitted: "success", void: "neutral" };

/**
 * Staff attempts of one assessment. Phase 6b S5c (UX T3): design-system Table (stacked cards under 640 px),
 * a student search over the loaded rows, a count line, status Badges and PageHeader breadcrumbs. Same API, filters and links.
 * Phase 8c S3 (PHASE_8C_DESIGN §5.1): also the Results tab of a quiz's assignment page (`embedded`: no page header;
 * the assessment comes from the `assessmentId` prop, never from the route).
 */
export function StaffAttemptList({ courseId, assessmentId, embedded = false }: { courseId: string; assessmentId: string; embedded?: boolean }) {
  const { lang, t } = useTranslation();
  const gradeText = useGradeText();
  const countText = useListCount();
  const tui = useTemplateUi();
  const ortCourse = tui.locked && tui.key === "ort";
  const [status, setStatus] = useState<AttemptStatus | "">("");
  const [previews, setPreviews] = useState(false);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<AttemptStaffSummaryOut[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const seq = useRef(0);

  useEffect(() => {
    getAssessment(courseId, assessmentId)
      .then((a) => setTitle(pickLocalized(a.title, lang, a.languages?.[0] ?? lang) || t("assessments.untitled")))
      .catch(() => setTitle(t("assessments.untitled")));
  }, [courseId, assessmentId, lang, t]);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const page = await listStaffAttempts(courseId, assessmentId, { status, preview: previews, limit: LIMIT });
      if (my !== seq.current) return;
      setRows(page.items);
      setNext(page.next_cursor);
      setError(null);
    } catch (e) {
      if (my === seq.current) setError(e);
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [courseId, assessmentId, status, previews]);
  useEffect(() => { void load(); }, [load]);

  async function loadMore() {
    if (!next) return;
    setMore(true);
    try {
      const page = await listStaffAttempts(courseId, assessmentId, { status, preview: previews, cursor: next, limit: LIMIT });
      setRows((r) => [...r, ...page.items]);
      setNext(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setMore(false);
    }
  }

  const base = `/${lang}/courses/${courseId}/assessments/${assessmentId}`;
  const crumbs = useTabCrumbs("assessments", [{ label: title || t("lms.common.loading"), href: base }, { label: t("grading.attemptsTitle") }], courseId);
  const needle = q.trim().toLocaleLowerCase(lang);
  const shown = useMemo(
    () => (needle ? rows.filter((r) => (r.student_name || "").toLocaleLowerCase(lang).includes(needle)) : rows),
    [rows, needle, lang],
  );

  const columns: TableColumn<AttemptStaffSummaryOut>[] = [
    {
      key: "student", header: t("grading.student"), primary: true,
      cell: (r) => (
        <span className="inline-flex flex-wrap items-center gap-2">
          <span>{r.student_name || t("grading.unnamed")}</span>
          {r.is_preview && <Badge tone="warning">{t("results.preview")}</Badge>}
        </span>
      ),
    },
    {
      key: "status", header: t("grading.status"), mobilePriority: 0,
      cell: (r) => (
        <span className="inline-flex flex-wrap items-center justify-end gap-1.5 sm:justify-start">
          <Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{t(`results.status.${r.status}`)}</Badge>
          {r.pending_review > 0 && <Badge tone="warning">{t("grading.pendingBadge", { n: r.pending_review })}</Badge>}
        </span>
      ),
    },
    { key: "attempt", header: t("grading.attemptNo"), cell: (r) => r.attempt_no ?? "—", nowrap: true, hideOnMobile: true },
    { key: "submitted", header: t("grading.submitted"), cell: (r) => fmtDateTime(r.submitted_at) || "—", nowrap: true, mobilePriority: 2 },
    {
      key: "score", header: t("grading.score"), nowrap: true, mobilePriority: 1,
      cell: (r) => (r.raw_score !== null && r.raw_score !== undefined ? `${fmtPoints(r.raw_score)} / ${fmtPoints(r.points_possible)}` : "—"),
    },
    {
      key: "grade", header: t("results.grade.title"), mobilePriority: 3,
      cell: (r) => (r.grade && gradeText(r.grade, r.grade.scheme_type) ? (
        <Badge tone="info" icon={!r.grade.released ? <EyeOff aria-hidden="true" /> : undefined}
          title={!r.grade.released ? t("results.grade.notReleased") : undefined}>
          {gradeText(r.grade, r.grade.scheme_type)}
          {!r.grade.released && <span className="sr-only"> ({t("results.grade.notReleased")})</span>}
        </Badge>
      ) : "—"),
    },
    {
      key: "open", header: "", actions: true, align: "right",
      cell: (r) => (
        <Link href={`${base}/attempts/${r.id}`} className={buttonClasses({ variant: "secondary", size: "sm", className: "w-full sm:w-auto" })}>
          {t("grading.open")}<span className="sr-only">: {r.student_name || t("grading.unnamed")}</span>
        </Link>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {!embedded && <PageHeader breadcrumbs={crumbs} title={t("grading.attemptsTitle")} className="mb-2" />}
      <ErrorMessage error={error} onRetry={() => void load()} />
      <Table
        caption={t("grading.attemptsTitle")}
        columns={columns}
        rows={shown}
        rowKey={(r) => r.id}
        loading={loading}
        countText={!loading ? (needle ? t("ui.table.count", { count: shown.length }) : countText(rows.length, !!next)) : undefined}
        search={ortCourse ? (
          // ORT (locked template): the filters stay exactly as they were
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end">
            <SearchInput value={q} onChange={setQ} label={t("teaching.searchStudent")} />
            <Select label={t("grading.filterStatus")} value={status} onChange={(e) => setStatus(e.target.value as AttemptStatus | "")}
              options={[{ value: "", label: t("grading.allStatuses") }, ...STATUSES.map((s) => ({ value: s, label: t(`results.status.${s}`) }))]} />
            <button type="button" onClick={() => setStatus(status === "needs_review" ? "" : "needs_review")} aria-pressed={status === "needs_review"}
              className={buttonClasses({ variant: "secondary", className: status === "needs_review" ? "border-warning-300 bg-warning-50 text-warning-900 hover:bg-warning-50" : "" })}>
              {t("grading.needsReviewOnly")}
            </button>
            <Checkbox label={t("grading.showPreviews")} checked={previews} onChange={(e) => setPreviews(e.target.checked)} containerClassName="sm:col-span-3" />
          </div>
        ) : (
          // Phase 8c UX m8: "Needs review only" is a checkbox next to "Show preview attempts"
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <SearchInput value={q} onChange={setQ} label={t("teaching.searchStudent")} />
            <Select label={t("grading.filterStatus")} value={status} onChange={(e) => setStatus(e.target.value as AttemptStatus | "")}
              options={[{ value: "", label: t("grading.allStatuses") }, ...STATUSES.map((s) => ({ value: s, label: t(`results.status.${s}`) }))]} />
            <div className="flex flex-wrap gap-x-6 gap-y-2 sm:col-span-2">
              <Checkbox label={t("grading.needsReviewOnly")} checked={status === "needs_review"}
                onChange={(e) => setStatus(e.target.checked ? "needs_review" : "")} />
              <Checkbox label={t("grading.showPreviews")} checked={previews} onChange={(e) => setPreviews(e.target.checked)} />
            </div>
          </div>
        )}
        empty={<EmptyState variant="bordered" title={needle ? t("teaching.noMatch") : t("grading.empty")} />}
        pagination={{ nextCursor: next, loading: more, onLoadMore: () => void loadMore() }}
      />
    </div>
  );
}
