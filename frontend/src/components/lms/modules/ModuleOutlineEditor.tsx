"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1): the teacher's module outline. Writes reload the outline (one document, design
// 2.3). Warnings are badges with text.
// Phase 8c S2 (PHASE_8C_DESIGN §3.2, §3.3, §3.6): the outline of the teacher Course page. `embedded` drops the page
// header for a small toolbar ("New module", "Expand all / Collapse all", "⋯" with student progress, course-wide
// re-apply and the deleted modules). Module cards collapse (state in sessionStorage per course) and carry
// `id="m-{moduleId}"` (the `from` fragment of every object opened from here). Lighter controls: a publish icon toggle
// and one "⋯" menu per module and per item (the Move entries are the keyboard, phone and screen-reader path); native
// HTML5 drag and drop on desktop pointers (≥ lg) with optimistic reorder and a revert on error; a grouped "+ Add" menu
// per module (Content: page, file, link, header; Assessment: quiz, or the ORT exam in ORT courses, and assignment).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ChevronRight, CircleCheck, CircleDashed, GripVertical, Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import {
  addItem, clearRequirement, createModule, deleteItem, deleteModule, getModules, moveItem, reapplyCourse, reapplyModule, reorderItems,
  reorderModules, restoreModule, setPrerequisites, setRequirement, updateItem, updateModule,
} from "@/lib/lms/modules";
import type { ItemStaffOut, ModuleStaffOut, ModulesStaffOut, ModuleWarningOut } from "@/lib/lms/modulesTypes";
import { withFrom } from "@/lib/lms/nav";
import { quizAssignmentId } from "@/lib/lms/quizAssignmentId";
import { templateUi } from "@/lib/lms/templates";
import { duplicateModule } from "@/lib/lms/unsorted";
import { useCourse } from "@/components/lms/CourseContext";
import {
  Badge, Button, ConfirmDialog, EmptyState, ErrorState, LoadingState, PageHeader, cn, focusRing, toast,
} from "@/components/ui";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { CreateAssessmentDialog } from "@/components/lms/assessments/CreateAssessmentDialog";
import { ItemKindIcon, useItemKindText, useModuleErrorText, useRequirementText } from "./moduleUi";
import { ItemEditDialog, ModuleSettingsDialog, MoveItemDialog, PrerequisiteDialog, RequirementDialog, type ModuleSettingsValue } from "./OutlineDialogs";
import { AddItemDialog, moduleAnchor, type AddKind } from "./AddItemDialog";
import { OutlineMenu, type MenuGroup } from "./OutlineMenu";
import { ProgressDrawer } from "./ProgressDrawer";

type DialogState =
  | null
  | { kind: "newModule" }
  | { kind: "settings"; module: ModuleStaffOut }
  | { kind: "prereq"; module: ModuleStaffOut }
  | { kind: "deleteModule"; module: ModuleStaffOut }
  | { kind: "reapply"; module: ModuleStaffOut | null }
  | { kind: "addItem"; module: ModuleStaffOut; initialKind?: AddKind }
  | { kind: "ortExam"; module: ModuleStaffOut }
  | { kind: "editItem"; item: ItemStaffOut }
  | { kind: "requirement"; item: ItemStaffOut }
  | { kind: "moveItem"; item: ItemStaffOut }
  | { kind: "deleteItem"; item: ItemStaffOut }
  | { kind: "progress" }
  | { kind: "publishWarn"; module: ModuleStaffOut; names: string };

type DragState = null | { type: "module"; id: string } | { type: "item"; id: string; moduleId: string };

function move<T>(list: T[], from: number, to: number): T[] {
  const next = [...list];
  const [x] = next.splice(from, 1);
  next.splice(to, 0, x);
  return next;
}

function Warnings({ warnings }: { warnings: ModuleWarningOut[] }) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;
  const codes = Array.from(new Set(warnings.map((w) => w.code)));
  return (
    <span className="flex flex-wrap gap-1.5">
      {codes.map((c) => <Badge key={c} tone="warning">{t(`modules.warnings.${c}`)}</Badge>)}
    </span>
  );
}

/** Phase 8c S2 (§3.6): published = filled green check, draft = dashed circle (shape differs, not only color). */
function PublishToggle({ published, name, busy, disabled, onToggle }: {
  published: boolean; name: string; busy: boolean; disabled?: boolean; onToggle: () => void;
}) {
  const { t } = useTranslation();
  const tip = published ? t("modules.editor.publishedIcon") : t("modules.editor.draftIcon");
  return (
    <button type="button" aria-pressed={published} aria-label={t("modules.editor.publishToggle", { title: name })} title={tip}
      aria-busy={busy || undefined} disabled={disabled || busy} onClick={onToggle}
      className={cn(
        "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60",
        focusRing,
      )}>
      {published
        ? <CircleCheck aria-hidden="true" className="h-6 w-6 fill-success-600 text-white" />
        : <CircleDashed aria-hidden="true" className="h-6 w-6 text-slate-500" />}
    </button>
  );
}

/** Drag handle for pointer devices (≥ lg). Hidden from assistive tech: the "⋯" menu's Move entries do the same. */
function DragHandle({ label, onStart, onEnd }: { label: string; onStart: (e: React.DragEvent) => void; onEnd: () => void }) {
  return (
    <span draggable aria-hidden="true" title={label} onDragStart={onStart} onDragEnd={onEnd}
      className="hidden h-11 w-6 shrink-0 cursor-grab items-center justify-center text-slate-400 hover:text-slate-700 active:cursor-grabbing lg:inline-flex">
      <GripVertical className="h-5 w-5" />
    </span>
  );
}

const REQ_IGNORED = "requirement_on_unpublished_target";
/** 8a UX M1: items whose requirement does not count because their target (for example a quiz) is still a draft. */
const ignoredReqItems = (m: ModuleStaffOut) => m.items.filter((i) => i.warnings.some((w) => w.code === REQ_IGNORED));

const collapsedKey = (courseId: string) => `outline.collapsed:${courseId}`;
function readCollapsed(courseId: string): string[] {
  try {
    const raw = window.sessionStorage.getItem(collapsedKey(courseId));
    const v = raw ? JSON.parse(raw) : [];
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export interface ModuleOutlineEditorProps {
  /** Phase 8c S2: inside the Course page (no page header; a toolbar instead). */
  embedded?: boolean;
  /** Changing it reloads the outline (an unsorted target was placed in a module). */
  refreshKey?: number;
  /** After every successful write (the Course page refreshes the To do panel and the Unsorted group). */
  onChanged?: () => void;
  /** The live modules after each load (the Unsorted group's "Move to module…" lists them). */
  onModules?: (modules: ModuleStaffOut[]) => void;
  /** Rendered after the live modules (the Unsorted group). */
  afterModules?: React.ReactNode;
  /** Empty course: "Add existing items" (opens the Unsorted group). */
  onAddExisting?: () => void;
}

export function ModuleOutlineEditor({ embedded = false, refreshKey = 0, onChanged, onModules, afterModules, onAddExisting }: ModuleOutlineEditorProps) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const kindText = useItemKindText();
  const reqText = useRequirementText();
  const base = `/${lang}/courses/${course.id}`;
  const langs = { languages: course.languages, defaultLanguage: course.default_language };
  const canEdit = course.status !== "concluded";
  const ui = templateUi(course);
  const ortCourse = ui.locked && ui.key === "ort";
  const [data, setData] = useState<ModulesStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [showDeleted, setShowDeleted] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [drag, setDrag] = useState<DragState>(null);
  const [over, setOver] = useState<string | null>(null);
  const hashDone = useRef(false);
  const onModulesRef = useRef(onModules);
  onModulesRef.current = onModules;

  useEffect(() => { setCollapsed(readCollapsed(course.id)); }, [course.id]);
  const saveCollapsed = (next: string[]) => {
    setCollapsed(next);
    try { window.sessionStorage.setItem(collapsedKey(course.id), JSON.stringify(next)); } catch { /* storage unavailable */ }
  };
  const toggleCollapsed = (id: string) => saveCollapsed(collapsed.includes(id) ? collapsed.filter((x) => x !== id) : [...collapsed, id]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = (await getModules(course.id, { deleted: showDeleted })) as ModulesStaffOut;
      const modules = [...(out.modules ?? [])].sort((a, b) => a.position - b.position);
      setData({ modules });
      onModulesRef.current?.(modules.filter((m) => !m.deleted_at));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, showDeleted]);
  useEffect(() => { void load(); }, [load, refreshKey]);

  const live = useMemo(() => (data?.modules ?? []).filter((m) => !m.deleted_at), [data]);
  const deleted = useMemo(() => (data?.modules ?? []).filter((m) => m.deleted_at), [data]);
  const moduleName = (m: ModuleStaffOut) => pickLocalized(m.title, lang, course.default_language) || t("modules.untitledModule");
  const itemName = (i: ItemStaffOut) =>
    pickLocalized(i.title_override, lang, course.default_language) || pickLocalized(i.target?.title, lang, course.default_language)
    || i.url || t("modules.untitledItem");
  const sortedItems = (m: ModuleStaffOut) => [...m.items].sort((a, b) => a.position - b.position);

  // `#m-{id}` (Back from an object, the To do "unpublished modules" link): expand that module and scroll to it
  const revealHash = useCallback(() => {
    const id = window.location.hash.startsWith("#m-") ? window.location.hash.slice(3) : "";
    if (!id) return;
    setCollapsed((prev) => {
      if (!prev.includes(id)) return prev;
      const next = prev.filter((x) => x !== id);
      try { window.sessionStorage.setItem(collapsedKey(course.id), JSON.stringify(next)); } catch { /* storage unavailable */ }
      return next;
    });
    window.requestAnimationFrame(() => document.getElementById(`m-${id}`)?.scrollIntoView({ block: "start" }));
  }, [course.id]);
  useEffect(() => {
    if (!data || hashDone.current) return;
    hashDone.current = true;
    revealHash();
  }, [data, revealHash]);
  useEffect(() => {
    window.addEventListener("hashchange", revealHash);
    return () => window.removeEventListener("hashchange", revealHash);
  }, [revealHash]);

  const closeDialog = () => { setDialog(null); setDialogError(null); };
  const ignoredNames = (m: ModuleStaffOut) => ignoredReqItems(m).map(itemName).join(", ");

  /** Runs a write; `inDialog`: keep the dialog open and show the error in it. */
  const run = async (key: string, fn: () => Promise<unknown>, opts: { inDialog?: boolean; success?: string } = {}) => {
    setBusy(key);
    setDialogError(null);
    try {
      await fn();
      if (opts.inDialog) closeDialog();
      if (opts.success) toast.success(opts.success);
      await load();
      onChanged?.();
      return true;
    } catch (e) {
      if (opts.inDialog) setDialogError(errorText(e));
      else toast.error(errorText(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  /** Optimistic reorder (drag and drop): show the new order at once, write, reload; on error reload and say why. */
  const optimistic = async (next: ModuleStaffOut[], key: string, fn: () => Promise<unknown>) => {
    const before = data;
    setData((d) => (d ? { modules: [...next, ...d.modules.filter((m) => m.deleted_at)] } : d));
    const ok = await run(key, fn);
    if (!ok && before) setData(before);
  };

  const saveSettings = (v: ModuleSettingsValue, module: ModuleStaffOut | null) => run("settings", () => (module
    ? updateModule(course.id, module.id, { title: v.title, unlock_at: v.unlock_at, sequential: v.sequential, completion_mode: v.completion_mode })
    : createModule(course.id, v)), { inDialog: true });

  const moveModuleTo = (from: number, to: number) => {
    if (from === to || to < 0 || to >= live.length) return;
    const next = move(live, from, to);
    void optimistic(next, `mm-${live[from].id}`, () => reorderModules(course.id, next.map((m) => m.id)));
  };
  const moveItemTo = (module: ModuleStaffOut, from: number, to: number) => {
    const items = sortedItems(module);
    if (from === to || to < 0 || to >= items.length) return;
    const nextItems = move(items, from, to).map((it, i) => ({ ...it, position: i + 1 }));
    const next = live.map((m) => (m.id === module.id ? { ...m, items: nextItems } : m));
    void optimistic(next, `mi-${items[from].id}`, () => reorderItems(course.id, module.id, nextItems.map((i) => i.id)));
  };
  /** Drop an item into another module before `beforeIndex` (or at the end). */
  const moveItemAcross = (item: ItemStaffOut, target: ModuleStaffOut, beforeIndex: number | null) => {
    const targetItems = sortedItems(target);
    const position = beforeIndex === null ? targetItems.length + 1 : beforeIndex + 1;
    const moved = { ...item, module_id: target.id };
    const nextTarget = [...targetItems];
    nextTarget.splice(position - 1, 0, moved);
    const next = live.map((m) => {
      if (m.id === item.module_id) return { ...m, items: m.items.filter((i) => i.id !== item.id) };
      if (m.id === target.id) return { ...m, items: nextTarget.map((it, i) => ({ ...it, position: i + 1 })) };
      return m;
    });
    void optimistic(next, `mv-${item.id}`, () => moveItem(course.id, item.module_id, item.id, target.id, position));
  };

  // ---- native drag and drop (desktop pointers; the "⋯" Move entries are the alternative) ----
  const startDrag = (state: NonNullable<DragState>, elId: string) => (e: React.DragEvent) => {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", state.id);
    const el = document.getElementById(elId);
    if (el) e.dataTransfer.setDragImage(el, 24, 24);
    setDrag(state);
  };
  const endDrag = () => { setDrag(null); setOver(null); };
  const onModuleDragOver = (m: ModuleStaffOut) => (e: React.DragEvent) => {
    if (!drag) return;
    if (drag.type === "module" && drag.id !== m.id) { e.preventDefault(); setOver(`m:${m.id}`); }
    else if (drag.type === "item") { e.preventDefault(); setOver(`end:${m.id}`); }
  };
  const onModuleDrop = (m: ModuleStaffOut, mi: number) => (e: React.DragEvent) => {
    if (!drag) return;
    e.preventDefault();
    const d = drag;
    endDrag();
    if (d.type === "module") {
      const from = live.findIndex((x) => x.id === d.id);
      if (from >= 0) moveModuleTo(from, mi);
      return;
    }
    // an item dropped on a module card (not on a row): to the end of that module
    const src = live.find((x) => x.id === d.moduleId);
    const item = src?.items.find((i) => i.id === d.id);
    if (!src || !item) return;
    if (src.id === m.id) moveItemTo(m, sortedItems(m).findIndex((i) => i.id === item.id), m.items.length - 1);
    else moveItemAcross(item, m, null);
  };
  const onItemDragOver = (it: ItemStaffOut) => (e: React.DragEvent) => {
    if (drag?.type !== "item" || drag.id === it.id) return;
    e.preventDefault();
    e.stopPropagation();
    setOver(`i:${it.id}`);
  };
  const onItemDrop = (m: ModuleStaffOut, ii: number) => (e: React.DragEvent) => {
    if (drag?.type !== "item") return;
    e.preventDefault();
    e.stopPropagation();
    const d = drag;
    endDrag();
    const src = live.find((x) => x.id === d.moduleId);
    const item = src?.items.find((i) => i.id === d.id);
    if (!src || !item) return;
    if (src.id === m.id) moveItemTo(m, sortedItems(m).findIndex((i) => i.id === item.id), ii);
    else moveItemAcross(item, m, ii);
  };

  const itemHref = (item: ItemStaffOut): string | null => {
    const from = moduleAnchor(base, item.module_id);
    if (item.kind === "page" && item.page_id) return withFrom(`${base}/pages/${item.page_id}`, from);
    if (item.kind === "file") return `${base}/files`;
    if (item.kind === "assignment" && item.target?.assignment_kind === "quiz" && item.target.assessment_id) {
      return withFrom(`${base}/assessments/${item.target.assessment_id}/edit`, from);
    }
    if (item.kind === "assignment" && item.assignment_id) return withFrom(`${base}/assignments/${item.assignment_id}`, from);
    return null;
  };

  const onModuleMenu = (m: ModuleStaffOut, mi: number, id: string) => {
    setDialogError(null);
    if (id === "settings") setDialog({ kind: "settings", module: m });
    else if (id === "prereq") setDialog({ kind: "prereq", module: m });
    else if (id === "duplicate") void run(`dup-${m.id}`, () => duplicateModule(course.id, m.id), { success: t("modules.editor.duplicated") });
    else if (id === "up") moveModuleTo(mi, mi - 1);
    else if (id === "down") moveModuleTo(mi, mi + 1);
    else if (id === "reapply") setDialog({ kind: "reapply", module: m });
    else if (id === "progress") setDialog({ kind: "progress" });
    else if (id === "delete") setDialog({ kind: "deleteModule", module: m });
  };
  const onItemMenu = (m: ModuleStaffOut, item: ItemStaffOut, ii: number, id: string) => {
    setDialogError(null);
    if (id === "edit") setDialog({ kind: "editItem", item });
    else if (id === "requirement") setDialog({ kind: "requirement", item });
    else if (id === "up") moveItemTo(m, ii, ii - 1);
    else if (id === "down") moveItemTo(m, ii, ii + 1);
    else if (id === "move") setDialog({ kind: "moveItem", item });
    else if (id === "delete") setDialog({ kind: "deleteItem", item });
    else if (id === "open") {
      const href = itemHref(item);
      if (href) router.push(href);
      else if (item.url) window.open(item.url, "_blank", "noopener,noreferrer");
    }
  };
  const onAdd = (m: ModuleStaffOut, id: string) => {
    setDialogError(null);
    if (id === "ortExam") setDialog({ kind: "ortExam", module: m });
    else setDialog({ kind: "addItem", module: m, initialKind: id as AddKind });
  };

  const addGroups: MenuGroup[] = [
    {
      id: "content", heading: t("coursePage.addGroups.content"), items: [
        { id: "page", label: t("coursePage.addItems.page"), icon: <ItemKindIcon kind="page" /> },
        { id: "file", label: t("coursePage.addItems.file"), icon: <ItemKindIcon kind="file" /> },
        { id: "url", label: t("coursePage.addItems.link"), icon: <ItemKindIcon kind="url" /> },
        { id: "header", label: t("coursePage.addItems.header"), icon: <ItemKindIcon kind="header" /> },
      ],
    },
    {
      id: "assessment", heading: t("coursePage.addGroups.assessment"), items: [
        ortCourse
          ? { id: "ortExam", label: t("coursePage.addItems.ortExam"), icon: <ItemKindIcon kind="assignment" assignmentKind="quiz" /> }
          : { id: "quiz", label: t("coursePage.addItems.quiz"), icon: <ItemKindIcon kind="assignment" assignmentKind="quiz" /> },
        { id: "assignment", label: t("coursePage.addItems.assignment"), icon: <ItemKindIcon kind="assignment" assignmentKind="text" /> },
      ],
    },
  ];
  const addMenu = (m: ModuleStaffOut, opts: { fullWidth?: boolean; className?: string } = {}) => (
    <OutlineMenu trigger="button" variant="secondary" label={t("modules.editor.addItem")} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}
      sheetTitle={t("coursePage.add", { title: moduleName(m) })} groups={addGroups} onSelect={(id) => onAdd(m, id)}
      fullWidth={opts.fullWidth} className={opts.className} />
  );

  const allCollapsed = live.length > 0 && live.every((m) => collapsed.includes(m.id));
  const moreGroups: MenuGroup[] = [{
    id: "more", items: [
      { id: "progress", label: t("modules.progress.open") },
      ...(canEdit ? [{ id: "reapply", label: t("modules.editor.reapplyCourse"), description: t("modules.editor.reapplyWholeCourse") }] : []),
      { id: "deleted", label: showDeleted ? t("coursePage.hideDeleted") : t("modules.editor.showDeleted") },
    ],
  }];
  const onMore = (id: string) => {
    if (id === "progress") setDialog({ kind: "progress" });
    else if (id === "reapply") { setDialogError(null); setDialog({ kind: "reapply", module: null }); }
    else if (id === "deleted") setShowDeleted((s) => !s);
  };

  const newModuleButton = (
    <Button leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} onClick={() => { setDialogError(null); setDialog({ kind: "newModule" }); }}>
      {t("modules.editor.newModule")}
    </Button>
  );
  const header = embedded ? (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-xl font-semibold leading-7 text-slate-900">{t("modules.editor.title")}</h2>
      <div className="flex flex-wrap items-center gap-1 sm:gap-2">
        {live.length > 1 && (
          <Button variant="link" size="sm" onClick={() => saveCollapsed(allCollapsed ? [] : live.map((m) => m.id))}>
            {allCollapsed ? t("coursePage.expandAll") : t("coursePage.collapseAll")}
          </Button>
        )}
        {(live.length > 0 || deleted.length > 0 || showDeleted) && (
          <OutlineMenu label={t("coursePage.moreActions")} groups={moreGroups} onSelect={onMore} />
        )}
        {/* an empty course shows "New module" in its empty state */}
        {canEdit && (live.length > 0 || deleted.length > 0) && newModuleButton}
      </div>
    </div>
  ) : (
    <PageHeader title={t("modules.editor.title")} description={t("modules.editor.description")} className="mb-2"
      primaryAction={canEdit ? newModuleButton : undefined}
      secondaryActions={live.length > 0 || deleted.length > 0 || showDeleted
        ? <OutlineMenu label={t("coursePage.moreActions")} groups={moreGroups} onSelect={onMore} /> : undefined} />
  );

  const H = embedded ? "h3" : "h2";
  let body: React.ReactNode;
  if (error && !data) body = <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  else if (!data) body = <LoadingState rows={3} />;
  else if (live.length === 0 && deleted.length === 0) {
    body = (
      <EmptyState title={t("modules.editor.emptyTitle")} description={t("modules.editor.emptyBody")}
        action={canEdit ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-center">
            <Button onClick={() => setDialog({ kind: "newModule" })} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{t("modules.editor.newModule")}</Button>
            {onAddExisting && <Button variant="secondary" onClick={onAddExisting}>{t("coursePage.addExisting")}</Button>}
          </div>
        ) : undefined} />
    );
  } else {
    body = (
      <div className="space-y-4">
        {live.map((m, mi) => {
          const items = sortedItems(m);
          const prereqNames = m.prerequisites.map((id) => live.find((x) => x.id === id)).filter(Boolean).map((x) => moduleName(x!));
          const headingId = `om-${m.id}`;
          const itemsId = `omi-${m.id}`;
          const isCollapsed = collapsed.includes(m.id);
          const name = moduleName(m);
          const dropTarget = over === `m:${m.id}` || over === `end:${m.id}`;
          return (
            <section key={m.id} id={`m-${m.id}`} aria-labelledby={headingId}
              onDragOver={canEdit ? onModuleDragOver(m) : undefined} onDrop={canEdit ? onModuleDrop(m, mi) : undefined}
              className={cn("scroll-mt-24 rounded-2xl border bg-white shadow-sm",
                dropTarget ? "border-brand-500 ring-2 ring-brand-200" : "border-slate-200",
                drag?.type === "module" && drag.id === m.id && "opacity-60")}>
              <header className="space-y-2 px-2 py-2 sm:px-3">
                <div className="flex items-start gap-1">
                  {canEdit && (
                    <DragHandle label={t("modules.editor.dragHandle", { title: name })} onEnd={endDrag}
                      onStart={startDrag({ type: "module", id: m.id }, `m-${m.id}`)} />
                  )}
                  <button type="button" aria-expanded={!isCollapsed} aria-controls={itemsId} onClick={() => toggleCollapsed(m.id)}
                    aria-label={t("coursePage.toggleModule", { title: name })} title={t("coursePage.toggleModule", { title: name })}
                    className={cn("inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-600 hover:bg-slate-100", focusRing)}>
                    <ChevronRight aria-hidden="true" className={cn("h-5 w-5 transition-transform", !isCollapsed && "rotate-90")} />
                  </button>
                  <div className="min-w-0 flex-1 py-2">
                    <H id={headingId} className="break-words text-lg font-semibold leading-7 text-slate-900">{name}</H>
                    <p className="mt-0.5 flex flex-wrap gap-x-3 text-sm leading-6 text-slate-600">
                      {!m.published && <span>{t("modules.editor.draft")}</span>}
                      {m.published && !canEdit && <span>{t("modules.editor.published")}</span>}
                      {isCollapsed && <span>{t("coursePage.itemCount", { n: m.items.length })}</span>}
                      {m.unlock_at && <span>{t("modules.reason.unlockAt", { date: fmtShortDateTime(m.unlock_at, lang) })}</span>}
                      {m.sequential && <span>{t("modules.sequentialHint")}</span>}
                      {m.completion_mode === "any" && <span>{t("modules.completionAny")}</span>}
                      {prereqNames.length > 0 && <span className="break-words">{t("modules.editor.after", { titles: prereqNames.join(", ") })}</span>}
                    </p>
                  </div>
                  {canEdit && (
                    <div className="flex shrink-0 items-center gap-1">
                      <PublishToggle published={m.published} name={name} busy={busy === `pub-${m.id}`}
                        onToggle={() => {
                          // 8a UX M1: publishing a module whose requirement points at a draft asks first
                          if (!m.published && ignoredReqItems(m).length > 0) { setDialogError(null); setDialog({ kind: "publishWarn", module: m, names: ignoredNames(m) }); return; }
                          void run(`pub-${m.id}`, () => updateModule(course.id, m.id, { published: !m.published }));
                        }} />
                      {addMenu(m, { className: "hidden sm:block" })}
                      <OutlineMenu label={t("modules.editor.actions")} onSelect={(id) => onModuleMenu(m, mi, id)} groups={[{
                        id: "module", items: [
                          { id: "settings", label: t("modules.editor.editSettings") },
                          { id: "prereq", label: t("modules.editor.prerequisites"), disabled: mi === 0 },
                          { id: "duplicate", label: t("modules.editor.duplicate"), disabled: !!busy },
                          { id: "up", label: t("modules.editor.moveUp"), disabled: mi === 0 || !!busy },
                          { id: "down", label: t("modules.editor.moveDown"), disabled: mi === live.length - 1 || !!busy },
                          { id: "reapply", label: t("modules.editor.reapply") },
                          { id: "progress", label: t("modules.progress.open") },
                          { id: "delete", label: t("modules.editor.delete") },
                        ],
                      }]} />
                    </div>
                  )}
                </div>
                <div className="space-y-2 pl-1 empty:hidden sm:pl-12">
                  {m.warnings.length > 0 && <Warnings warnings={m.warnings} />}
                  {m.published && ignoredReqItems(m).length > 0 && (
                    <div role="note" className="flex items-start gap-2 rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm leading-6 text-warning-900">
                      <AlertTriangle aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-warning-700" />
                      <div className="min-w-0 space-y-1 break-words">
                        <Badge tone="warning">{t("modules.warnings.requirementIgnoredTitle")}</Badge>
                        <p>{t("modules.warnings.requirementIgnoredBody", { item: ignoredNames(m) })}</p>
                      </div>
                    </div>
                  )}
                </div>
              </header>
              <div id={itemsId} hidden={isCollapsed} className="border-t border-slate-100">
                {items.length === 0 ? (
                  <p className="px-4 py-4 text-base text-slate-600 sm:px-6 sm:text-sm">{t("modules.editor.noItems")}</p>
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {items.map((it, ii) => {
                      const pad = ["", "sm:pl-8", "sm:pl-12", "sm:pl-16"][Math.min(it.indent, 3)];
                      const iname = itemName(it);
                      const href = it.kind !== "header" ? itemHref(it) : null;
                      const titleCls = cn("break-words text-base leading-6 sm:text-sm",
                        it.kind === "header" ? "font-semibold uppercase tracking-wide text-slate-700" : "font-medium text-slate-900");
                      return (
                        <li key={it.id} id={`mi-${it.id}`} onDragOver={canEdit ? onItemDragOver(it) : undefined} onDrop={canEdit ? onItemDrop(m, ii) : undefined}
                          className={cn("flex items-start gap-1 px-2 py-1.5 sm:px-3", pad,
                            over === `i:${it.id}` && "shadow-[inset_0_2px_0_0_theme(colors.brand.500)]",
                            drag?.type === "item" && drag.id === it.id && "opacity-60")}>
                          {canEdit && (
                            <DragHandle label={t("modules.editor.dragHandle", { title: iname })} onEnd={endDrag}
                              onStart={startDrag({ type: "item", id: it.id, moduleId: m.id }, `mi-${it.id}`)} />
                          )}
                          <ItemKindIcon kind={it.kind} assignmentKind={it.target?.assignment_kind} className="mt-3 h-5 w-5 text-slate-500" />
                          <div className="min-w-0 flex-1 py-2 pl-2">
                            {href ? (
                              <Link href={href} className={cn(titleCls, "rounded hover:text-brand-700 hover:underline", focusRing)}>{iname}</Link>
                            ) : it.kind === "url" && it.url ? (
                              <a href={it.url} target="_blank" rel="noopener noreferrer" className={cn(titleCls, "rounded hover:text-brand-700 hover:underline", focusRing)}>
                                {iname}<span className="sr-only"> {t("modules.opensNewTab")}</span>
                              </a>
                            ) : (
                              <p className={titleCls}>{iname}</p>
                            )}
                            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm leading-6 text-slate-600">
                              {it.kind !== "header" && <span>{kindText(it.kind, it.target?.assignment_kind)}</span>}
                              {!it.published && <span>{t("modules.editor.draft")}</span>}
                              {it.target?.language && it.kind === "page" && <span>{t(`courses.languages.${it.target.language}`)}</span>}
                              {it.requirement && (canEdit ? (
                                <button type="button" onClick={() => onItemMenu(m, it, ii, "requirement")}
                                  className={cn("min-h-11 rounded text-left font-medium text-brand-700 underline underline-offset-2 hover:text-brand-800 sm:min-h-0", focusRing)}>
                                  {t("modules.editor.requirement", { text: reqText(it.requirement.type, it.requirement.threshold) })}
                                </button>
                              ) : <span>{t("modules.editor.requirement", { text: reqText(it.requirement.type, it.requirement.threshold) })}</span>)}
                              <Warnings warnings={it.warnings} />
                            </p>
                          </div>
                          {canEdit && (
                            <div className="flex shrink-0 items-center gap-1">
                              <PublishToggle published={it.published} name={iname} busy={busy === `ip-${it.id}`}
                                onToggle={() => void run(`ip-${it.id}`, () => updateItem(course.id, m.id, it.id, { published: !it.published }))} />
                              <OutlineMenu label={t("modules.editor.actionsFor", { title: iname })} onSelect={(id) => onItemMenu(m, it, ii, id)} groups={[{
                                id: "item", items: [
                                  { id: "edit", label: t("modules.editor.editItem") },
                                  ...(it.kind !== "header" ? [{ id: "requirement", label: t("modules.editor.setRequirement") }] : []),
                                  { id: "up", label: t("modules.editor.moveUp"), disabled: ii === 0 || !!busy },
                                  { id: "down", label: t("modules.editor.moveDown"), disabled: ii === items.length - 1 || !!busy },
                                  ...(live.length > 1 ? [{ id: "move", label: t("modules.editor.moveTo") }] : []),
                                  ...(it.kind !== "header" ? [{ id: "open", label: it.target?.assignment_kind === "quiz" ? t("modules.editor.editQuiz") : t("modules.editor.openTarget") }] : []),
                                  { id: "delete", label: t("modules.editor.removeItem") },
                                ],
                              }]} />
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {canEdit && (
                  <div className={cn("border-t border-slate-100 px-3 py-3 sm:px-4", items.length === 0 && "sm:hidden")}>
                    {addMenu(m, { fullWidth: true, className: "sm:w-fit" })}
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    );
  }

  const d = dialog;
  return (
    <div className="space-y-4">
      {header}
      {!embedded && course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700">{t("courses.home.concludedNotice")}</p>
      )}
      {body}
      {afterModules}

      {deleted.length > 0 && (
        <section aria-labelledby="om-deleted" className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-6">
          <h2 id="om-deleted" className="text-base font-semibold text-slate-800">{t("modules.editor.deletedTitle")}</h2>
          <ul className="mt-2 divide-y divide-slate-200">
            {deleted.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="min-w-0 break-words text-base text-slate-700 sm:text-sm">{moduleName(m)}</span>
                {canEdit && (
                  <Button size="sm" variant="secondary" loading={busy === `restore-${m.id}`}
                    onClick={() => void run(`restore-${m.id}`, () => restoreModule(course.id, m.id))}>{t("modules.editor.restore")}</Button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {d?.kind === "newModule" && (
        <ModuleSettingsDialog open module={null} langs={langs} busy={busy === "settings"} error={dialogError}
          onSave={(v) => void saveSettings(v, null)} onClose={closeDialog} />
      )}
      {d?.kind === "settings" && (
        <ModuleSettingsDialog open module={d.module} langs={langs} busy={busy === "settings"} error={dialogError}
          onSave={(v) => void saveSettings(v, d.module)} onClose={closeDialog} />
      )}
      {d?.kind === "prereq" && (
        <PrerequisiteDialog open module={d.module} modules={live} defaultLang={course.default_language} busy={busy === "prereq"} error={dialogError}
          onSave={(ids) => void run("prereq", () => setPrerequisites(course.id, d.module.id, ids), { inDialog: true })} onClose={closeDialog} />
      )}
      {d?.kind === "deleteModule" && (
        <ConfirmDialog open tone="danger" busy={busy === "delete"} title={t("modules.editor.deleteModuleTitle")} object={moduleName(d.module)}
          effect={t("modules.editor.deleteModuleBody")} confirmLabel={t("modules.editor.delete")} error={dialogError ?? undefined}
          onConfirm={() => void run("delete", () => deleteModule(course.id, d.module.id), { inDialog: true })} onCancel={closeDialog} />
      )}
      {d?.kind === "reapply" && (
        <ConfirmDialog open busy={busy === "reapply"} title={t("modules.editor.reapplyTitle")}
          object={d.module ? moduleName(d.module) : t("modules.editor.reapplyWholeCourse")} effect={t("modules.editor.reapplyBody")}
          confirmLabel={t("modules.editor.reapply")} error={dialogError ?? undefined}
          onConfirm={() => {
            const target = d.module;
            void (async () => {
              setBusy("reapply");
              setDialogError(null);
              try {
                const out = target ? await reapplyModule(course.id, target.id) : await reapplyCourse(course.id);
                closeDialog();
                toast.success(t("modules.editor.reapplyDone", { n: out?.cleared_students ?? 0 }));
                await load();
              } catch (e) {
                setDialogError(errorText(e));
              } finally {
                setBusy(null);
              }
            })();
          }} onCancel={closeDialog} />
      )}
      {d?.kind === "addItem" && (
        <AddItemDialog open module={d.module} courseId={course.id} base={base} langs={langs} initialKind={d.initialKind}
          allowNewAssignment={!ortCourse}
          onAdded={() => { closeDialog(); void load(); onChanged?.(); }} onClose={closeDialog} />
      )}
      {d?.kind === "ortExam" && (
        // ORT courses: the existing create dialog with the ORT presets; the exam's quiz assignment goes into the module
        <CreateAssessmentDialog open courseId={course.id} courseLanguages={course.languages} defaultLanguage={course.default_language}
          onCancel={closeDialog}
          onCreated={(a) => {
            const target = d.module;
            closeDialog();
            void (async () => {
              try {
                await addItem(course.id, target.id, { kind: "assignment", assignment_id: quizAssignmentId(a.id), published: true });
              } catch (e) {
                toast.error(errorText(e));
              }
              router.push(withFrom(`${base}/assessments/${a.id}/edit`, moduleAnchor(base, target.id)));
            })();
          }} />
      )}
      {d?.kind === "editItem" && (
        <ItemEditDialog open item={d.item} langs={langs} busy={busy === "item"} error={dialogError}
          onSave={(v) => void run("item", () => updateItem(course.id, d.item.module_id, d.item.id, v), { inDialog: true })} onClose={closeDialog} />
      )}
      {d?.kind === "requirement" && (
        <RequirementDialog open item={d.item} itemTitle={itemName(d.item)} busy={busy === "req"} error={dialogError}
          onSave={(body) => void run("req", () => (body
            ? setRequirement(course.id, d.item.module_id, d.item.id, body)
            : d.item.requirement ? clearRequirement(course.id, d.item.module_id, d.item.id) : Promise.resolve()), { inDialog: true })}
          onClose={closeDialog} />
      )}
      {d?.kind === "moveItem" && (
        <MoveItemDialog open item={d.item} itemTitle={itemName(d.item)} modules={live} defaultLang={course.default_language} busy={busy === "move"}
          error={dialogError} onMove={(to, pos) => void run("move", () => moveItem(course.id, d.item.module_id, d.item.id, to, pos), { inDialog: true })}
          onClose={closeDialog} />
      )}
      {d?.kind === "deleteItem" && (
        <ConfirmDialog open tone="danger" busy={busy === "delItem"} title={t("modules.editor.deleteItemTitle")} object={itemName(d.item)}
          effect={t("modules.editor.deleteItemBody")} confirmLabel={t("modules.editor.removeItem")} error={dialogError ?? undefined}
          onConfirm={() => void run("delItem", () => deleteItem(course.id, d.item.module_id, d.item.id), { inDialog: true })} onCancel={closeDialog} />
      )}
      {d?.kind === "progress" && <ProgressDrawer open onClose={closeDialog} />}
      {d?.kind === "publishWarn" && (
        <ConfirmDialog open busy={busy === `pub-${d.module.id}`} title={t("modules.warnings.requirementIgnoredTitle")} object={moduleName(d.module)}
          effect={t("modules.warnings.requirementIgnoredBody", { item: d.names })} confirmLabel={t("modules.editor.publishAnyway")}
          error={dialogError ?? undefined}
          onConfirm={() => void run(`pub-${d.module.id}`, () => updateModule(course.id, d.module.id, { published: true }), { inDialog: true })}
          onCancel={closeDialog} />
      )}
    </div>
  );
}
