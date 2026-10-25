"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { TemplatePassage } from "@/components/lms/PlainPassage";
import { fmtApiDateTime } from "@/lib/format";
import { MathRenderer } from "@/components/math/MathRenderer";
import { createPassage, getPassageVersion, listPassageVersions, revertPassage, updatePassage } from "@/lib/lms/content";
import type { PassageOut, PassageVersionOut, PassageVersionSummaryOut } from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { Pager } from "@/components/lms/Pager";
import { ContentError } from "./ContentError";
import { ImagePicker } from "./ImagePicker";
import { btnPrimary, btnSecondary, cardCls, inputCls, labelCls } from "./ui";
import type { ImageOut } from "@/lib/lms/contentTypes";

export function PassageEditor({
  courseId, bankId, passage, courseLanguages, defaultLanguage, readOnly, onSaved, onConflict,
}: {
  courseId: string;
  bankId: string;
  passage?: PassageOut;
  courseLanguages: Lang[];
  defaultLanguage: Lang;
  readOnly?: boolean;
  onSaved: (p: PassageOut) => void;
  onConflict: () => void;
}) {
  const { t } = useTranslation();
  const cv = passage?.current_version;
  const [language, setLanguage] = useState<Lang>(cv?.language || defaultLanguage);
  const [title, setTitle] = useState(cv?.title || "");
  const [body, setBody] = useState(cv?.body || "");
  const [image, setImage] = useState<ImageOut | null>(cv?.image || null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    if (cv) { setTitle(cv.title || ""); setBody(cv.body); setImage(cv.image || null); setLanguage(cv.language); }
  }, [cv?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!body.trim()) { setEmpty(true); return; }
    setEmpty(false);
    setSaving(true);
    setError(null);
    try {
      const payload = { title: title.trim() || null, body, image_asset_id: image?.asset_id ?? null };
      const p = passage
        ? await updatePassage(courseId, passage.id, { base_version_id: passage.current_version.id, ...payload })
        : await createPassage(courseId, bankId, { language, ...payload });
      onSaved(p);
    } catch (err) {
      if ((err as { code?: string }).code === "version_conflict") onConflict();
      else setError(err);
    } finally {
      setSaving(false);
    }
  };
  const disabled = saving || !!readOnly;
  return (
    <form onSubmit={save} className="space-y-4">
      <div className={`${cardCls} space-y-4`}>
        {!passage && (
          <div>
            <label className={labelCls} htmlFor="p-lang">{t("bank.editor.language")}</label>
            <select id="p-lang" className={`${inputCls} w-auto`} value={language} disabled={disabled} onChange={(e) => setLanguage(e.target.value as Lang)}>
              {courseLanguages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
            </select>
          </div>
        )}
        <div>
          <label className={labelCls} htmlFor="p-title">{t("bank.passages.title")}</label>
          <input id="p-title" className={inputCls} maxLength={300} disabled={disabled} value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="p-body">{t("bank.passages.body")}</label>
          <textarea id="p-body" rows={14} className={`${inputCls} font-mono`} disabled={disabled} value={body} onChange={(e) => setBody(e.target.value)} />
          <p className="mt-1 text-xs text-slate-500">{t("bank.passages.lineHelp")}</p>
        </div>
        <ImagePicker courseId={courseId} label={t("bank.editor.image")} value={image} disabled={disabled} onChange={setImage} />
      </div>
      {body.trim() && (
        <div className={cardCls}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{t("bank.rich.preview")}</p>
          {title.trim() && <h3 className="mb-2 font-semibold text-slate-900">{title}</h3>}
          {image && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={image.url} alt="" className="mb-3 max-h-72 w-auto rounded-lg" />
          )}
          <TemplatePassage text={body} />
        </div>
      )}
      {empty && <p role="alert" className="text-sm text-red-700">{t("bank.passages.errBody")}</p>}
      <ContentError error={error} />
      {!readOnly && (
        <div className="flex justify-end">
          <button type="submit" disabled={saving} className={btnPrimary}>
            {saving ? t("bank.editor.saving") : passage ? t("lms.common.save") : t("bank.editor.create")}
          </button>
        </div>
      )}
    </form>
  );
}

export function PassageHistory({
  courseId, passage, canEdit, onReverted, onConflict,
}: { courseId: string; passage: PassageOut; canEdit: boolean; onReverted: (p: PassageOut) => void; onConflict: () => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<PassageVersionSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<PassageVersionOut | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revertError, setRevertError] = useState<unknown>(null);
  const currentId = passage.current_version.id;

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listPassageVersions(courseId, passage.id, { cursor: next, limit: 30 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId, passage.id]);
  useEffect(() => { void load(); }, [load, currentId]);

  const revert = async () => {
    if (!selected) return;
    setBusy(true);
    setRevertError(null);
    try {
      const p = await revertPassage(courseId, passage.id, selected.id, { base_version_id: currentId });
      setConfirm(false);
      setSelected(null);
      onReverted(p);
    } catch (e) {
      if ((e as { code?: string }).code === "version_conflict") { setConfirm(false); onConflict(); } else setRevertError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem,1fr]">
      <div>
        <ContentError error={error} onRetry={() => load()} className="mb-2" />
        {loading && items.length === 0 && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
        <ul className="space-y-1.5">
          {items.map((v) => (
            <li key={v.id}>
              <button type="button" onClick={async () => { try { setSelected(await getPassageVersion(courseId, passage.id, v.id)); } catch (e) { setError(e); } }}
                className={`w-full rounded-xl border px-3 py-2 text-left text-sm ${selected?.id === v.id ? "border-brand-400 bg-brand-50" : "border-slate-200 bg-white hover:bg-slate-50"}`}>
                <span className="font-semibold">{t("bank.history.version", { n: v.version_no })}</span>
                {v.id === currentId && <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">{t("bank.history.current")}</span>}
                <span className="block text-xs text-slate-500">{t(`bank.history.origin.${v.origin}`)} · {fmtApiDateTime(v.created_at)}{v.created_by_name ? ` · ${v.created_by_name}` : ""}</span>
              </button>
            </li>
          ))}
        </ul>
        <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      </div>
      <div>
        {!selected && <p className="text-sm text-slate-500">{t("bank.history.pick")}</p>}
        {selected && (
          <div className="space-y-3">
            <div className={cardCls}>
              <h3 className="mb-2 text-sm font-bold text-slate-900">{t("bank.history.selected", { n: selected.version_no })}</h3>
              {selected.title && <p className="mb-1 font-semibold">{selected.title}</p>}
              <MathRenderer content={selected.body} />
            </div>
            {canEdit && selected.id !== currentId && (
              <div className="flex gap-2">
                <button type="button" className={btnPrimary} onClick={() => { setRevertError(null); setConfirm(true); }}>{t("bank.history.revert")}</button>
                <button type="button" className={btnSecondary} onClick={() => setSelected(null)}>{t("lms.common.cancel")}</button>
              </div>
            )}
          </div>
        )}
      </div>
      <ConfirmDialog open={confirm} busy={busy} title={t("bank.history.revertTitle", { n: selected?.version_no ?? 0 })}
        body={t("bank.history.revertBody")} confirmLabel={t("bank.history.revert")}
        onConfirm={() => void revert()} onCancel={() => setConfirm(false)}>
        {revertError ? <ContentError error={revertError} className="mt-3" /> : null}
      </ConfirmDialog>
    </div>
  );
}
