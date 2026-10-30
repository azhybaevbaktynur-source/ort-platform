"use client";

// Phase 8c S2 (PHASE_8C_DESIGN §3.4): the "Unsorted" group, last in the teacher outline. Live assignments (quizzes
// included), pages (one row per translation group, with language chips) and course files that no live item of a live
// module references (`GET _C/modules/unsorted`, S1): 20 rows per kind with "Show more" per kind. Each row: kind icon,
// title, draft mark and a "⋯" menu (Move to module…, Open, Delete). Collapsed when empty ("Everything is in a module").
import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { deleteAssignment } from "@/lib/lms/assignments";
import { deleteCourseFile } from "@/lib/lms/courseFiles";
import { pickLocalized } from "@/lib/lms/localized";
import type { ModuleStaffOut } from "@/lib/lms/modulesTypes";
import { withFrom } from "@/lib/lms/nav";
import { deletePage } from "@/lib/lms/pages";
import type { Lang, UnsortedItemOut, UnsortedKind, UnsortedOut, UnsortedPageOut } from "@/lib/lms/types";
import { getUnsorted } from "@/lib/lms/unsorted";
import { ItemKindIcon, useModuleErrorText } from "@/components/lms/modules/moduleUi";
import { OutlineMenu } from "@/components/lms/modules/OutlineMenu";
import { PlaceInModuleDialog, type PlaceTarget } from "@/components/lms/modules/AddItemDialog";
import { Badge, Button, ConfirmDialog, Skeleton, cn, focusRing, toast } from "@/components/ui";

const KINDS: { kind: UnsortedKind; key: keyof UnsortedOut }[] = [
  { kind: "assignment", key: "assignments" },
  { kind: "page", key: "pages" },
  { kind: "file", key: "files" },
];

export function UnsortedGroup({ courseId, defaultLang, modules, canEdit, open, onOpenChange, refreshKey = 0, onPlaced, onChanged }: {
  courseId: string;
  defaultLang: Lang;
  /** Live modules (targets of "Move to module…"). */
  modules: ModuleStaffOut[];
  canEdit: boolean;
  /** Expanded state (the Course page opens it from "Add existing items"). */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  refreshKey?: number;
  /** A target went into a module: the outline reloads. */
  onPlaced: (moduleId: string) => void;
  /** A target was deleted (To do counts may change). */
  onChanged?: () => void;
}) {
  const { lang, t } = useTranslation();
  const errorText = useModuleErrorText();
  const router = useRouter();
  const base = `/${lang}/courses/${courseId}`;
  const [data, setData] = useState<UnsortedOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [more, setMore] = useState<UnsortedKind | null>(null);
  const [placing, setPlacing] = useState<PlaceTarget | null>(null);
  const [toDelete, setToDelete] = useState<UnsortedItemOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getUnsorted(courseId));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load, refreshKey]);

  const showMore = async (kind: UnsortedKind, key: keyof UnsortedOut) => {
    const page = data?.[key];
    if (!page?.next_cursor) return;
    setMore(kind);
    try {
      const out = await getUnsorted(courseId, { kind, cursor: page.next_cursor });
      const next = out[key];
      if (next) setData((d) => (d ? { ...d, [key]: { ...next, items: [...(d[key]?.items ?? []), ...next.items] } } : d));
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setMore(null);
    }
  };

  const titleOf = (it: UnsortedItemOut) =>
    (typeof it.title === "string" ? it.title : pickLocalized(it.title, lang, defaultLang)) || t("modules.untitledItem");
  const hrefOf = (it: UnsortedItemOut) => {
    if (it.kind === "page") return withFrom(`${base}/pages/${it.id}`, base);
    if (it.kind === "file") return `${base}/files`;
    if (it.assignment_kind === "quiz" && it.assessment_id) return withFrom(`${base}/assessments/${it.assessment_id}/edit`, base);
    return withFrom(`${base}/assignments/${it.id}`, base);
  };

  const remove = async () => {
    if (!toDelete) return;
    setBusy(true);
    setDeleteError(null);
    try {
      if (toDelete.kind === "assignment") await deleteAssignment(courseId, toDelete.id);
      else if (toDelete.kind === "file") await deleteCourseFile(courseId, toDelete.id);
      else {
        // one row per translation group: every language variant goes to the pages trash
        const ids = toDelete.variants?.length ? toDelete.variants.map((v) => v.id) : [toDelete.id];
        for (const id of ids) await deletePage(courseId, id);
      }
      setToDelete(null);
      await load();
      onChanged?.();
    } catch (e) {
      setDeleteError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const totals = { assignments: data?.assignments?.total ?? 0, pages: data?.pages?.total ?? 0, files: data?.files?.total ?? 0 };
  const total = totals.assignments + totals.pages + totals.files;
  const empty = !!data && total === 0;
  // collapsed when empty on the first load ("Everything is in a module"); the teacher can still open it
  const firstLoad = useRef(true);
  useEffect(() => {
    if (!data || !firstLoad.current) return;
    firstLoad.current = false;
    if (empty) onOpenChange(false);
  }, [data, empty, onOpenChange]);

  const row = (it: UnsortedItemOut) => {
    const name = titleOf(it);
    return (
      <li key={`${it.kind}-${it.id}`} className="flex items-start gap-1 px-2 py-1.5 sm:px-3">
        <ItemKindIcon kind={it.kind} assignmentKind={it.assignment_kind ?? undefined} className="mt-3 h-5 w-5 text-slate-500" />
        <div className="min-w-0 flex-1 py-2 pl-2">
          <Link href={hrefOf(it)} className={cn("break-words rounded text-base font-medium leading-6 text-slate-900 hover:text-brand-700 hover:underline sm:text-sm", focusRing)}>
            {name}
          </Link>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm leading-6 text-slate-600">
            {it.kind === "assignment" && it.assignment_kind && <span>{t(`assignments.kinds.${it.assignment_kind}`)}</span>}
            {it.kind === "file" && it.folder && <span className="break-all">{it.folder}</span>}
            {!it.published && <span>{t("modules.editor.draft")}</span>}
            {it.kind === "page" && (it.variants?.length ? it.variants : it.language ? [{ id: it.id, language: it.language }] : []).map((v) => (
              <Badge key={v.id}>{t(`courses.languages.${v.language}`)}</Badge>
            ))}
          </p>
        </div>
        <OutlineMenu label={t("modules.editor.actionsFor", { title: name })} onSelect={(id) => {
          if (id === "place") setPlacing({ kind: it.kind, id: it.id, title: name });
          else if (id === "open") router.push(hrefOf(it));
          else if (id === "delete") { setDeleteError(null); setToDelete(it); }
        }} groups={[{
          id: "row", items: [
            ...(canEdit ? [{ id: "place", label: t("coursePage.unsorted.moveTo"), disabled: modules.length === 0 }] : []),
            { id: "open", label: t("modules.editor.openTarget") },
            ...(canEdit ? [{ id: "delete", label: t("modules.editor.delete"), danger: true }] : []),
          ],
        }]} />
      </li>
    );
  };

  const sectionId = "unsorted-items";
  return (
    <section id="unsorted" aria-labelledby="unsorted-title" className="scroll-mt-24 rounded-2xl border border-dashed border-slate-300 bg-slate-50/60">
      <div className="flex items-start gap-1 px-2 py-2 sm:px-3">
        <button type="button" aria-expanded={open} aria-controls={sectionId} onClick={() => onOpenChange(!open)}
          aria-label={t("coursePage.toggleModule", { title: t("coursePage.unsorted.title") })}
          className={cn("inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-600 hover:bg-slate-100", focusRing)}>
          <ChevronRight aria-hidden="true" className={cn("h-5 w-5 transition-transform", open && "rotate-90")} />
        </button>
        <div className="min-w-0 flex-1 py-2">
          <h3 id="unsorted-title" className="text-lg font-semibold leading-7 text-slate-900">{t("coursePage.unsorted.title")}</h3>
          <div className="mt-0.5 text-sm leading-6 text-slate-600">
            {!data && !error ? <Skeleton className="h-4 w-40" />
              : empty ? t("coursePage.unsorted.empty")
                : t("coursePage.unsorted.totals", totals)}
          </div>
        </div>
      </div>
      <div id={sectionId} hidden={!open} className="space-y-4 border-t border-slate-200 px-2 pb-4 pt-3 sm:px-3">
        <p className="px-2 text-sm leading-6 text-slate-600">{t("coursePage.unsorted.hint")}</p>
        {error && !data ? (
          <div className="flex flex-wrap items-center gap-3 px-2 text-sm text-danger-800">
            <span role="alert">{errorText(error)}</span>
            <Button size="sm" variant="secondary" onClick={() => void load()}>{t("lms.common.retry")}</Button>
          </div>
        ) : !data ? (
          <div aria-hidden="true" className="space-y-2 px-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
        ) : (
          KINDS.map(({ kind, key }) => {
            const page = data[key] as UnsortedPageOut | null;
            if (!page || page.items.length === 0) return null;
            return (
              <div key={kind} className="rounded-xl border border-slate-200 bg-white">
                <h4 className="px-4 pt-3 text-sm font-semibold uppercase tracking-wide text-slate-600">
                  {t(`coursePage.unsorted.groups.${key}`, { n: page.total })}
                </h4>
                <ul className="divide-y divide-slate-100">{page.items.map(row)}</ul>
                {page.next_cursor && (
                  <div className="px-4 pb-3">
                    <Button variant="link" size="sm" loading={more === kind} onClick={() => void showMore(kind, key)}>{t("coursePage.unsorted.more")}</Button>
                  </div>
                )}
              </div>
            );
          })
        )}
        <div className="flex flex-wrap gap-x-5 px-2">
          <Link href={`${base}/pages`} className={cn("inline-flex min-h-11 items-center rounded text-sm font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
            {t("coursePage.unsorted.allPages")}
          </Link>
          <Link href={`${base}/files`} className={cn("inline-flex min-h-11 items-center rounded text-sm font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
            {t("coursePage.unsorted.allFiles")}
          </Link>
        </div>
      </div>

      {placing && (
        <PlaceInModuleDialog open target={placing} modules={modules} courseId={courseId} defaultLang={defaultLang}
          onClose={() => setPlacing(null)}
          onPlaced={(mid) => { setPlacing(null); toast.success(t("coursePage.unsorted.placed")); void load(); onPlaced(mid); }} />
      )}
      <ConfirmDialog open={!!toDelete} tone="danger" busy={busy} title={t("coursePage.unsorted.deleteTitle")}
        object={toDelete ? titleOf(toDelete) : undefined} effect={t("coursePage.unsorted.deleteBody")}
        confirmLabel={t("modules.editor.delete")} error={deleteError ?? undefined}
        onConfirm={() => void remove()} onCancel={() => setToDelete(null)} />
    </section>
  );
}
