"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1): the teacher's module outline. Writes reload the outline (one document, design
// 2.3). Warnings are badges with text.
// Phase 8c S2 (PHASE_8C_DESIGN §3.2, §3.3, §3.6): the outline of the teacher Course page: a small toolbar ("New module",
// "⋯" with expand / collapse all, student progress, course-wide re-apply and the deleted modules). Module cards
// collapse (state in sessionStorage per course) and carry `id="m-{moduleId}"` (the `from` fragment of every object
// opened from here). A publish icon toggle and one "⋯" menu per module and per item (the Move entries are the keyboard,
// phone and screen-reader path); native HTML5 drag and drop on desktop pointers (≥ lg) with optimistic reorder and a
// revert on error.
// UX rework D (UR-4): new module, rename and most adds happen inline (Enter saves, Esc cancels). A module's "+" menu picks
// the kind; a file (and an ORT exam or assignment) keeps its dialog. Rows are one line from `sm`; details that are not
// essential sit in a tooltip and in the "⋯" menu.
// F5c (COURSE_LESSONS_DESIGN §6, §7.3): a module header shows "N уроков · 48 мин" and, on platform courses only, the Pro
// switch (gold when on; turning it on asks first). Rows get a minutes chip (pages, files, links), a requirement chip
// and ↑ ↓ buttons (keyboard path; drag stays on desktop pointers). Under each module an "add" row: Видео (a dialog with
// a YouTube / Vimeo hint), Страница, Файл, Тест, Ссылка (the existing flows) and "Ещё" with the full grouped menu.
// FB8 S2 (STAFF_UX_AUDIT §3): one "+ Добавить" menu per module instead of the add row (groups: lesson content, checks,
// more); publish is a small `Switch` (`role="switch"`), Pro a `LockToggle` (platform courses only); the drag handle is
// always visible at `lg` and sits at the row's end (↑ ↓ and the "⋯" Move entries stay the keyboard / phone path).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ChevronRight, Flag, GripVertical, Info, Plus, PlayCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { createAssignment } from "@/lib/lms/assignments";
import type { AssignmentKind } from "@/lib/lms/assignmentTypes";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import {
  addItem, clearRequirement, createModule, createQuizItem, deleteItem, deleteModule, getModules, moveItem, reapplyCourse, reapplyModule, reorderItems,
  reorderModules, restoreModule, setPrerequisites, setRequirement, updateItem, updateModule,
} from "@/lib/lms/modules";
import type { ItemStaffOut, ModuleStaffOut, ModulesStaffOut, ModuleWarningOut } from "@/lib/lms/modulesTypes";
import type { LocalizedText } from "@/lib/lms/types";
import { withFrom } from "@/lib/lms/nav";
import { createPage } from "@/lib/lms/pages";
import { parseVideo } from "@/lib/lms/video";
import { quizAssignmentId } from "@/lib/lms/quizAssignmentId";
import { templateUi } from "@/lib/lms/templates";
import { duplicateModule } from "@/lib/lms/unsorted";
import { useCourse } from "@/components/lms/CourseContext";
import {
  Badge, Button, ConfirmDialog, EmptyState, ErrorState, LoadingState, LockToggle, Switch, cn, focusRing, toast,
} from "@/components/ui";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { CreateAssessmentDialog } from "@/components/lms/assessments/CreateAssessmentDialog";
import { ItemKindIcon, useItemKindText, useModuleErrorText, useRequirementText } from "./moduleUi";
import { ItemEditDialog, ModuleSettingsDialog, MoveItemDialog, PrerequisiteDialog, RequirementDialog, type ModuleSettingsValue } from "./OutlineDialogs";
import { AddItemDialog, VideoDialog, moduleAnchor, type AddKind } from "./AddItemDialog";
import { DurationChip, MoveButtons, parseMinutes, useDurationText } from "./EditorParts";
import { InlineForm, type InlineValues } from "./InlineForm";
import { OutlineMenu, type MenuGroup } from "./OutlineMenu";
import { ProgressDrawer } from "./ProgressDrawer";

type DialogState =
  | null
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
  | { kind: "publishWarn"; module: ModuleStaffOut; names: string }
  | { kind: "video"; module: ModuleStaffOut }
  | { kind: "pro"; module: ModuleStaffOut };

/** The one inline form that is open: a new module, a rename, or an add at the end of a module. */
type InlineKind = "page" | "url" | "header" | "quiz" | "assignment";
type InlineState =
  | null
  | { type: "newModule" }
  | { type: "renameModule"; id: string }
  | { type: "renameItem"; id: string; moduleId: string }
  | { type: "add"; moduleId: string; kind: InlineKind };
const INLINE_KINDS: string[] = ["page", "url", "header", "quiz", "assignment"];
/** Assignment kinds offered inline: the kind is fixed once created, so the form asks for it. A quiz has its own entry. */
const INLINE_ASSIGNMENT_KINDS: AssignmentKind[] = ["text", "file", "none"];

/** F5c: rows with a duration (lessons); tests and headers have none (the server refuses it there). */
const LESSON_KINDS: string[] = ["page", "file", "url"];

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

/** FB8 S2 (§3): published or draft as a small switch (`role="switch"`, label "Опубликовано: {title}" for screen readers);
 * the tooltip says the state and what a click does. The row also says "Черновик" in text. */
function PublishSwitch({ published, name, busy, onToggle }: {
  published: boolean; name: string; busy: boolean; onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <span title={published ? t("modules.editor.publishedIcon") : t("modules.editor.draftIcon")} className="inline-flex shrink-0">
      <Switch size="sm" hideLabel label={t("modules.editor.publishToggle", { title: name })} checked={published} busy={busy}
        onChange={() => onToggle()} />
    </span>
  );
}

/** Drag handle for pointer devices (≥ lg), at the end of a module header or item row. Hidden from assistive tech: the
 * "⋯" menu's Move entries (and ↑ ↓ on rows) do the same. FB8 S2: always visible at `lg` (no action only on hover). */
function DragHandle({ label, onStart, onEnd }: {
  label: string; onStart: (e: React.DragEvent) => void; onEnd: () => void;
}) {
  return (
    <span draggable aria-hidden="true" title={label} onDragStart={onStart} onDragEnd={onEnd}
      className="hidden h-11 w-6 shrink-0 cursor-grab items-center justify-center text-slate-300 transition-colors hover:text-slate-600 active:cursor-grabbing lg:inline-flex">
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
  /** Changing it reloads the outline (an unsorted target was placed in a module). */
  refreshKey?: number;
  /** After every successful write (the Course page refreshes the To do panel and the Unsorted group). */
  onChanged?: () => void;
  /** The live modules after each load (the Unsorted group's "Move to module…" lists them). */
  onModules?: (modules: ModuleStaffOut[]) => void;
  /** Rendered after the live modules (the Unsorted group). */
  afterModules?: React.ReactNode;
}

export function ModuleOutlineEditor({ refreshKey = 0, onChanged, onModules, afterModules }: ModuleOutlineEditorProps) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const kindText = useItemKindText();
  const reqText = useRequirementText();
  const durationText = useDurationText();
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
  const [inline, setInline] = useState<InlineState>(null);
  const [inlineBusy, setInlineBusy] = useState(false);
  const [inlineError, setInlineError] = useState<string | null>(null);
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
      setData({ modules, is_platform_course: !!out.is_platform_course });
      onModulesRef.current?.(modules.filter((m) => !m.deleted_at));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, showDeleted]);
  useEffect(() => { void load(); }, [load, refreshKey]);

  const isPlatform = !!data?.is_platform_course;
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

  // ---- inline forms (one at a time). Text goes into the language the teacher is working in. ----
  const editLang = course.languages.includes(lang) ? lang : course.default_language;
  const openInline = (next: NonNullable<InlineState>) => { setInlineError(null); setInline(next); };
  /** Close a form; focus goes back to the control it replaced (the form's own button or the module's toggle). */
  const closeInline = (focus?: string) => {
    setInline(null);
    setInlineError(null);
    if (focus) window.requestAnimationFrame(() => document.querySelector<HTMLElement>(focus)?.focus());
  };
  const moduleFocus = (id: string) => `[aria-controls="omi-${id}"]`;
  const inlineFocus = (st: InlineState) => {
    if (!st) return undefined;
    if (st.type === "newModule") return "[data-new-module]";
    if (st.type === "renameModule") return moduleFocus(st.id);
    if (st.type === "renameItem") return `#mi-${st.id} button[aria-haspopup]`;
    return moduleFocus(st.moduleId);
  };
  const cancelInline = () => closeInline(inlineFocus(inline));
  const runInline = async (fn: () => Promise<unknown>) => {
    const focus = inlineFocus(inline);
    setInlineBusy(true);
    setInlineError(null);
    try {
      await fn();
      closeInline(focus);
      await load();
      onChanged?.();
    } catch (e) {
      setInlineError(errorText(e));
    } finally {
      setInlineBusy(false);
    }
  };
  const submitNewModule = ({ title }: InlineValues) => {
    if (!title) { setInlineError(t("modules.settings.titleRequired")); return; }
    void runInline(() => createModule(course.id, { title: { [editLang]: title }, published: false }));
  };
  const submitRenameModule = (m: ModuleStaffOut, { title }: InlineValues) => {
    if (!title) { setInlineError(t("modules.settings.titleRequired")); return; }
    if (title === moduleName(m)) { cancelInline(); return; }
    void runInline(() => updateModule(course.id, m.id, { title: cleanLocalized({ ...m.title, [editLang]: title }, course.languages) }));
  };
  const submitRenameItem = (it: ItemStaffOut, { title }: InlineValues) => {
    if (!title && it.kind === "header") { setInlineError(t("modules.add.headerRequired")); return; }
    if (title === itemName(it)) { cancelInline(); return; }
    // Empty: back to the object's own title (the other languages of the override stay).
    const override: LocalizedText = cleanLocalized({ ...(it.title_override ?? {}), [editLang]: title }, course.languages);
    void runInline(() => updateItem(course.id, it.module_id, it.id, { title_override: Object.keys(override).length > 0 ? override : null }));
  };
  /** A new page or assignment exists even if the module refuses it: report it, the object waits in "Not in modules". */
  const placeCreated = async (moduleId: string, body: Parameters<typeof addItem>[2]) => {
    try {
      await addItem(course.id, moduleId, body);
    } catch {
      toast.error(t("pages.object.addToModuleFailed"));
    }
  };
  const submitAdd = (moduleId: string, kind: InlineKind, { title, url, assignmentKind, minutes }: InlineValues) => {
    const titled: LocalizedText = title ? { [editLang]: title } : {};
    if (kind === "url") {
      if (!/^https?:\/\/\S+$/i.test(url)) { setInlineError(t("modules.errors.url_invalid")); return; }
      const seconds = parseMinutes(minutes);
      if (seconds === undefined) { setInlineError(t("modules.editor.durationInvalid")); return; }
      void runInline(() => addItem(course.id, moduleId, {
        kind: "url", url, published: true, ...(title ? { title_override: titled } : {}), ...(seconds !== null ? { duration_s: seconds } : {}),
      }));
      return;
    }
    if (!title) { setInlineError(t(kind === "header" ? "modules.add.headerRequired" : "modules.settings.titleRequired")); return; }
    void runInline(async () => {
      if (kind === "header") await addItem(course.id, moduleId, { kind: "header", title_override: titled, published: true });
      else if (kind === "quiz") await createQuizItem(course.id, moduleId, { kind: "quiz", title: titled, quiz: { preset: "none", languages: [editLang] } });
      else if (kind === "page") {
        const p = await createPage(course.id, { title, language: editLang, body_md: "", published: false });
        await placeCreated(moduleId, { kind: "page", page_id: p.id, published: true });
      } else {
        const a = await createAssignment(course.id, { kind: assignmentKind, title: titled, points_possible: 10, due_at: null });
        await placeCreated(moduleId, { kind: "assignment", assignment_id: a.id, published: true });
      }
    });
  };
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
    setData((d) => (d ? { ...d, modules: [...next, ...d.modules.filter((m) => m.deleted_at)] } : d));
    const ok = await run(key, fn);
    if (!ok && before) setData(before);
  };

  const saveSettings = (v: ModuleSettingsValue, module: ModuleStaffOut) => run("settings", () => (
    updateModule(course.id, module.id, { title: v.title, unlock_at: v.unlock_at, sequential: v.sequential, completion_mode: v.completion_mode })
  ), { inDialog: true });

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

  /** Phase 8c UX M4: the icon toggle and the menu entry; a toast names the new state. */
  const publishToast = (published: boolean, title: string) =>
    (published ? t("modules.editor.toastPublished", { title }) : t("modules.editor.toastUnpublished", { title }));
  const toggleModulePublished = (m: ModuleStaffOut) => {
    // 8a UX M1: publishing a module whose requirement points at a draft asks first
    if (!m.published && ignoredReqItems(m).length > 0) { setDialogError(null); setDialog({ kind: "publishWarn", module: m, names: ignoredNames(m) }); return; }
    void run(`pub-${m.id}`, () => updateModule(course.id, m.id, { published: !m.published }), { success: publishToast(!m.published, moduleName(m)) });
  };
  const toggleItemPublished = (m: ModuleStaffOut, it: ItemStaffOut) => {
    void run(`ip-${it.id}`, () => updateItem(course.id, m.id, it.id, { published: !it.published }), { success: publishToast(!it.published, itemName(it)) });
  };

  /** F5c: Pro on asks first (students without access see only the titles); Pro off is immediate. */
  const toggleModulePro = (m: ModuleStaffOut) => {
    if (m.access_tier !== "paid") { setDialogError(null); setDialog({ kind: "pro", module: m }); return; }
    void run(`pro-${m.id}`, () => updateModule(course.id, m.id, { access_tier: "free" }), { success: t("modules.editor.toastFree", { title: moduleName(m) }) });
  };
  const saveDuration = (m: ModuleStaffOut, it: ItemStaffOut, seconds: number | null) =>
    run(`dur-${it.id}`, () => updateItem(course.id, m.id, it.id, { duration_s: seconds }));
  /** ↑ ↓ buttons: the same optimistic reorder as a drop; focus stays on the pressed button of the moved row. */
  const moveItemBy = (m: ModuleStaffOut, ii: number, dir: -1 | 1) => {
    if (busy) return;
    const it = sortedItems(m)[ii];
    if (!it) return;
    moveItemTo(m, ii, ii + dir);
    window.requestAnimationFrame(() => document.querySelector<HTMLElement>(`#mi-${it.id} [data-move="${dir < 0 ? "up" : "down"}"]`)?.focus());
  };

  const onModuleMenu = (m: ModuleStaffOut, mi: number, id: string) => {
    setDialogError(null);
    if (id === "publish") toggleModulePublished(m);
    else if (id === "rename") openInline({ type: "renameModule", id: m.id });
    else if (id === "settings") setDialog({ kind: "settings", module: m });
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
    if (id === "publish") toggleItemPublished(m, item);
    else if (id === "rename") openInline({ type: "renameItem", id: item.id, moduleId: m.id });
    else if (id === "edit") setDialog({ kind: "editItem", item });
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
    else if (id === "video") setDialog({ kind: "video", module: m });
    else if (id === "existing") setDialog({ kind: "addItem", module: m });
    // ORT courses take no new non-quiz assignments (7a): their "Assignment" entry picks an existing one
    else if (INLINE_KINDS.includes(id) && !(ortCourse && id === "assignment")) {
      if (collapsed.includes(m.id)) toggleCollapsed(m.id);
      openInline({ type: "add", moduleId: m.id, kind: id as InlineKind });
    } else setDialog({ kind: "addItem", module: m, initialKind: id as AddKind });
  };

  /** FB8 S2: the one "+ Добавить" menu of a module: lesson content, checks, then the header and an existing object. */
  const addGroups: MenuGroup[] = [
    {
      id: "content", heading: t("coursePage.addGroups.content"), items: [
        { id: "video", label: t("modules.editor.addVideo"), icon: <PlayCircle aria-hidden="true" /> },
        { id: "page", label: t("coursePage.addItems.page"), icon: <ItemKindIcon kind="page" /> },
        { id: "file", label: t("coursePage.addItems.file"), icon: <ItemKindIcon kind="file" /> },
        { id: "url", label: t("coursePage.addItems.link"), icon: <ItemKindIcon kind="url" /> },
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
    {
      id: "more", heading: t("modules.editor.addMore"), items: [
        { id: "header", label: t("coursePage.addItems.header"), icon: <ItemKindIcon kind="header" /> },
        { id: "existing", label: t("coursePage.addExisting") },
      ],
    },
  ];

  const allCollapsed = live.length > 0 && live.every((m) => collapsed.includes(m.id));
  const moreGroups: MenuGroup[] = [{
    id: "more", items: [
      ...(live.length > 1 ? [{ id: "toggleAll", label: allCollapsed ? t("coursePage.expandAll") : t("coursePage.collapseAll") }] : []),
      { id: "progress", label: t("modules.progress.open") },
      ...(canEdit ? [{ id: "reapply", label: t("modules.editor.reapplyCourse"), description: t("modules.editor.reapplyWholeCourse") }] : []),
      { id: "deleted", label: showDeleted ? t("coursePage.hideDeleted") : t("modules.editor.showDeleted") },
    ],
  }];
  const onMore = (id: string) => {
    if (id === "toggleAll") saveCollapsed(allCollapsed ? [] : live.map((m) => m.id));
    else if (id === "progress") setDialog({ kind: "progress" });
    else if (id === "reapply") { setDialogError(null); setDialog({ kind: "reapply", module: null }); }
    else if (id === "deleted") setShowDeleted((s) => !s);
  };

  const newModuleButton = (
    <Button data-new-module leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} onClick={() => openInline({ type: "newModule" })}>
      {t("modules.editor.newModule")}
    </Button>
  );
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-xl font-semibold leading-7 text-slate-900">{t("modules.editor.title")}</h2>
      <div className="flex items-center gap-1 sm:gap-2">
        {/* an empty course shows "New module" in its empty state */}
        {canEdit && (live.length > 0 || deleted.length > 0) && newModuleButton}
        {(live.length > 0 || deleted.length > 0 || showDeleted) && (
          <OutlineMenu label={t("coursePage.moreActions")} groups={moreGroups} onSelect={onMore} />
        )}
      </div>
    </div>
  );

  const newModuleForm = inline?.type === "newModule" && (
    <div className="rounded-xl border border-brand-300 bg-white p-2 shadow-sm sm:p-3">
      <InlineForm label={t("modules.settings.titleLabel")} submitLabel={t("modules.settings.create")} busy={inlineBusy} error={inlineError}
        onSubmit={submitNewModule} onCancel={cancelInline} />
    </div>
  );

  let body: React.ReactNode;
  if (error && !data) body = <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  else if (!data) body = <LoadingState rows={3} />;
  else if (live.length === 0 && deleted.length === 0) {
    body = newModuleForm || (
      <EmptyState mascot="working" title={t("modules.editor.emptyTitle")} description={canEdit ? t("modules.editor.emptyBody") : undefined}
        action={canEdit ? newModuleButton : undefined} />
    );
  } else {
    body = (
      <div className="space-y-3">
        {live.map((m, mi) => {
          const items = sortedItems(m);
          const prereqNames = m.prerequisites.map((id) => live.find((x) => x.id === id)).filter(Boolean).map((x) => moduleName(x!));
          const headingId = `om-${m.id}`;
          const itemsId = `omi-${m.id}`;
          const isCollapsed = collapsed.includes(m.id);
          const name = moduleName(m);
          const dropTarget = over === `m:${m.id}` || over === `end:${m.id}`;
          // what used to be a line of its own: a tooltip here, and the same words in the Settings menu entry for phones
          const details = [
            m.unlock_at ? t("modules.reason.unlockAt", { date: fmtShortDateTime(m.unlock_at, lang) }) : "",
            m.sequential ? t("modules.sequentialHint") : "",
            m.completion_mode === "any" ? t("modules.completionAny") : "",
            prereqNames.length > 0 ? t("modules.editor.after", { titles: prereqNames.join(", ") }) : "",
          ].filter(Boolean).join(" · ");
          const renaming = inline?.type === "renameModule" && inline.id === m.id;
          const adding = inline?.type === "add" && inline.moduleId === m.id ? inline.kind : null;
          const addLabel = t("coursePage.add", { title: name });
          // F5c: "5 уроков · 32 мин" (published lessons and their minutes, from the server)
          const lessonsLine = [
            m.lessons_count ? t("modules.editor.lessons", { n: m.lessons_count }) : "",
            m.duration_s ? durationText(m.duration_s) : "",
          ].filter(Boolean).join(" · ");
          // F5c (§5): a free module that waits for a Pro one stays locked for students without access
          const proPrereq = isPlatform && m.access_tier !== "paid"
            && m.prerequisites.some((id) => live.find((x) => x.id === id)?.access_tier === "paid");
          return (
            <section key={m.id} id={`m-${m.id}`} aria-labelledby={headingId}
              onDragOver={canEdit ? onModuleDragOver(m) : undefined} onDrop={canEdit ? onModuleDrop(m, mi) : undefined}
              className={cn("scroll-mt-24 rounded-xl border bg-white shadow-sm",
                dropTarget ? "border-brand-500 ring-2 ring-brand-200" : "border-slate-200",
                drag?.type === "module" && drag.id === m.id && "opacity-60")}>
              <header className="group/mod rounded-t-xl bg-slate-50 px-1 sm:px-2">
                <div className="flex min-h-12 items-center gap-0.5">
                  <button type="button" aria-expanded={!isCollapsed} aria-controls={itemsId} onClick={() => toggleCollapsed(m.id)}
                    aria-label={t("coursePage.toggleModule", { title: name })} title={t("coursePage.toggleModule", { title: name })}
                    className={cn("inline-flex h-11 w-9 shrink-0 items-center justify-center rounded-xl text-slate-600 hover:bg-slate-100", focusRing)}>
                    <ChevronRight aria-hidden="true" className={cn("h-5 w-5 transition-transform", !isCollapsed && "rotate-90")} />
                  </button>
                  {renaming ? (
                    <InlineForm className="min-w-0 flex-1 py-1.5 pr-1" label={t("coursePage.rename")} initial={name} submitLabel={t("lms.common.save")}
                      busy={inlineBusy} error={inlineError} onSubmit={(v) => submitRenameModule(m, v)} onCancel={cancelInline} />
                  ) : (
                    <>
                      <div className="min-w-0 flex-1 py-1 sm:flex sm:items-baseline sm:gap-3">
                        <h3 id={headingId} className="break-words text-base font-semibold leading-6 text-slate-900">{name}</h3>
                        <p className="flex flex-wrap items-center gap-x-2 text-sm leading-5 text-slate-600 sm:shrink-0">
                          {!m.published && <span>{t("modules.editor.draft")}</span>}
                          {m.published && !canEdit && <span>{t("modules.editor.published")}</span>}
                          {lessonsLine && <span>{lessonsLine}</span>}
                          {isCollapsed && <span>{t("coursePage.itemCount", { n: m.items.length })}</span>}
                          {details && (
                            <span title={details} className="inline-flex self-center">
                              <Info aria-hidden="true" className="h-4 w-4 text-slate-500" />
                              <span className="sr-only">{details}</span>
                            </span>
                          )}
                        </p>
                      </div>
                      {canEdit && (
                        <div className="flex shrink-0 items-center">
                          {/* F5c: only where the server accepts it (platform courses) */}
                          {isPlatform && (
                            <LockToggle locked={m.access_tier === "paid"} label={t("modules.editor.proSwitch", { title: name })}
                              lockedHint={t("modules.editor.proHintOn")} unlockedHint={t("modules.editor.proHintOff")}
                              busy={busy === `pro-${m.id}`} onToggle={() => toggleModulePro(m)} />
                          )}
                          <PublishSwitch published={m.published} name={name} busy={busy === `pub-${m.id}`}
                            onToggle={() => toggleModulePublished(m)} />
                          <OutlineMenu label={t("modules.editor.actions")} sheetTitle={t("modules.editor.actionsFor", { title: name })}
                            onSelect={(id) => onModuleMenu(m, mi, id)} groups={[{
                            id: "module", items: [
                              { id: "publish", label: m.published ? t("modules.editor.unpublish") : t("modules.editor.publish"), disabled: !!busy },
                              { id: "rename", label: t("coursePage.rename") },
                              { id: "settings", label: t("modules.editor.editSettings"), description: details || undefined },
                              // Phase 8c UX m3: the first module has no Prerequisites and no Move up
                              ...(mi > 0 ? [{ id: "prereq", label: t("modules.editor.prerequisites") }] : []),
                              { id: "duplicate", label: t("modules.editor.duplicate"), disabled: !!busy },
                              ...(mi > 0 ? [{ id: "up", label: t("modules.editor.moveUp"), disabled: !!busy }] : []),
                              { id: "down", label: t("modules.editor.moveDown"), disabled: mi === live.length - 1 || !!busy },
                              { id: "reapply", label: t("modules.editor.reapply") },
                              { id: "progress", label: t("modules.progress.open") },
                              { id: "delete", label: t("modules.editor.delete"), danger: true },
                            ],
                          }]} />
                          <DragHandle label={t("modules.editor.dragHandle", { title: name })} onEnd={endDrag}
                            onStart={startDrag({ type: "module", id: m.id }, `m-${m.id}`)} />
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="space-y-2 pb-2 pl-1 empty:hidden sm:pl-10">
                  {m.warnings.length > 0 && <Warnings warnings={m.warnings} />}
                  {proPrereq && (
                    <p role="note" className="flex items-start gap-1.5 text-sm leading-5 text-warning-900">
                      <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-warning-700" />
                      <span className="min-w-0 break-words">{t("modules.editor.proPrereqWarning")}</span>
                    </p>
                  )}
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
              <div id={itemsId} hidden={isCollapsed} className="border-t border-slate-200">
                {items.length > 0 && (
                  <ul className="divide-y divide-slate-100">
                    {items.map((it, ii) => {
                      const pad = ["", "sm:pl-8", "sm:pl-12", "sm:pl-16"][Math.min(it.indent, 3)];
                      const iname = itemName(it);
                      const href = it.kind !== "header" ? itemHref(it) : null;
                      const titleCls = cn("block break-words text-base leading-6 sm:truncate sm:text-sm",
                        it.kind === "header" ? "font-semibold uppercase tracking-wide text-slate-700" : "font-medium text-slate-900");
                      const reqLine = it.requirement ? t("modules.editor.requirement", { text: reqText(it.requirement.type, it.requirement.threshold) }) : null;
                      const language = it.target?.language && it.kind === "page" ? t(`courses.languages.${it.target.language}`) : null;
                      const renamingItem = inline?.type === "renameItem" && inline.id === it.id;
                      // F5c: a YouTube / Vimeo link reads as a video (the client guess; students get the player when the server agrees)
                      const isVideo = it.kind === "url" && !!parseVideo(it.url);
                      return (
                        <li key={it.id} id={`mi-${it.id}`} onDragOver={canEdit ? onItemDragOver(it) : undefined} onDrop={canEdit ? onItemDrop(m, ii) : undefined}
                          className={cn("group/row flex min-h-11 items-center gap-1 px-1 sm:px-2", pad,
                            over === `i:${it.id}` && "shadow-[inset_0_2px_0_0_theme(colors.brand.500)]",
                            drag?.type === "item" && drag.id === it.id && "opacity-60")}>
                          {isVideo
                            ? <PlayCircle aria-hidden="true" className="ml-1 h-4 w-4 shrink-0 text-slate-500" />
                            : <ItemKindIcon kind={it.kind} assignmentKind={it.target?.assignment_kind} className="ml-1 h-4 w-4 text-slate-500" />}
                          {renamingItem ? (
                            <InlineForm className="min-w-0 flex-1 py-1.5 pl-2 pr-1" label={t("coursePage.rename")} initial={iname} submitLabel={t("lms.common.save")}
                              busy={inlineBusy} error={inlineError} onSubmit={(v) => submitRenameItem(it, v)} onCancel={cancelInline} />
                          ) : (
                            <>
                              <div className="min-w-0 flex-1 py-1.5 pl-2 sm:flex sm:items-center sm:gap-3">
                                <div className="min-w-0 sm:shrink" title={language ? `${iname} · ${language}` : iname}>
                                  {href ? (
                                    <Link href={href} className={cn(titleCls, "rounded hover:text-brand-700 hover:underline", focusRing)}>{iname}</Link>
                                  ) : it.kind === "url" && it.url ? (
                                    <a href={it.url} target="_blank" rel="noopener noreferrer" className={cn(titleCls, "rounded hover:text-brand-700 hover:underline", focusRing)}>
                                      {iname}<span className="sr-only"> {t("modules.opensNewTab")}</span>
                                    </a>
                                  ) : (
                                    <p className={titleCls}>{iname}</p>
                                  )}
                                </div>
                                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm leading-5 text-slate-600 sm:shrink-0 sm:flex-nowrap sm:whitespace-nowrap">
                                  {it.kind !== "header" && <span>{isVideo ? t("modules.editor.addVideo") : kindText(it.kind, it.target?.assignment_kind)}</span>}
                                  {!it.published && <span>{t("modules.editor.draft")}</span>}
                                  {it.requirement && reqLine && (
                                    <span title={reqLine} className="inline-flex items-center gap-1 sm:rounded-full sm:border sm:border-slate-200 sm:px-2 sm:text-xs sm:leading-5">
                                      <Flag aria-hidden="true" className="h-4 w-4 text-slate-500 sm:h-3.5 sm:w-3.5" />
                                      <span className="sr-only">{reqLine}</span>
                                      <span aria-hidden="true" className="hidden sm:inline">{reqText(it.requirement.type, it.requirement.threshold)}</span>
                                    </span>
                                  )}
                                  <Warnings warnings={it.warnings} />
                                </div>
                              </div>
                              {LESSON_KINDS.includes(it.kind) && (canEdit ? (
                                <DurationChip seconds={it.duration_s} name={iname} onSave={(sec) => saveDuration(m, it, sec)} />
                              ) : it.duration_s ? (
                                <span className="shrink-0 px-1 text-sm text-slate-600">{durationText(it.duration_s)}</span>
                              ) : null)}
                              {canEdit && (
                                <div className="flex shrink-0 items-center">
                                  <MoveButtons name={iname} first={ii === 0} last={ii === items.length - 1} onMove={(dir) => moveItemBy(m, ii, dir)} />
                                  <PublishSwitch published={it.published} name={iname} busy={busy === `ip-${it.id}`}
                                    onToggle={() => toggleItemPublished(m, it)} />
                                  <OutlineMenu label={t("modules.editor.actionsFor", { title: iname })} onSelect={(id) => onItemMenu(m, it, ii, id)} groups={[{
                                    id: "item", items: [
                                      // Phase 8c UX M4, M6: Publish first, then Open, settings, requirement, moves; Remove last
                                      { id: "publish", label: it.published ? t("modules.editor.unpublish") : t("modules.editor.publish"), disabled: !!busy },
                                      ...(it.kind !== "header" ? [{ id: "open", label: it.target?.assignment_kind === "quiz" ? t("modules.editor.editQuiz") : t("modules.editor.openTarget") }] : []),
                                      { id: "rename", label: t("coursePage.rename") },
                                      { id: "edit", label: t("modules.editor.editItem"), description: language ?? undefined },
                                      ...(it.kind !== "header" ? [{ id: "requirement", label: t("modules.editor.setRequirement"), description: reqLine ?? undefined }] : []),
                                      { id: "up", label: t("modules.editor.moveUp"), disabled: ii === 0 || !!busy },
                                      { id: "down", label: t("modules.editor.moveDown"), disabled: ii === items.length - 1 || !!busy },
                                      ...(live.length > 1 ? [{ id: "move", label: t("modules.editor.moveTo") }] : []),
                                      { id: "delete", label: t("modules.editor.removeItem"), danger: true },
                                    ],
                                  }]} />
                                  <DragHandle label={t("modules.editor.dragHandle", { title: iname })} onEnd={endDrag}
                                    onStart={startDrag({ type: "item", id: it.id, moduleId: m.id }, `mi-${it.id}`)} />
                                </div>
                              )}
                            </>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {adding ? (
                  <div className={cn("flex items-start gap-1 px-1 py-1.5 sm:px-2", items.length > 0 && "border-t border-slate-100")}>
                    <ItemKindIcon kind={adding === "quiz" ? "assignment" : adding} assignmentKind={adding === "quiz" ? "quiz" : adding === "assignment" ? "text" : undefined}
                      className="ml-1 mt-3 h-4 w-4 text-slate-500" />
                    <InlineForm className="min-w-0 flex-1 pl-2 pr-1" submitLabel={t("modules.add.submit")} busy={inlineBusy} error={inlineError}
                      label={t("coursePage.inlineTitle", { kind: t(`coursePage.addItems.${adding === "url" ? "link" : adding}`) })}
                      url={adding === "url" ? { label: t("modules.add.url") } : undefined}
                      minutes={adding === "url" ? { label: t("modules.editor.linkMinutes") } : undefined}
                      assignmentKinds={adding === "assignment" ? { label: t("assignments.create.kind"), options: INLINE_ASSIGNMENT_KINDS.map((k) => ({ value: k, label: t(`assignments.kinds.${k}`) })) } : undefined}
                      onSubmit={(v) => submitAdd(m.id, adding, v)} onCancel={cancelInline} />
                  </div>
                ) : canEdit && (
                  <div className={cn("px-2 py-2 sm:px-3", items.length > 0 && "border-t border-slate-100")}>
                    {items.length === 0 && <p className="px-1 pb-1.5 text-sm leading-5 text-slate-600">{t("modules.editor.emptyModule")}</p>}
                    {/* FB8 S2: one "+ Добавить" menu (a bottom sheet on phones) instead of a button per kind */}
                    <OutlineMenu trigger="button" variant="secondary" chevron label={addLabel} groups={addGroups} onSelect={(id) => onAdd(m, id)}
                      leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} text={t("modules.editor.addMenu")} />
                  </div>
                )}
              </div>
            </section>
          );
        })}
        {newModuleForm}
      </div>
    );
  }

  const d = dialog;
  return (
    <div className="space-y-4">
      {header}
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
      {d?.kind === "video" && (
        <VideoDialog open module={d.module} courseId={course.id} editLang={editLang} defaultLang={course.default_language}
          onAdded={() => { closeDialog(); void load(); onChanged?.(); }} onClose={closeDialog} />
      )}
      {d?.kind === "pro" && (
        <ConfirmDialog open busy={busy === `pro-${d.module.id}`} title={t("modules.editor.proConfirmTitle")} object={moduleName(d.module)}
          effect={t("modules.editor.proConfirmBody")} confirmLabel={t("modules.editor.proConfirm")} error={dialogError ?? undefined}
          onConfirm={() => void run(`pro-${d.module.id}`, () => updateModule(course.id, d.module.id, { access_tier: "paid" }),
            { inDialog: true, success: t("modules.editor.toastPro", { title: moduleName(d.module) }) })}
          onCancel={closeDialog} />
      )}
      {d?.kind === "publishWarn" && (
        <ConfirmDialog open busy={busy === `pub-${d.module.id}`} title={t("modules.warnings.requirementIgnoredTitle")} object={moduleName(d.module)}
          effect={t("modules.warnings.requirementIgnoredBody", { item: d.names })} confirmLabel={t("modules.editor.publishAnyway")}
          error={dialogError ?? undefined}
          onConfirm={() => void run(`pub-${d.module.id}`, () => updateModule(course.id, d.module.id, { published: true }),
            { inDialog: true, success: t("modules.editor.toastPublished", { title: moduleName(d.module) }) })}
          onCancel={closeDialog} />
      )}
    </div>
  );
}
