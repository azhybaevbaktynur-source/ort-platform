"use client";

// Phase 8c S2 (PHASE_8C_DESIGN §3.4): live assignments (quizzes included), pages (one row per translation group) and
// course files that no live item of a live module references (`GET _C/modules/unsorted`, S1): 20 rows per kind with
// "Show more". UX rework D (UR-4): one collapsed row at the end of the outline, "Not in modules · N", absent when N = 0;
// expanded, a flat list of one-line rows (kind icon, title, kind text, "⋯" with Move to module, Edit, Delete).
import React, { useCallback, useEffect, useState } from "react";
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
import { ItemKindIcon, useItemKindText, useModuleErrorText } from "@/components/lms/modules/moduleUi";
import { OutlineMenu } from "@/components/lms/modules/OutlineMenu";
import { PlaceInModuleDialog, type PlaceTarget } from "@/components/lms/modules/AddItemDialog";
import { Button, ConfirmDialog, cn, focusRing, toast } from "@/components/ui";

const KINDS: { kind: UnsortedKind; key: keyof UnsortedOut }[] = [
  { kind: "assignment", key: "assignments" },
  { kind: "page", key: "pages" },
  { kind: "file", key: "files" },
];

export function UnsortedGroup({ courseId, defaultLang, modules, canEdit, refreshKey = 0, onPlaced, onChanged }: {
  courseId: string;
  defaultLang: Lang;
  /** Live modules (targets of "Move to module…"). */
  modules: ModuleStaffOut[];
  canEdit: boolean;
  refreshKey?: number;
  /** A target went into a module: the outline reloads. */
  onPlaced: (moduleId: string) => void;
  /** A target was deleted (the "to grade" count may change). */
  onChanged?: () => void;
}) {
  const { lang, t } = useTranslation();
  const errorText = useModuleErrorText();
  const kindText = useItemKindText();
  const router = useRouter();
  const base = `/${lang}/courses/${courseId}`;
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<UnsortedOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [more, setMore] = useState(false);
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

  const pageOf = (d: UnsortedOut, key: keyof UnsortedOut) => d[key] as UnsortedPageOut | null | undefined;
  /** "Show more" continues every kind that has more rows. */
  const showMore = async () => {
    if (!data) return;
    setMore(true);
    try {
      const pending = KINDS.filter(({ key }) => pageOf(data, key)?.next_cursor);
      const pages = await Promise.all(pending.map(({ kind, key }) => getUnsorted(courseId, { kind, cursor: pageOf(data, key)!.next_cursor })));
      setData((d) => {
        if (!d) return d;
        const next: UnsortedOut = { ...d };
        pending.forEach(({ key }, i) => {
          const page = pageOf(pages[i], key);
          if (page) Object.assign(next, { [key]: { ...page, items: [...(pageOf(d, key)?.items ?? []), ...page.items] } });
        });
        return next;
      });
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setMore(false);
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

  const total = (data?.assignments?.total ?? 0) + (data?.pages?.total ?? 0) + (data?.files?.total ?? 0);
  if (!data || total === 0) {
    if (!error || data) return null;
    return (
      <div className="flex flex-wrap items-center gap-3 px-1 text-sm text-danger-800">
        <span role="alert">{errorText(error)}</span>
        <Button size="sm" variant="secondary" onClick={() => void load()}>{t("lms.common.retry")}</Button>
      </div>
    );
  }

  const row = (it: UnsortedItemOut) => {
    const name = titleOf(it);
    const languages = it.kind === "page" ? (it.variants?.length ? it.variants : it.language ? [{ id: it.id, language: it.language }] : []) : [];
    const tip = [name, it.kind === "file" ? it.folder : "", ...languages.map((v) => t(`courses.languages.${v.language}`))].filter(Boolean).join(" · ");
    return (
      <li key={`${it.kind}-${it.id}`} className="flex min-h-11 items-center gap-1 px-1 sm:px-2">
        <ItemKindIcon kind={it.kind} assignmentKind={it.assignment_kind ?? undefined} className="ml-1 h-4 w-4 text-slate-500" />
        <div className="min-w-0 flex-1 py-1.5 pl-2 sm:flex sm:items-center sm:gap-3" title={tip}>
          <Link href={hrefOf(it)} className={cn("block break-words rounded text-base font-medium leading-6 text-slate-900 hover:text-brand-700 hover:underline sm:truncate sm:text-sm", focusRing)}>
            {name}
          </Link>
          <p className="flex flex-wrap items-center gap-x-2 text-sm leading-5 text-slate-600 sm:shrink-0">
            <span>{kindText(it.kind, it.assignment_kind)}</span>
            {!it.published && <span>{t("modules.editor.draft")}</span>}
          </p>
        </div>
        <OutlineMenu label={t("modules.editor.actionsFor", { title: name })} onSelect={(id) => {
          if (id === "place") setPlacing({ kind: it.kind, id: it.id, title: name });
          else if (id === "open") router.push(hrefOf(it));
          else if (id === "delete") { setDeleteError(null); setToDelete(it); }
        }} groups={[{
          id: "row", items: [
            ...(canEdit ? [{ id: "place", label: t("coursePage.unsorted.moveTo"), disabled: modules.length === 0 }] : []),
            { id: "open", label: t("coursePage.unsorted.edit") },
            ...(canEdit ? [{ id: "delete", label: t("modules.editor.delete"), danger: true }] : []),
          ],
        }]} />
      </li>
    );
  };

  const sectionId = "unsorted-items";
  const rows = KINDS.flatMap(({ key }) => pageOf(data, key)?.items ?? []);
  const hasMore = KINDS.some(({ key }) => pageOf(data, key)?.next_cursor);
  return (
    <section id="unsorted" aria-labelledby="unsorted-title" className="scroll-mt-24 rounded-xl border border-slate-200 bg-white">
      <h3 id="unsorted-title">
        <button type="button" aria-expanded={open} aria-controls={sectionId} onClick={() => setOpen((o) => !o)} title={t("coursePage.unsorted.hint")}
          className={cn("flex min-h-11 w-full items-center gap-1 rounded-xl px-1 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50 sm:px-2", focusRing)}>
          <span aria-hidden="true" className="inline-flex h-11 w-9 shrink-0 items-center justify-center text-slate-600">
            <ChevronRight className={cn("h-5 w-5 transition-transform", open && "rotate-90")} />
          </span>
          {t("coursePage.unsorted.row", { n: total })}
        </button>
      </h3>
      <div id={sectionId} hidden={!open} className="border-t border-slate-200">
        <ul className="divide-y divide-slate-100">{rows.map(row)}</ul>
        {hasMore && (
          <div className="border-t border-slate-100 px-3 py-1">
            <Button variant="link" size="sm" loading={more} onClick={() => void showMore()}>{t("coursePage.unsorted.more")}</Button>
          </div>
        )}
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
