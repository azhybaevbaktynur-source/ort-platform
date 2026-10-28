"use client";

// Phase 8a S4a (PHASE_8A_DESIGN 8.1): the teacher's module outline. "New module" is the one primary action; each
// module card has a publish switch, move up/down buttons and a labelled actions menu (settings, prerequisites,
// re-apply rules, delete); each item row has a visibility switch, move up/down buttons and an actions menu
// (edit, completion requirement, move to another module, open, remove). Everything is a visible button: no drag-only
// action (375 px first). Warnings are badges with text. Writes reload the outline (one document, design 2.3).
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, Plus, RefreshCw, Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import {
  clearRequirement, createModule, deleteItem, deleteModule, getModules, moveItem, reapplyCourse, reapplyModule, reorderItems,
  reorderModules, restoreModule, setPrerequisites, setRequirement, updateItem, updateModule,
} from "@/lib/lms/modules";
import type { ItemStaffOut, ModuleStaffOut, ModulesStaffOut, ModuleWarningOut } from "@/lib/lms/modulesTypes";
import { isStaffCourse } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import {
  Badge, Button, Checkbox, ConfirmDialog, EmptyState, ErrorState, IconButton, LoadingState, MenuButton, PageHeader, Switch, toast,
} from "@/components/ui";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { ItemKindIcon, useItemKindText, useModuleErrorText, useRequirementText } from "./moduleUi";
import { ItemEditDialog, ModuleSettingsDialog, MoveItemDialog, PrerequisiteDialog, RequirementDialog, type ModuleSettingsValue } from "./OutlineDialogs";
import { AddItemDialog } from "./AddItemDialog";
import { ProgressDrawer } from "./ProgressDrawer";

type DialogState =
  | null
  | { kind: "newModule" }
  | { kind: "settings"; module: ModuleStaffOut }
  | { kind: "prereq"; module: ModuleStaffOut }
  | { kind: "deleteModule"; module: ModuleStaffOut }
  | { kind: "reapply"; module: ModuleStaffOut | null }
  | { kind: "addItem"; module: ModuleStaffOut }
  | { kind: "editItem"; item: ItemStaffOut }
  | { kind: "requirement"; item: ItemStaffOut }
  | { kind: "moveItem"; item: ItemStaffOut }
  | { kind: "deleteItem"; item: ItemStaffOut }
  | { kind: "progress" };

function swap<T>(list: T[], i: number, j: number): T[] {
  const next = [...list];
  [next[i], next[j]] = [next[j], next[i]];
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

export function ModuleOutlineEditor() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const errorText = useModuleErrorText();
  const kindText = useItemKindText();
  const reqText = useRequirementText();
  const base = `/${lang}/courses/${course.id}`;
  const langs = { languages: course.languages, defaultLanguage: course.default_language };
  const canEdit = course.status !== "concluded";
  const [data, setData] = useState<ModulesStaffOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [showDeleted, setShowDeleted] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = (await getModules(course.id, { deleted: showDeleted })) as ModulesStaffOut;
      setData({ modules: [...(out.modules ?? [])].sort((a, b) => a.position - b.position) });
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, showDeleted]);
  useEffect(() => { void load(); }, [load]);

  const live = useMemo(() => (data?.modules ?? []).filter((m) => !m.deleted_at), [data]);
  const deleted = useMemo(() => (data?.modules ?? []).filter((m) => m.deleted_at), [data]);
  const moduleName = (m: ModuleStaffOut) => pickLocalized(m.title, lang, course.default_language) || t("modules.untitledModule");
  const itemName = (i: ItemStaffOut) =>
    pickLocalized(i.title_override, lang, course.default_language) || pickLocalized(i.target?.title, lang, course.default_language)
    || i.url || t("modules.untitledItem");

  const closeDialog = () => { setDialog(null); setDialogError(null); };

  /** Runs a write; `inDialog`: keep the dialog open and show the error in it. */
  const run = async (key: string, fn: () => Promise<unknown>, opts: { inDialog?: boolean; success?: string } = {}) => {
    setBusy(key);
    setDialogError(null);
    try {
      await fn();
      if (opts.inDialog) closeDialog();
      if (opts.success) toast.success(opts.success);
      await load();
      return true;
    } catch (e) {
      if (opts.inDialog) setDialogError(errorText(e));
      else toast.error(errorText(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const saveSettings = (v: ModuleSettingsValue, module: ModuleStaffOut | null) => run("settings", () => (module
    ? updateModule(course.id, module.id, { title: v.title, unlock_at: v.unlock_at, sequential: v.sequential, completion_mode: v.completion_mode })
    : createModule(course.id, v)), { inDialog: true });

  const moveModule = (index: number, delta: number) => {
    const next = swap(live, index, index + delta).map((m) => m.id);
    void run(`mm-${live[index].id}`, () => reorderModules(course.id, next));
  };
  const moveItemBy = (module: ModuleStaffOut, index: number, delta: number) => {
    const items = [...module.items].sort((a, b) => a.position - b.position);
    const next = swap(items, index, index + delta).map((i) => i.id);
    void run(`mi-${items[index].id}`, () => reorderItems(course.id, module.id, next));
  };

  const onModuleMenu = (m: ModuleStaffOut, id: string) => {
    setDialogError(null);
    if (id === "settings") setDialog({ kind: "settings", module: m });
    else if (id === "prereq") setDialog({ kind: "prereq", module: m });
    else if (id === "reapply") setDialog({ kind: "reapply", module: m });
    else if (id === "delete") setDialog({ kind: "deleteModule", module: m });
  };
  const onItemMenu = (item: ItemStaffOut, id: string) => {
    setDialogError(null);
    if (id === "edit") setDialog({ kind: "editItem", item });
    else if (id === "requirement") setDialog({ kind: "requirement", item });
    else if (id === "move") setDialog({ kind: "moveItem", item });
    else if (id === "delete") setDialog({ kind: "deleteItem", item });
    else if (id === "open") {
      const href = item.kind === "page" && item.page_id ? `${base}/pages/${item.page_id}/edit`
        : item.kind === "file" ? `${base}/files`
          : item.kind === "assignment" && item.target?.assignment_kind === "quiz" && item.target.assessment_id ? `${base}/assessments/${item.target.assessment_id}/edit`
            : item.kind === "assignment" && item.assignment_id ? `${base}/assignments/${item.assignment_id}` : null;
      if (href) router.push(href);
      else if (item.url) window.open(item.url, "_blank", "noopener,noreferrer");
    }
  };

  const header = (
    <PageHeader title={t("modules.editor.title")} description={t("modules.editor.description")} className="mb-2"
      primaryAction={canEdit ? (
        <Button leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} onClick={() => { setDialogError(null); setDialog({ kind: "newModule" }); }}>
          {t("modules.editor.newModule")}
        </Button>
      ) : undefined}
      secondaryActions={live.length > 0 ? (
        <>
          {isStaffCourse(course) && (
            <Button variant="secondary" leftIcon={<Users aria-hidden="true" className="h-4 w-4" />} onClick={() => setDialog({ kind: "progress" })}>
              {t("modules.progress.open")}
            </Button>
          )}
          {canEdit && (
            <Button variant="secondary" leftIcon={<RefreshCw aria-hidden="true" className="h-4 w-4" />} onClick={() => setDialog({ kind: "reapply", module: null })}>
              {t("modules.editor.reapplyCourse")}
            </Button>
          )}
        </>
      ) : undefined} />
  );

  let body: React.ReactNode;
  if (error && !data) body = <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  else if (!data) body = <LoadingState rows={3} />;
  else if (live.length === 0 && deleted.length === 0) {
    body = (
      <EmptyState title={t("modules.editor.emptyTitle")} description={t("modules.editor.emptyBody")}
        action={canEdit ? <Button onClick={() => setDialog({ kind: "newModule" })} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{t("modules.editor.newModule")}</Button> : undefined} />
    );
  } else {
    body = (
      <div className="space-y-5">
        {live.map((m, mi) => {
          const items = [...m.items].sort((a, b) => a.position - b.position);
          const prereqNames = m.prerequisites.map((id) => live.find((x) => x.id === id)).filter(Boolean).map((x) => moduleName(x!));
          const headingId = `om-${m.id}`;
          return (
            <section key={m.id} aria-labelledby={headingId} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
              <header className="space-y-2 border-b border-slate-100 px-4 py-4 sm:px-6">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <h2 id={headingId} className="break-words text-lg font-semibold leading-7 text-slate-900">{moduleName(m)}</h2>
                    <p className="mt-0.5 flex flex-wrap gap-x-3 text-sm leading-6 text-slate-600">
                      <span>{m.published ? t("modules.editor.published") : t("modules.editor.draft")}</span>
                      {m.unlock_at && <span>{t("modules.reason.unlockAt", { date: fmtShortDateTime(m.unlock_at, lang) })}</span>}
                      {m.sequential && <span>{t("modules.sequentialHint")}</span>}
                      {m.completion_mode === "any" && <span>{t("modules.completionAny")}</span>}
                      {prereqNames.length > 0 && <span className="break-words">{t("modules.editor.after", { titles: prereqNames.join(", ") })}</span>}
                    </p>
                  </div>
                  {canEdit && (
                    <div className="flex shrink-0 flex-wrap items-center gap-1">
                      <Switch label={t("modules.editor.publishModule")} checked={m.published} busy={busy === `pub-${m.id}`}
                        onChange={(v) => void run(`pub-${m.id}`, () => updateModule(course.id, m.id, { published: v }))} />
                      <IconButton aria-label={t("modules.editor.moveModuleUp")} icon={<ArrowUp />} disabled={mi === 0 || !!busy} onClick={() => moveModule(mi, -1)} />
                      <IconButton aria-label={t("modules.editor.moveModuleDown")} icon={<ArrowDown />} disabled={mi === live.length - 1 || !!busy} onClick={() => moveModule(mi, 1)} />
                      <MenuButton variant="secondary" size="sm" label={t("modules.editor.actions")} onSelect={(id) => onModuleMenu(m, id)} items={[
                        { id: "settings", label: t("modules.editor.editSettings") },
                        { id: "prereq", label: t("modules.editor.prerequisites"), disabled: mi === 0 },
                        { id: "reapply", label: t("modules.editor.reapply") },
                        { id: "delete", label: t("modules.editor.delete") },
                      ]} />
                    </div>
                  )}
                </div>
                <Warnings warnings={m.warnings} />
              </header>
              {items.length === 0 ? (
                <p className="px-4 py-4 text-base text-slate-600 sm:px-6 sm:text-sm">{t("modules.editor.noItems")}</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {items.map((it, ii) => {
                    const pad = ["", "sm:pl-10", "sm:pl-14", "sm:pl-20"][Math.min(it.indent, 3)];
                    const hidden = !it.published || (it.target && (!it.target.published || it.target.deleted));
                    return (
                      <li key={it.id} className={`px-4 py-3 sm:px-6 ${pad}`}>
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                          <div className="flex min-w-0 items-start gap-3">
                            <ItemKindIcon kind={it.kind} assignmentKind={it.target?.assignment_kind} className="mt-1 h-5 w-5 text-slate-500" />
                            <div className="min-w-0">
                              <p className={`break-words text-base leading-6 sm:text-sm ${it.kind === "header" ? "font-semibold uppercase tracking-wide text-slate-700" : "font-medium text-slate-900"} ${hidden ? "opacity-80" : ""}`}>{itemName(it)}</p>
                              <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm leading-6 text-slate-600">
                                <span>{kindText(it.kind, it.target?.assignment_kind)}</span>
                                {it.target?.language && it.kind === "page" && <span>{t(`courses.languages.${it.target.language}`)}</span>}
                                {it.requirement && <span>{t("modules.editor.requirement", { text: reqText(it.requirement.type, it.requirement.threshold) })}</span>}
                                {!it.published && <Badge>{t("modules.editor.hidden")}</Badge>}
                                <Warnings warnings={it.warnings} />
                              </p>
                            </div>
                          </div>
                          {canEdit && (
                            <div className="flex shrink-0 flex-wrap items-center gap-1 pl-8 lg:pl-0">
                              <Switch label={t("modules.editor.visible")} checked={it.published} busy={busy === `ip-${it.id}`}
                                onChange={(v) => void run(`ip-${it.id}`, () => updateItem(course.id, m.id, it.id, { published: v }))} />
                              <IconButton aria-label={t("modules.editor.moveItemUp", { title: itemName(it) })} icon={<ArrowUp />} disabled={ii === 0 || !!busy} onClick={() => moveItemBy(m, ii, -1)} />
                              <IconButton aria-label={t("modules.editor.moveItemDown", { title: itemName(it) })} icon={<ArrowDown />} disabled={ii === items.length - 1 || !!busy} onClick={() => moveItemBy(m, ii, 1)} />
                              <MenuButton variant="secondary" size="sm" label={t("modules.editor.actions")} onSelect={(id) => onItemMenu(it, id)} items={[
                                { id: "edit", label: t("modules.editor.editItem") },
                                ...(it.kind !== "header" ? [{ id: "requirement", label: t("modules.editor.setRequirement") }] : []),
                                ...(live.length > 1 ? [{ id: "move", label: t("modules.editor.moveTo") }] : []),
                                ...(it.kind !== "header" ? [{ id: "open", label: it.target?.assignment_kind === "quiz" ? t("modules.editor.editQuiz") : t("modules.editor.openTarget") }] : []),
                                { id: "delete", label: t("modules.editor.removeItem") },
                              ]} />
                            </div>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
              {canEdit && (
                <div className="border-t border-slate-100 px-4 py-3 sm:px-6">
                  <Button variant="secondary" size="sm" leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}
                    onClick={() => { setDialogError(null); setDialog({ kind: "addItem", module: m }); }}>
                    {t("modules.editor.addItem")}
                  </Button>
                </div>
              )}
            </section>
          );
        })}

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
      </div>
    );
  }

  const d = dialog;
  return (
    <div className="space-y-5">
      {header}
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700">{t("courses.home.concludedNotice")}</p>
      )}
      {data && (live.length > 0 || deleted.length > 0 || showDeleted) && (
        <Checkbox label={t("modules.editor.showDeleted")} checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
      )}
      {body}

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
        <AddItemDialog open module={d.module} courseId={course.id} base={base} langs={langs}
          onAdded={() => { closeDialog(); void load(); }} onClose={closeDialog} />
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
    </div>
  );
}
