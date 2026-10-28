"use client";

// Phase 8a S4b: page editor (design 8.1): title, language, Markdown with toolbar and server preview, language variants,
// publish switch and optimistic `rev` (stale save -> 409 `page_conflict` -> conflict dialog).
import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { createPage, getPage, updatePage } from "@/lib/lms/pages";
import { PAGE_BODY_MAX, isStaffPage, type PageStaffOut } from "@/lib/lms/pagesTypes";
import type { Lang } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { Badge, Button, Dialog, LoadingState, PageHeader, Select, Switch, toast, Input } from "@/components/ui";
import { ContentError } from "./ApiError";
import { MarkdownField } from "./MarkdownField";

const isLang = (v: string | null, langs: Lang[]): v is Lang => !!v && (langs as string[]).includes(v);

export function PageEditor({ pageId }: { pageId?: string }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const search = useSearchParams();
  const base = `/${lang}/courses/${course.id}`;
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

  const apply = useCallback((p: PageStaffOut) => {
    setPage(p); setTitle(p.title); setBody(p.body_md); setPublished(p.published); setLanguage(p.language as Lang); setDirty(false);
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
        router.replace(`${base}/pages/${p.id}/edit`);
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
      setPage(p); setPublished(p.published);
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

  return (
    <div className="max-w-4xl">
      <PageHeader
        title={page ? t("pages.editor.editTitle") : t("pages.editor.newTitle")}
        breadcrumbs={[{ label: t("pages.title"), href: `${base}/pages` }, { label: page ? page.title : t("pages.editor.newTitle") }]}
        badge={page ? <Badge tone={page.published ? "success" : "neutral"}>{t(page.published ? "pages.published" : "pages.draft")}</Badge> : undefined}
        secondaryActions={page ? <Link href={`${base}/pages/${page.id}`} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline">{t("pages.editor.viewPage")}</Link> : undefined}
        primaryAction={<Button onClick={() => void save()} loading={saving} disabled={!canSave}>{t("common.save")}</Button>}
      />
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
              <li><Badge tone="info">{langName(page.language)}</Badge></li>
              {page.variants.map((v) => (
                <li key={v.id}>
                  <Link href={`${base}/pages/${v.id}/edit`} className="inline-flex min-h-11 items-center rounded-full border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50">
                    {langName(v.language)}
                  </Link>
                </li>
              ))}
              {missingLangs.map((l) => (
                <li key={l}>
                  <Link href={`${base}/pages/new?lang=${l}&group=${page.translation_group_id}`} className="inline-flex min-h-11 items-center gap-1 rounded-full border border-dashed border-slate-400 px-3 text-sm font-medium text-brand-700 hover:bg-brand-50">
                    <Plus className="h-4 w-4" aria-hidden="true" />{t("pages.editor.addVariant", { language: langName(l) })}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        <MarkdownField courseId={course.id} label={t("pages.editor.fieldBody")} value={body} max={PAGE_BODY_MAX} onChange={(v) => { setBody(v); setDirty(true); }} />
        <div className="flex justify-end">
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
