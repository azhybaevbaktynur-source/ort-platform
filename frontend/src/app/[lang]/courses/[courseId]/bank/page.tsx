"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { createBank, deleteBank, listBanks, restoreBank, updateBank } from "@/lib/lms/content";
import type { BankOut } from "@/lib/lms/contentTypes";
import { fmtApiDate } from "@/lib/format";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { Pager } from "@/components/lms/Pager";
import { BankDialog } from "@/components/lms/content/BankDialog";
import { Button, ConfirmDialog, EmptyState, LinkButton, LoadingState, PageHeader } from "@/components/ui";
import { ContentError } from "@/components/lms/content/ContentError";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { getBankSharing, type BankSharingOut } from "@/lib/lms/organizations"; // Phase 9 S2
import { useTemplateUi } from "@/lib/lms/templates";
import { SharedBankPicker } from "@/components/lms/content/SharedBankPicker";

export default function BankListPage() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const base = `/${lang}/courses/${course.id}/bank`;
  // --- Phase 9 S2 --- (org admins see the organization-shared banks only: no trash, no create; per-bank rights)
  const role = course.my_enrollment.role;
  const staff = !course.my_enrollment.read_only && (role === "teacher" || role === "assistant");
  const open = course.status !== "concluded";
  const isOrt = useTemplateUi().key === "ort";
  const [sharing, setSharing] = useState<BankSharingOut | null>(null);
  useEffect(() => {
    if (isOrt || !staff) return; // ORT stays as it is; only course staff copy shared banks in
    let alive = true;
    getBankSharing(course.id).then((s) => { if (alive) setSharing(s); }).catch(() => { if (alive) setSharing(null); });
    return () => { alive = false; };
  }, [course.id, isOrt, staff]);
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
      const page = await listBanks(course.id, { deleted: trash, cursor: next, limit: 50, kind: "all" });
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

  const sharedItems = items.filter((b) => !b.assessment);
  const quizItems = items.filter((b) => !!b.assessment);
  const card = (b: BankOut) => (
          <li key={b.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
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
              <p className="text-xs text-slate-400">{t("bank.list.updated", { date: fmtApiDate(b.updated_at) })}</p>
              {b.assessment && <p className="mt-1 text-xs font-medium text-slate-600">{t("bank.quizBanks.quiz", { title: pickLocalized(b.assessment.title, lang, course.default_language) })}</p>}
            </div>
            {b.assessment && (
              <div className="mt-3 space-y-2">
                <p className="text-xs text-slate-500">{t("bank.quizBanks.followsQuiz")}</p>
                <LinkButton variant="secondary" size="sm" href={`/${lang}/courses/${course.id}/assessments/${b.assessment.id}/edit`}>{t("bank.quizBanks.openQuiz")}</LinkButton>
              </div>
            )}
            {/* Phase 9 S2: rename follows `can_edit`; delete and restore follow `can_delete` (course staff only). */}
            {open && !b.assessment && (b.deleted_at ? b.can_delete : b.can_edit || b.can_delete) && (
              <div className="mt-3 flex flex-wrap gap-2">
                {b.deleted_at ? (
                  <button type="button" className={btnSmall} onClick={() => void restore(b)}>{t("bank.list.restore")}</button>
                ) : (
                  <>
                    {b.can_edit && <button type="button" className={btnSmall} onClick={() => { setActionError(null); setDialog({ bank: b }); }}>{t("bank.list.rename")}</button>}
                    {b.can_delete && <button type="button" className={btnSmall} onClick={() => { setActionError(null); setToDelete(b); }}>{t("bank.list.delete")}</button>}
                  </>
                )}
              </div>
            )}
          </li>
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("bank.list.title")} className="mb-2"
        secondaryActions={<>
          {staff && <Button variant="secondary" onClick={() => setTrash((s) => !s)}>{trash ? t("bank.list.hideTrash") : t("bank.list.showTrash")}</Button>}
          {canEdit && <LinkButton variant="secondary" href={`${base}/import`}>{t("bank.list.import")}</LinkButton>}
        </>}
        primaryAction={canEdit ? <Button onClick={() => { setActionError(null); setDialog({ bank: null }); }}>{t("bank.list.create")}</Button> : undefined} />
      <ContentError error={error || (!dialog && !toDelete ? actionError : null)} onRetry={error ? () => load() : undefined} />
      {loading && items.length === 0 && !error && <LoadingState rows={2} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title={trash ? t("bank.list.emptyTrash") : t("bank.list.empty")}
          action={!trash && canEdit ? <>
            <Button onClick={() => { setActionError(null); setDialog({ bank: null }); }}>{t("bank.list.create")}</Button>
            <LinkButton variant="secondary" href={`${base}/import`}>{t("bank.list.import")}</LinkButton>
          </> : undefined} />
      )}
      {quizItems.length === 0 ? (
        <ul className="grid gap-3 sm:grid-cols-2">{items.map(card)}</ul>
      ) : (
        <>
          {sharedItems.length > 0 && (
            <section aria-labelledby="bank-group-shared" className="space-y-2">
              <h2 id="bank-group-shared" className="text-sm font-semibold text-slate-700">{t("bank.quizBanks.sharedGroup")}</h2>
              <ul className="grid gap-3 sm:grid-cols-2">{sharedItems.map(card)}</ul>
            </section>
          )}
          <section aria-labelledby="bank-group-quiz" className="space-y-2">
            <h2 id="bank-group-quiz" className="text-sm font-semibold text-slate-700">{t("bank.quizBanks.group")}</h2>
            <ul className="grid gap-3 sm:grid-cols-2">{quizItems.map(card)}</ul>
          </section>
        </>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      {/* Phase 9 S2: "From my organization" (copy a shared bank into this course) */}
      {sharing?.can_copy && canEdit && !trash && (
        <SharedBankPicker courseId={course.id} sharing={sharing} onCopied={() => void load()} />
      )}
      <BankDialog open={!!dialog} bank={dialog?.bank ?? null} courseLanguages={course.languages} busy={busy} error={actionError}
        onSubmit={(v) => void submit(v)} onCancel={() => setDialog(null)} />
      <ConfirmDialog open={!!toDelete} tone="danger" busy={busy} title={t("bank.list.deleteTitle")} object={toDelete?.title}
        effect={t("bank.list.deleteBody")} confirmLabel={t("bank.list.delete")} onConfirm={() => void remove()} onCancel={() => setToDelete(null)}
        error={actionError ? <ContentError error={actionError} /> : undefined} />
    </div>
  );
}
