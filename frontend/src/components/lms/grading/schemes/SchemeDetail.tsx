"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Copy, Info } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { addSchemeVersion, deleteScheme, getScheme, restoreScheme, updateSchemeTitle } from "@/lib/lms/grading";
import type { SchemeOut, SchemeParams, SchemeVersionOut } from "@/lib/lms/gradingTypes";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import { LMS_LANGS, type Lang, type LocalizedText } from "@/lib/lms/types";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { fmtDateTime } from "@/components/lms/assessments/format";
import { btnDanger, btnPrimary, btnSecondary, btnSmall, cardCls } from "@/components/lms/content/ui";
import { ScaleText, SchemeBadges } from "./SchemeBadges";
import { SchemeError } from "./SchemeError";
import { SchemeWorkbench } from "./SchemeWorkbench";
import { cleanParams, normalizeParams, stableStringify, validateParams } from "./params";

function currentVersion(s: SchemeOut): SchemeVersionOut | null {
  return s.versions.find((v) => v.id === s.current_version?.id)
    ?? [...s.versions].sort((a, b) => b.version_no - a.version_no)[0]
    ?? null;
}

/**
 * One scheme: title, versions, editor + preview. Editing is offered for the owner's live schemes only;
 * system and deleted schemes are read-only (the server enforces it either way).
 */
export function SchemeDetail({ schemeId }: { schemeId: string }) {
  const { lang, t } = useTranslation();
  const { me } = useLmsMe();
  const [scheme, setScheme] = useState<SchemeOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [baseId, setBaseId] = useState<string | null>(null);
  const [params, setParams] = useState<SchemeParams | null>(null);
  const [title, setTitle] = useState<LocalizedText>({});
  const [busy, setBusy] = useState<"" | "title" | "version" | "delete" | "restore">("");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const baseRef = useRef<string | null>(null);
  const showVersion = useCallback((v: SchemeVersionOut | null) => {
    baseRef.current = v?.id ?? null;
    setBaseId(baseRef.current);
    setParams(v ? normalizeParams(v.params) : null);
  }, []);

  /** Take a fresh server copy; `keepBase` keeps the version shown in the editor (title/delete/restore). */
  const apply = useCallback((s: SchemeOut, keepBase = false) => {
    setScheme(s);
    setTitle(s.title);
    const kept = keepBase ? s.versions.find((v) => v.id === baseRef.current) : undefined;
    if (!kept) showVersion(currentVersion(s));
  }, [showVersion]);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      apply(await getScheme(schemeId));
    } catch (e) {
      setLoadError(e);
    }
  }, [schemeId, apply]);

  useEffect(() => { void load(); }, [load]);

  const cur = scheme ? currentVersion(scheme) : null;
  const base = scheme?.versions.find((v) => v.id === baseId) ?? cur;
  const type = scheme?.type ?? "percent";
  const cleaned = useMemo(() => (params ? cleanParams(type, params) : null), [type, params]);
  const issues = useMemo(() => (cleaned ? validateParams(type, cleaned) : []), [type, cleaned]);
  const unchanged = useMemo(
    () => !!(cleaned && cur && stableStringify(cleaned) === stableStringify(cleanParams(type, normalizeParams(cur.params)))),
    [cleaned, cur, type],
  );

  if (loadError) return <SchemeError error={loadError} onRetry={load} />;
  if (!scheme || !params) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;

  const canWrite = scheme.is_mine && !scheme.is_system && !!me?.can_create_courses;
  const editable = canWrite && !scheme.deleted_at;
  const name = pickLocalized(scheme.title, lang as Lang) || t("schemes.library.untitled");
  const versions = [...scheme.versions].sort((a, b) => b.version_no - a.version_no);

  const run = async (kind: typeof busy, fn: () => Promise<void>) => {
    setBusy(kind);
    setError(null);
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy("");
    }
  };

  const saveTitle = () => run("title", async () => {
    const clean = cleanLocalized(title, LMS_LANGS);
    if (!Object.keys(clean).length) throw { code: "title_required" };
    apply(await updateSchemeTitle(scheme.id, clean), true);
    setNotice(t("schemes.editor.titleSaved"));
  });

  const saveVersion = () => run("version", async () => {
    if (!cleaned || issues.length) return;
    const v = await addSchemeVersion(scheme.id, cleaned);
    apply(await getScheme(scheme.id));
    setNotice(t("schemes.editor.versionSaved", { n: v.version_no }));
  });

  const doDelete = () => run("delete", async () => {
    await deleteScheme(scheme.id);
    setConfirmDelete(false);
    apply(await getScheme(scheme.id), true);
  });

  const doRestore = () => run("restore", async () => {
    apply(await restoreScheme(scheme.id), true);
  });

  return (
    <div className="space-y-5">
      <Link href={`/${lang}/grading-schemes`} className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("schemes.editor.back")}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <h1 className="break-words text-2xl font-bold text-slate-900">{name}</h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
            <SchemeBadges scheme={scheme} />
            {cur && <span>{t("schemes.library.version", { n: cur.version_no })}</span>}
            {cur && <ScaleText min={cur.scale_min} max={cur.scale_max} />}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {me?.can_create_courses && (
            <Link href={`/${lang}/grading-schemes/new?from=${encodeURIComponent(scheme.id)}${base ? `&version=${encodeURIComponent(base.id)}` : ""}`}
              className={`${btnSecondary} inline-flex items-center gap-1.5`}>
              <Copy className="h-4 w-4" aria-hidden="true" />{t("schemes.editor.duplicate")}
            </Link>
          )}
          {editable && (
            <button type="button" className={btnDanger} disabled={!!busy} onClick={() => setConfirmDelete(true)}>{t("schemes.editor.delete")}</button>
          )}
        </div>
      </div>

      {scheme.is_system && (
        <p className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-100 px-3.5 py-3 text-sm text-slate-700">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />{t("schemes.editor.systemReadOnly")}
        </p>
      )}
      {scheme.deleted_at && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">
          <span>{t("schemes.editor.deletedBanner")}</span>
          {canWrite && (
            <button type="button" className={btnSecondary} disabled={!!busy} onClick={doRestore}>
              {busy === "restore" ? t("lms.common.loading") : t("schemes.editor.restore")}
            </button>
          )}
        </div>
      )}

      {editable && (
        <div className={`${cardCls} space-y-3`}>
          <LocalizedTextInput label={t("schemes.editor.title")} languages={LMS_LANGS} defaultLanguage={lang as Lang}
            value={title} onChange={setTitle} maxLength={200} required disabled={!!busy} />
          <button type="button" className={btnSecondary} disabled={!!busy || stableStringify(cleanLocalized(title, LMS_LANGS)) === stableStringify(cleanLocalized(scheme.title, LMS_LANGS))}
            onClick={saveTitle}>
            {busy === "title" ? t("lms.common.loading") : t("schemes.editor.saveTitle")}
          </button>
        </div>
      )}

      <details className={cardCls}>
        <summary className="cursor-pointer text-sm font-semibold text-slate-900">{t("schemes.editor.versions", { n: versions.length })}</summary>
        <ul className="mt-3 divide-y divide-slate-100">
          {versions.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-semibold text-slate-900">{t("schemes.library.version", { n: v.version_no })}</span>
                {v.id === cur?.id && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">{t("schemes.editor.current")}</span>}
                {v.id === base?.id && v.id !== cur?.id && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">{t("schemes.editor.shown")}</span>}
                <span className="text-xs text-slate-500">{fmtDateTime(v.created_at)}</span>
                <span className="text-xs text-slate-500">{t("schemes.editor.inUse", { n: v.in_use_count })}</span>
              </span>
              {v.id !== base?.id && (
                <button type="button" className={btnSmall} onClick={() => { showVersion(v); setNotice(""); }}>
                  {editable ? t("schemes.editor.loadVersion") : t("schemes.editor.showVersion")}
                </button>
              )}
            </li>
          ))}
        </ul>
      </details>

      <SchemeWorkbench type={type} params={params} onChange={setParams} issues={issues} readOnly={!editable || !!busy} />

      {error ? <SchemeError error={error} /> : null}
      {notice && <p role="status" className="text-sm font-medium text-emerald-700">{notice}</p>}

      {editable && cur && (
        <div className={`${cardCls} space-y-3`}>
          <p className="flex items-start gap-2 text-sm text-slate-700">
            <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand-600" aria-hidden="true" />
            {t("schemes.editor.versionNotice", { next: cur.version_no + 1, current: cur.version_no })}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className={btnPrimary} disabled={!!busy || issues.length > 0 || unchanged} onClick={saveVersion}>
              {busy === "version" ? t("schemes.editor.saving") : t("schemes.editor.saveVersion")}
            </button>
            {unchanged && <span className="text-xs text-slate-500">{t("schemes.editor.unchanged")}</span>}
          </div>
        </div>
      )}

      <ConfirmDialog open={confirmDelete} title={t("schemes.editor.deleteTitle", { name })} body={t("schemes.editor.deleteBody")}
        confirmLabel={t("schemes.editor.delete")} danger busy={busy === "delete"} error={busy ? null : error}
        onConfirm={doDelete} onCancel={() => setConfirmDelete(false)} />
    </div>
  );
}
