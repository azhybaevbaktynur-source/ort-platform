"use client";

import React, { useEffect, useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { BankOut } from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";
import { ContentError } from "./ContentError";
import { btnPrimary, btnSecondary, inputCls, labelCls } from "./ui";

/** Create or rename a bank. */
export function BankDialog({
  open, bank, courseLanguages, busy, error, onSubmit, onCancel,
}: {
  open: boolean;
  bank: BankOut | null;
  courseLanguages: Lang[];
  busy: boolean;
  error: unknown;
  onSubmit: (v: { title: string; description: string | null; default_language: Lang | null }) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [lang, setLang] = useState<Lang | "">("");
  useEffect(() => {
    if (open) { setTitle(bank?.title || ""); setDescription(bank?.description || ""); setLang(bank?.default_language || ""); }
  }, [open, bank]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <form role="dialog" aria-modal="true" aria-labelledby={`${id}-t`} className="w-full max-w-md space-y-3 rounded-2xl bg-white p-6 shadow-xl"
        onSubmit={(e) => { e.preventDefault(); if (title.trim()) onSubmit({ title: title.trim(), description: description.trim() || null, default_language: lang || null }); }}>
        <h2 id={`${id}-t`} className="text-lg font-bold text-slate-900">{bank ? t("bank.list.renameTitle") : t("bank.list.createTitle")}</h2>
        <div>
          <label className={labelCls} htmlFor={`${id}-title`}>{t("bank.list.titleLabel")}</label>
          <input id={`${id}-title`} autoFocus required maxLength={200} className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor={`${id}-desc`}>{t("bank.list.descriptionLabel")}</label>
          <textarea id={`${id}-desc`} rows={3} className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor={`${id}-lang`}>{t("bank.list.defaultLanguage")}</label>
          <select id={`${id}-lang`} className={inputCls} value={lang} onChange={(e) => setLang(e.target.value as Lang | "")}>
            <option value="">{t("bank.editor.none")}</option>
            {courseLanguages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
          </select>
        </div>
        <ContentError error={error} />
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" disabled={busy} className={btnSecondary} onClick={onCancel}>{t("lms.common.cancel")}</button>
          <button type="submit" disabled={busy || !title.trim()} className={btnPrimary}>{busy ? t("lms.common.loading") : t("lms.common.save")}</button>
        </div>
      </form>
    </div>
  );
}
