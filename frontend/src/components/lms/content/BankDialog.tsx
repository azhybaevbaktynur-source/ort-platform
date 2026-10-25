"use client";

import React, { useEffect, useId, useState } from "react";
import { Button, Dialog } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import type { BankOut } from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";
import { ContentError } from "./ContentError";
import { inputCls, labelCls } from "./ui";

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
  // Phase 6b S5c: design-system Dialog (focus trap, Esc, focus return).
  return (
    <Dialog open={open} onClose={onCancel} busy={busy} closeOnBackdrop={false} title={bank ? t("bank.list.renameTitle") : t("bank.list.createTitle")}>
      <form className="space-y-3"
        onSubmit={(e) => { e.preventDefault(); if (title.trim()) onSubmit({ title: title.trim(), description: description.trim() || null, default_language: lang || null }); }}>
        <div>
          <label className={labelCls} htmlFor={`${id}-title`}>{t("bank.list.titleLabel")}</label>
          <input id={`${id}-title`} required maxLength={200} className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
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
        <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" disabled={busy} onClick={onCancel}>{t("lms.common.cancel")}</Button>
          <Button type="submit" loading={busy} disabled={!title.trim()}>{t("lms.common.save")}</Button>
        </div>
      </form>
    </Dialog>
  );
}
