"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { createBank, deleteBank, listBanks, restoreBank, updateBank } from "@/lib/lms/content";
import type { BankOut } from "@/lib/lms/contentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { Pager } from "@/components/lms/Pager";
import { BankDialog } from "@/components/lms/content/BankDialog";
import { ContentError } from "@/components/lms/content/ContentError";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { btnPrimary, btnSecondary, btnSmall } from "@/components/lms/content/ui";

export default function BankListPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const base = `/${lang}/courses/${course.id}/bank`;
  const [trash, setTrash] = useState(false);
  const [items, setItems] = useState<BankOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<{ bank: BankOut | null } | null>(null);
  const [toDelete, setToDelete] = useState<BankOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listBanks(course.id, { deleted: trash, cursor: next, limit: 50 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, trash]);
  useEffect(() => { void load(); }, [load]);

  const submit = async (v: { title: string; description: string | null; default_language: BankOut["default_language"] }) => {
    setBusy(true);
    setActionError(null);
    try {
      if (dialog?.bank) await updateBank(course.id, dialog.bank.id, v);
      else await createBank(course.id, v);
      setDialog(null);
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!toDelete) return;
    setBusy(true);
    setActionError(null);
    try {
      await deleteBank(course.id, toDelete.id);
      setToDelete(null);
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  const restore = async (b: BankOut) => {
    setActionError(null);
    try {
      await restoreBank(course.id, b.id);
      await load();
    } catch (e) {
      setActionError(e);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold text-slate-900">{t("bank.list.title")}</h2>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btnSecondary} onClick={() => setTrash((s) => !s)}>{trash ? t("bank.list.hideTrash") : t("bank.list.showTrash")}</button>
          {canEdit && <Link href={`${base}/import`} className={btnSecondary}>{t("bank.list.import")}</Link>}
          {canEdit && <button type="button" className={btnPrimary} onClick={() => { setActionError(null); setDialog({ bank: null }); }}>{t("bank.list.create")}</button>}
        </div>
      </div>
      <ContentError error={error || (!dialog && !toDelete ? actionError : null)} onRetry={error ? () => load() : undefined} />
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && <p className="text-sm text-slate-500">{trash ? t("bank.list.emptyTrash") : t("bank.list.empty")}</p>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((b) => (
          <li key={b.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex-1">
              {b.deleted_at ? (
                <h3 className="font-semibold text-slate-900">{b.title}</h3>
              ) : (
                <Link href={`${base}/${b.id}`} className="font-semibold text-slate-900 hover:text-brand-700">{b.title}</Link>
              )}
              {b.description && <p className="mt-1 line-clamp-2 text-sm text-slate-600">{b.description}</p>}
              <p className="mt-2 text-xs text-slate-500">
                {t("bank.list.counts", { questions: b.question_count, passages: b.passage_count })}
                {b.source_id ? ` · ${t("bank.list.source", { id: b.source_id })}` : ""}
              </p>
              <p className="text-xs text-slate-400">{t("bank.list.updated", { date: new Date(b.updated_at).toLocaleDateString() })}</p>
            </div>
            {canEdit && (
              <div className="mt-3 flex gap-2">
                {b.deleted_at ? (
                  <button type="button" className={btnSmall} onClick={() => void restore(b)}>{t("bank.list.restore")}</button>
                ) : (
                  <>
                    <button type="button" className={btnSmall} onClick={() => { setActionError(null); setDialog({ bank: b }); }}>{t("bank.list.rename")}</button>
                    <button type="button" className={btnSmall} onClick={() => { setActionError(null); setToDelete(b); }}>{t("bank.list.delete")}</button>
                  </>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <BankDialog open={!!dialog} bank={dialog?.bank ?? null} courseLanguages={course.languages} busy={busy} error={actionError}
        onSubmit={(v) => void submit(v)} onCancel={() => setDialog(null)} />
      <ConfirmDialog open={!!toDelete} danger busy={busy} title={t("bank.list.deleteTitle")} body={t("bank.list.deleteBody")}
        confirmLabel={t("bank.list.delete")} onConfirm={() => void remove()} onCancel={() => setToDelete(null)}>
        {actionError ? <ContentError error={actionError} className="mt-3" /> : null}
      </ConfirmDialog>
    </div>
  );
}
