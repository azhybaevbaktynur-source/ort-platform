"use client";

import React, { useEffect, useId, useState } from "react";
import { Button, Dialog, LinkButton, Select } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { copyToBank, getQuestionUsage, listBanks } from "@/lib/lms/content";
import type { BankOut } from "@/lib/lms/contentTypes";
import { ContentError } from "./ContentError";

const KNOWN = ["target_not_shared_bank", "question_has_passage", "quiz_bank_follows_quiz", "source_conflict"];

/** Move or copy a quiz-bank question to a shared bank of the same course (Phase 7c S4). */
export function MoveToBankDialog({
  open, courseId, questionId, banksHref, onDone, onCancel,
}: {
  open: boolean;
  courseId: string;
  questionId: string | null;
  banksHref: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [banks, setBanks] = useState<BankOut[] | null>(null);
  const [target, setTarget] = useState("");
  const [mode, setMode] = useState<"move" | "copy">("move");
  const [usage, setUsage] = useState<number>(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!open || !questionId) return;
    let live = true;
    setBanks(null); setTarget(""); setMode("move"); setUsage(0); setError(null);
    listBanks(courseId, { kind: "shared", limit: 100 }).then((p) => { if (live) setBanks(p.items); }).catch((e) => { if (live) { setBanks([]); setError(e); } });
    getQuestionUsage(courseId, questionId).then((u) => { if (live) setUsage(u.other_count); }).catch(() => {});
    return () => { live = false; };
  }, [open, courseId, questionId]);

  const submit = async () => {
    if (!questionId || !target) return;
    setBusy(true);
    setError(null);
    try {
      await copyToBank(courseId, questionId, { bank_id: target, mode });
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const code = (error as { code?: string } | null)?.code;
  const known = !!code && KNOWN.includes(code);
  const empty = banks !== null && banks.length === 0 && !error;
  const radio = (v: "move" | "copy") => (
    <label className="flex min-h-[44px] cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3 has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50">
      <input type="radio" name={`${id}-mode`} value={v} checked={mode === v} onChange={() => setMode(v)} className="mt-1 h-4 w-4" />
      <span>
        <span className="block text-sm font-semibold text-slate-900">{t(`bank.moveToBank.${v}`)}</span>
        <span className="block text-sm text-slate-600">{t(`bank.moveToBank.${v}Hint`)}</span>
      </span>
    </label>
  );

  return (
    <Dialog open={open} onClose={onCancel} busy={busy} closeOnBackdrop={false} title={t("bank.moveToBank.title")}>
      {empty ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-700">{t("bank.moveToBank.noShared")}</p>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={onCancel}>{t("lms.common.cancel")}</Button>
            <LinkButton href={banksHref}>{t("bank.moveToBank.createBank")}</LinkButton>
          </div>
        </div>
      ) : (
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <Select label={t("bank.moveToBank.target")} placeholder={t("bank.moveToBank.choose")} value={target} disabled={banks === null || busy}
            onChange={(e) => setTarget(e.target.value)} options={(banks ?? []).map((b) => ({ value: b.id, label: b.title }))} />
          <fieldset className="space-y-2" disabled={busy}>
            <legend className="mb-1 text-sm font-medium text-slate-700">{t("bank.moveToBank.mode")}</legend>
            {radio("move")}
            {radio("copy")}
          </fieldset>
          {usage > 0 && <p className="text-sm text-slate-600">{t("bank.moveToBank.usageNote", { count: usage })}</p>}
          {known ? <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">{t(`bank.moveToBank.errors.${code}`)}</p> : <ContentError error={error} />}
          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="secondary" disabled={busy} onClick={onCancel}>{t("lms.common.cancel")}</Button>
            <Button type="submit" loading={busy} disabled={!target}>{t("bank.moveToBank.submit")}</Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
