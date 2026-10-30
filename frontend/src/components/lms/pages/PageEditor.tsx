"use client";

// Phase 8a S4b: page editor (design 8.1): title, language, Markdown with toolbar and server preview, language variants,
// publish switch and optimistic `rev` (stale save -> 409 `page_conflict` -> conflict dialog).
// Phase 8c S3 (PHASE_8C_DESIGN §5.2, §5.3): the Edit tab of the page object (`embedded`: no header of its own, the
// object page shows the title through `onPage`), and the creation route `/pages/new` with `?module=` (the new page
// is added to that module right after it is created) and `?from=` (Back, carried over to the object page).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { createPage, getPage, updatePage } from "@/lib/lms/pages";
import { addItem } from "@/lib/lms/modules";
import { PAGE_BODY_MAX, isStaffPage, type PageStaffOut } from "@/lib/lms/pagesTypes";
import type { Lang } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { Badge, Button, Dialog, LoadingState, PageHeader, Select, Switch, toast, Input } from "@/components/ui";
import { BackLink, maybeFrom, useObjectNav } from "@/components/lms/assignments/objectNav";
import { ContentError } from "./ApiError";
import { MarkdownField } from "./MarkdownField";
import { LangChip } from "./LangChip";

const isLang = (v: string | null, langs: Lang[]): v is Lang => !!v && (langs as string[]).includes(v);

export function PageEditor({ pageId, embedded = false, onPage }: {
  pageId?: string;
  /** Inside the page object: no header (the object page has the title, the badge and Back). */
  embedded?: boolean;
  /** The page as loaded or saved (title and published state for the object page's header). */
  onPage?: (p: PageStaffOut) => void;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const search = useSearchParams();
  const base = `/${lang}/courses/${course.id}`;
  const nav = useObjectNav(); // Back: the validated `?from=`, else the Course page
  const moduleId = search.get("module");
  const langName = useCallback((l: string) => t(`pages.lang.${l}`), [t]);

  const [page, setPage] = useState<PageStaffOut | null>(null);
  const [loading, setLoading] = useState(!!pageId);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [language, setLanguage] = useState<Lang>(() => {
    const q = search.get("lang");
    return isLang(q, course.languages) ? q : course.default_language;
  });
  const [published, setPublished] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [conflict, setConflict] = useState(false);
  const [dirty, setDirty] = useState(false);
  const group = search.get("group");

  const onPageRef = useRef(onPage);
  onPageRef.current = onPage;
  const apply = useCallback((p: PageStaffOut) => {
    setPage(p); setTitle(p.title); setBody(p.body_md); setPublished(p.published); setLanguage(p.language as Lang); setDirty(false);
    onPageRef.current?.(p);
  }, []);

  useEffect(() => {
    if (!pageId) return;
    let live = true;
    setLoading(true);
    getPage(course.id, pageId)
      .then((p) => { if (live && isStaffPage(p)) apply(p); })
      .catch((e) => { if (live) setLoadError(e); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [course.id, pageId, apply]);

  useEffect(() => {
    if (!dirty) return;
    const h = (ev: BeforeUnloadEvent) => { ev.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const usedLangs = useMemo(() => new Set([page?.language, ...(page?.variants ?? []).map((v) => v.language)]), [page]);
  const missingLangs = course.languages.filter((l) => !usedLangs.has(l));
  const overLimit = body.length > PAGE_BODY_MAX;
  const canSave = title.trim().length > 0 && !overLimit && !saving;

  const save = async (overrideRev?: number) => {
    if (!canSave) return;
    setSaving(true); setError(null);
    try {
      if (!page) {
        const p = await createPage(course.id, {
          title: title.trim(), language, body_md: body, published, translation_group_id: group || null,
        });
        setDirty(false);
        toast.success(t("pages.editor.saved"));
        if (moduleId) {
          // Phase 8c S3: "+ Add > Page" in a module. The page exists either way; a refused item is reported, not fatal.
          try {
            await addItem(course.id, moduleId, { kind: "page", page_id: p.id });
          } catch {
            toast.error(t("pages.object.addToModuleFailed"));
          }
        }
        router.replace(maybeFrom(`${base}/pages/${p.id}?tab=edit`, nav.from));
        return;
      }
      const p = await updatePage(course.id, page.id, { rev: overrideRev ?? page.rev, title: title.trim(), body_md: body, published });
      apply(p);
      toast.success(t("pages.editor.saved"));
    } catch (e) {
      if ((e as { code?: string }).code === "page_conflict") setConflict(true);
      else setError(e);
    } finally {
      setSaving(false);
    }
  };

  const togglePublished = async (next: boolean) => {
    if (!page) { setPublished(next); return; }
    setSaving(true); setError(null);
    try {
      const p = await updatePage(course.id, page.id, { rev: page.rev, published: next });
      setPage(p); setPublished(p.published); onPageRef.current?.(p);
      toast.success(t(next ? "pages.editor.publishedOn" : "pages.editor.publishedOff"));
    } catch (e) {
      if ((e as { code?: string }).code === "page_conflict") setConflict(true);
      else setError(e);
    } finally {
      setSaving(false);
    }
  };

  const reloadLatest = async () => {
    if (!page) return;
    try { const p = await getPage(course.id, page.id); if (isStaffPage(p)) apply(p); setConflict(false); }
    catch (e) { setConflict(false); setError(e); }
  };
  const overwrite = async () => {
    if (!page) return;
    try {
      const p = await getPage(course.id, page.id);
      setConflict(false);
      if (isStaffPage(p)) await save(p.rev);
    } catch (e) { setConflict(false); setError(e); }
  };

  if (loading) return <LoadingState />;
  if (loadError) return <ContentError error={loadError} />;

  const saveButton = <Button onClick={() => void save()} loading={saving} disabled={!canSave}>{t("common.save")}</Button>;
  return (
    <div className="max-w-4xl">
      {embedded ? (
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end [&>*]:w-full sm:[&>*]:w-auto">
          {dirty && <p role="status" className="text-sm text-slate-600 sm:mr-auto">{t("pages.object.unsaved")}</p>}
          {saveButton}
        </div>
      ) : (
        <>
          <BackLink nav={nav} />
          <PageHeader
            title={page ? t("pages.editor.editTitle") : t("pages.editor.newTitle")}
            badge={page ? <Badge tone={page.published ? "success" : "neutral"}>{t(page.published ? "pages.published" : "pages.draft")}</Badge> : undefined}
            primaryAction={saveButton}
          />
        </>
      )}
      <div className="space-y-5">
        <ContentError error={error} />
        <Input label={t("pages.editor.fieldTitle")} value={title} maxLength={300} onChange={(ev) => { setTitle(ev.target.value); setDirty(true); }} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label={t("pages.editor.fieldLanguage")}
            value={language}
            disabled={!!page || !!group}
            hint={page ? t("pages.editor.languageFixed") : undefined}
            onChange={(ev) => setLanguage(ev.target.value as Lang)}
            options={course.languages.map((l) => ({ value: l, label: langName(l) }))}
          />
          <Switch label={t("pages.editor.fieldPublished")} hint={page ? t("pages.editor.publishedHintNow") : t("pages.editor.publishedHint")} checked={published} busy={saving} onChange={(v) => void togglePublished(v)} />
        </div>

        {page && (page.variants.length > 0 || missingLangs.length > 0) && (
          <section aria-label={t("pages.editor.variants")}>
            <h2 className="text-sm font-medium text-slate-800">{t("pages.editor.variants")}</h2>
            <ul className="mt-2 flex flex-wrap gap-2">
              <li><LangChip label={langName(page.language)} selected /></li>
              {page.variants.map((v) => (
                <li key={v.id}><LangChip label={langName(v.language)} href={maybeFrom(`${base}/pages/${v.id}?tab=edit`, nav.from)} /></li>
              ))}
              {missingLangs.map((l) => (
                <li key={l}>
                  <Link href={maybeFrom(`${base}/pages/new?lang=${l}&group=${page.translation_group_id}`, nav.from)} className="inline-flex min-h-11 items-center gap-1 rounded-full border border-dashed border-slate-400 px-3 text-sm font-medium text-brand-700 hover:bg-brand-50">
                    <Plus className="h-4 w-4" aria-hidden="true" />{t("pages.editor.addVariant", { language: langName(l) })}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        <MarkdownField courseId={course.id} label={t("pages.editor.fieldBody")} value={body} max={PAGE_BODY_MAX} onChange={(v) => { setBody(v); setDirty(true); }} />
        {/* Phase 8c UX m6: a sticky footer Save, so a long body never hides the action */}
        <div className="sticky bottom-0 z-10 -mx-4 flex flex-col gap-2 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:mx-0 sm:flex-row sm:items-center sm:justify-end sm:rounded-xl sm:px-3 [&>button]:w-full sm:[&>button]:w-auto">
          {dirty && <p className="text-sm text-slate-600 sm:mr-auto">{t("pages.object.unsaved")}</p>}
          <Button onClick={() => void save()} loading={saving} disabled={!canSave}>{t("common.save")}</Button>
        </div>
      </div>

      <Dialog
        open={conflict}
        onClose={() => setConflict(false)}
        title={t("pages.conflict.title")}
        description={t("pages.conflict.body")}
        footer={<>
          <Button variant="secondary" onClick={() => setConflict(false)}>{t("pages.conflict.keep")}</Button>
          <Button variant="secondary" onClick={() => void overwrite()}>{t("pages.conflict.overwrite")}</Button>
          <Button onClick={() => void reloadLatest()}>{t("pages.conflict.reload")}</Button>
        </>}
      />
    </div>
  );
}
