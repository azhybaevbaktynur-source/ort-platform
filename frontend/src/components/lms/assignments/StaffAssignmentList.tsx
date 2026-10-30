"use client";

// Phase 7a S5: the teacher's Assignments tab (PHASE_7A_DESIGN 5): a design-system Table with search, kind / published /
// category filters, a published switch per row (quizzes publish in the exam builder), a row menu (edit, grade, release,
// order, delete) and one primary button "New assignment". The server decides every permission.
// Phase 8c S3 (PHASE_8C_DESIGN §4.1, §5.3): the filters live in the URL (`?kind=quiz|text|file|none`,
// `?published=yes|no`, `?category=`, `?needs_grading=1`), `?new=<kind>` opens "New assignment" with that kind
// (a locked ORT course has no "New" here: its exam is created from the Course page, so `?new=` goes there), and every
// link into an assignment or a quiz carries `from` = this list with its filters.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ClipboardList } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  deleteAssignment, listAssignments, releaseAssignmentGrades, reorderAssignments, restoreAssignment, unreleaseAssignmentGrades,
  updateAssignment,
} from "@/lib/lms/assignments";
import type { AssignmentKind, AssignmentStaffSummaryOut } from "@/lib/lms/assignmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { withFrom } from "@/lib/lms/nav";
import { useTemplateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { useListCount } from "@/components/lms/course/StaffCourseUi";
import {
  Badge, Button, Checkbox, ConfirmDialog, EmptyState, FilterBar, MenuButton, PageHeader, Select, Switch, Table, toast,
  type MenuItem, type TableColumn,
} from "@/components/ui";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { AssignmentError, KindBadge, fmtPts, useAssignmentErrorText } from "./assignmentUi";
import { AssignmentEditorDialog } from "./AssignmentEditorDialog";
import { useCategories } from "./useCategories";

const KINDS: AssignmentKind[] = ["quiz", "text", "file", "none"];
const asKind = (v: string | null): AssignmentKind | "" => ((KINDS as string[]).includes(v ?? "") ? (v as AssignmentKind) : "");

type Confirm =
  | { kind: "delete"; a: AssignmentStaffSummaryOut }
  | { kind: "unpublish"; a: AssignmentStaffSummaryOut }
  | { kind: "unrelease"; a: AssignmentStaffSummaryOut };

export function StaffAssignmentList() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const isTeacher = course.my_enrollment.role === "teacher";
  const router = useRouter();
  const search = useSearchParams();
  const ui = useTemplateUi();
  const errorText = useAssignmentErrorText();
  const countText = useListCount();
  const categories = useCategories(course.id);
  const base = `/${lang}/courses/${course.id}`;

  const [trash, setTrash] = useState(false);
  // Phase 8c S3: filters from the URL
  const kind = asKind(search.get("kind"));
  const publishedParam = search.get("published");
  const published: "" | "yes" | "no" = publishedParam === "yes" || publishedParam === "no" ? publishedParam : "";
  const category = search.get("category") ?? "";
  const needsGrading = search.get("needs_grading") === "1";
  const listQuery = (() => {
    const p = new URLSearchParams(search.toString());
    p.delete("new");
    return p.toString();
  })();
  const here = `${base}/assignments${listQuery ? `?${listQuery}` : ""}`;
  const setFilters = (patch: Record<string, string | null>) => {
    const p = new URLSearchParams(listQuery);
    for (const [k, v] of Object.entries(patch)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    const qs = p.toString();
    router.replace(`${base}/assignments${qs ? `?${qs}` : ""}`, { scroll: false });
  };
  const [query, setQuery] = useState("");
  const [createKind, setCreateKind] = useState<AssignmentKind>("text");
  const [items, setItems] = useState<AssignmentStaffSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  // Phase 7a UX (owner Q5 default): a locked ORT course has only its exam (quiz) assignments; the server refuses others
  const ortOnly = ui.key === "ort" && ui.locked;
  const newParam = search.get("new");
  useEffect(() => {
    if (!newParam || !canEdit) return;
    if (ortOnly) { router.replace(`${base}?new=1`); return; } // the ORT exam list on the Course page
    setCreateKind(asKind(newParam) || "text"); // `?new=1` (old links): the default kind
    setCreating(true);
    router.replace(here, { scroll: false });
  }, [newParam, canEdit, ortOnly, router, base, here]);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAssignments(course.id, {
        deleted: trash, cursor: next, limit: 50, kind,
        published: published === "" ? undefined : published === "yes", category_id: category || undefined,
      });
      const rows = page.items as AssignmentStaffSummaryOut[];
      setItems((p) => (next ? [...p, ...rows] : rows));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, trash, kind, published, category]);
  useEffect(() => { void load(); }, [load]);

  const titleOf = useCallback(
    (a: AssignmentStaffSummaryOut) => pickLocalized(a.title, lang, course.default_language) || t("assignments.untitled"),
    [lang, course.default_language, t],
  );
  const q = query.trim().toLowerCase();
  const rows = useMemo(() => items.filter((a) => (!q || titleOf(a).toLowerCase().includes(q))
    && (!needsGrading || (a.counts?.needs_grading ?? 0) > 0)), [items, q, needsGrading, titleOf]);
  // Reordering sends the full order: only when every assignment is loaded and nothing is filtered.
  const canOrder = canEdit && !trash && !cursor && !kind && !published && !category && !q && !needsGrading;

  const run = async (id: string, fn: () => Promise<void>) => {
    setBusyId(id);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusyId(null);
    }
  };

  const setPublishedFlag = (a: AssignmentStaffSummaryOut, value: boolean) => {
    if (!value && ((a.counts?.submitted ?? 0) > 0 || (a.counts?.graded ?? 0) > 0)) { setConfirm({ kind: "unpublish", a }); return; }
    void run(a.id, async () => {
      const out = await updateAssignment(course.id, a.id, { published: value });
      setItems((p) => p.map((x) => (x.id === a.id ? { ...x, ...out } : x)));
    });
  };

  const move = (a: AssignmentStaffSummaryOut, delta: number) => {
    const i = items.findIndex((x) => x.id === a.id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= items.length) return;
    const next = items.slice();
    [next[i], next[j]] = [next[j], next[i]];
    void run(a.id, async () => {
      await reorderAssignments(course.id, next.map((x) => x.id));
      setItems(next);
    });
  };

  const release = (a: AssignmentStaffSummaryOut) => void run(a.id, async () => {
    const r = await releaseAssignmentGrades(course.id, a.id);
    toast.success(t("assignments.list.releasedN", { n: r.released }));
    await load();
  });

  const onConfirm = async () => {
    if (!confirm) return;
    const a = confirm.a;
    setBusyId(a.id);
    setActionError(null);
    try {
      if (confirm.kind === "delete") await deleteAssignment(course.id, a.id);
      else if (confirm.kind === "unpublish") await updateAssignment(course.id, a.id, { published: false });
      else {
        const r = await unreleaseAssignmentGrades(course.id, a.id);
        toast.success(t("assignments.list.unreleasedN", { n: r.unreleased }));
      }
      setConfirm(null);
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusyId(null);
    }
  };

  const onMenu = (a: AssignmentStaffSummaryOut, id: string) => {
    const i = items.findIndex((x) => x.id === a.id);
    if (id === "edit") router.push(withFrom(`${base}/assignments/${a.id}?tab=settings`, here));
    else if (id === "grade") router.push(withFrom(`${base}/assignments/${a.id}?tab=submissions`, here));
    else if (id === "builder" && a.assessment_id) router.push(withFrom(`${base}/assessments/${a.assessment_id}/edit`, here));
    else if (id === "attempts") router.push(withFrom(`${base}/assignments/${a.id}?tab=results`, here));
    else if (id === "release") release(a);
    else if (id === "unrelease") { setActionError(null); setConfirm({ kind: "unrelease", a }); }
    else if (id === "up" && i > 0) move(a, -1);
    else if (id === "down") move(a, 1);
    else if (id === "delete") { setActionError(null); setConfirm({ kind: "delete", a }); }
  };

  const menuItems = (a: AssignmentStaffSummaryOut): MenuItem[] => {
    const i = items.findIndex((x) => x.id === a.id);
    const quiz = a.kind === "quiz";
    const out: MenuItem[] = [{ id: "edit", label: t("assignments.list.edit") }];
    if (quiz) {
      out.push({ id: "builder", label: t("assignments.list.openBuilder") });
      out.push({ id: "attempts", label: t("assignments.list.attempts") });
    } else {
      out.push({ id: "grade", label: t("assignments.list.grade") });
    }
    if (a.grade_release === "manual") {
      out.push({ id: "release", label: t("assignments.list.release"), description: t("assignments.list.releaseHint") });
      out.push({ id: "unrelease", label: t("assignments.list.unrelease") });
    }
    if (canOrder) {
      out.push({ id: "up", label: t("assignments.list.moveUp"), disabled: i <= 0 });
      out.push({ id: "down", label: t("assignments.list.moveDown"), disabled: i < 0 || i >= items.length - 1 });
    }
    out.push({ id: "delete", label: t("assignments.list.delete") });
    return out;
  };

  const columns: TableColumn<AssignmentStaffSummaryOut>[] = [
    {
      key: "title", header: t("assignments.list.colTitle"), primary: true,
      cell: (a) => a.deleted_at ? <span className="break-words">{titleOf(a)}</span> : (
        <Link href={withFrom(`${base}/assignments/${a.id}`, here)} className="break-words font-semibold text-slate-900 hover:text-brand-700 hover:underline">{titleOf(a)}</Link>
      ),
    },
    { key: "kind", header: t("assignments.list.colKind"), mobilePriority: 0, cell: (a) => <KindBadge kind={a.kind} ort={a.kind === "quiz" && ui.key === "ort"} /> },
    { key: "due", header: t("assignments.list.colDue"), nowrap: true, mobilePriority: 1, cell: (a) => (a.due_at ? fmtShortDateTime(a.due_at, lang) : "—") },
    { key: "points", header: t("assignments.list.colPoints"), align: "right", mobilePriority: 3, hideOnMobile: false, cell: (a) => fmtPts(a.points_possible) || "—" },
    {
      key: "progress", header: t("assignments.list.colProgress"), mobilePriority: 2,
      cell: (a) => a.counts ? t("assignments.list.counts", { submitted: a.counts.submitted, graded: a.counts.graded }) : "—",
    },
    {
      key: "published", header: t("assignments.list.colPublished"), mobilePriority: 4,
      cell: (a) => {
        if (a.deleted_at) return <Badge tone="neutral">{t("assignments.list.deleted")}</Badge>;
        if (a.kind === "quiz" || !canEdit) {
          return <Badge tone={a.published ? "success" : "neutral"}>{a.published ? t("assignments.list.publishedBadge") : t("assignments.list.draftBadge")}</Badge>;
        }
        return (
          <Switch label={<><span className="sr-only">{titleOf(a)}: </span>{a.published ? t("assignments.list.publishedBadge") : t("assignments.list.draftBadge")}</>}
            checked={a.published} busy={busyId === a.id} onChange={(v) => setPublishedFlag(a, v)} containerClassName="min-w-[7rem]" />
        );
      },
    },
    ...(canEdit ? [{
      key: "actions", header: "", actions: true, align: "right" as const,
      cell: (a: AssignmentStaffSummaryOut) => a.deleted_at ? (
        <Button variant="secondary" size="sm" loading={busyId === a.id} onClick={() => void run(a.id, async () => { await restoreAssignment(course.id, a.id); await load(); })}>
          {t("assignments.list.restore")}<span className="sr-only">: {titleOf(a)}</span>
        </Button>
      ) : (
        <MenuButton variant="secondary" size="sm" disabled={busyId === a.id}
          label={<>{t("assignments.list.actions")}<span className="sr-only">: {titleOf(a)}</span></>}
          items={menuItems(a)} onSelect={(id) => onMenu(a, id)} />
      ),
    }] : []),
  ];

  const create = canEdit && !trash && !ortOnly ? <Button onClick={() => { setCreateKind("text"); setCreating(true); }}>{t("assignments.list.create")}</Button> : undefined;
  const filtered = !!(kind || published || category || q || needsGrading);
  const confirmTitle = confirm?.kind === "delete" ? t("assignments.list.deleteTitle")
    : confirm?.kind === "unpublish" ? t("assignments.list.unpublishTitle") : t("assignments.list.unreleaseTitle");
  const confirmEffect = confirm?.kind === "delete" ? (confirm.a.kind === "quiz" ? t("assignments.list.deleteQuizBody") : t("assignments.list.deleteBody"))
    : confirm?.kind === "unpublish" ? t("assignments.list.unpublishBody") : t("assignments.list.unreleaseBody");
  const confirmLabel = confirm?.kind === "delete" ? t("assignments.list.delete")
    : confirm?.kind === "unpublish" ? t("assignments.list.unpublish") : t("assignments.list.unrelease");

  return (
    <div className="space-y-4">
      <PageHeader title={t("assignments.list.title")} className="mb-2"
        description={ui.key === "ort" ? t("assignments.list.ortHint") : t("assignments.list.subtitle")}
        secondaryActions={canEdit ? <Button variant="secondary" onClick={() => { setTrash((s) => !s); setCursor(null); }}>
          {trash ? t("assignments.list.hideTrash") : t("assignments.list.showTrash")}</Button> : undefined}
        primaryAction={create} />
      {!isTeacher && canEdit && <p className="text-sm text-slate-600">{t("assignments.list.assistantNote")}</p>}
      {!confirm && <AssignmentError error={actionError} />}
      <Table<AssignmentStaffSummaryOut>
        caption={trash ? t("assignments.list.trashCaption") : t("assignments.list.caption")}
        rows={rows}
        rowKey={(a) => a.id}
        columns={columns}
        loading={loading}
        countText={!loading && !error && rows.length > 0 ? countText(rows.length, !!cursor) : undefined}
        search={(
          <FilterBar search={{ value: query, onChange: setQuery, label: t("assignments.list.search") }}
            canReset={filtered} onReset={() => { setQuery(""); setFilters({ kind: null, published: null, category: null, needs_grading: null }); }}>
            <Select label={t("assignments.list.filterKind")} value={kind} onChange={(e) => setFilters({ kind: e.target.value || null })}
              options={[{ value: "", label: t("assignments.list.allKinds") }, ...KINDS.map((k) => ({ value: k, label: t(`assignments.kinds.${k}`) }))]} />
            {!trash && (
              <Select label={t("assignments.list.filterPublished")} value={published} onChange={(e) => setFilters({ published: e.target.value || null })}
                options={[{ value: "", label: t("assignments.list.allStates") }, { value: "yes", label: t("assignments.list.publishedBadge") }, { value: "no", label: t("assignments.list.draftBadge") }]} />
            )}
            {categories.length > 0 && (
              <Select label={t("assignments.list.filterCategory")} value={category} onChange={(e) => setFilters({ category: e.target.value || null })}
                options={[{ value: "", label: t("assignments.list.allCategories") }, ...categories.map((c) => ({ value: c.id, label: pickLocalized(c.title, lang, course.default_language) || "—" }))]} />
            )}
            {!trash && (
              <Checkbox label={t("assignments.page.filterNeedsGrading")} checked={needsGrading} containerClassName="sm:self-end sm:pb-2"
                onChange={(e) => setFilters({ needs_grading: e.target.checked ? "1" : null })} />
            )}
          </FilterBar>
        )}
        error={error ? <AssignmentError error={error} onRetry={() => void load()} /> : undefined}
        empty={(
          <EmptyState icon={<ClipboardList />}
            title={filtered ? t("assignments.list.emptyFiltered") : trash ? t("assignments.list.emptyTrash") : t("assignments.list.empty")}
            description={filtered || trash ? undefined : t("assignments.list.emptyHint")}
            action={filtered || trash ? undefined : create} />
        )}
        pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }}
      />
      <AssignmentEditorDialog open={creating} initialKind={createKind} onCancel={() => setCreating(false)}
        onCreated={(a) => {
          setCreating(false);
          router.push(a.kind === "quiz" && a.assessment_id
            ? withFrom(`${base}/assessments/${a.assessment_id}/edit`, here)
            : withFrom(`${base}/assignments/${a.id}?tab=settings`, here));
        }} />
      <ConfirmDialog open={!!confirm} tone={confirm?.kind === "delete" || confirm?.kind === "unrelease" ? "danger" : "primary"}
        busy={!!confirm && busyId === confirm.a.id} title={confirmTitle} object={confirm ? titleOf(confirm.a) : undefined}
        effect={confirmEffect} confirmLabel={confirmLabel} onConfirm={() => void onConfirm()} onCancel={() => setConfirm(null)}
        error={actionError ? errorText(actionError) : undefined} />
    </div>
  );
}
