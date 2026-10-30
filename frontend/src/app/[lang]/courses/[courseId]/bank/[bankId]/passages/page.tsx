"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { deletePassage, getBank, listPassages, restorePassage } from "@/lib/lms/content";
import type { BankOut, PassageSummaryOut } from "@/lib/lms/contentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { Pager } from "@/components/lms/Pager";
import { BankHeader } from "@/components/lms/content/BankHeader";
import { ContentError } from "@/components/lms/content/ContentError";
import { useCanEditBank } from "@/components/lms/content/StaffGate";
import { btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { Badge, Button, ConfirmDialog, EmptyState, LinkButton, LoadingState } from "@/components/ui";
import { excerptText } from "@/components/lms/course/excerpt";

export default function PassagesPage() {
  const { lang, t } = useTranslation();
  const { bankId } = useParams<{ bankId: string }>();
  const { course } = useCourse();
  const base = `/${lang}/courses/${course.id}/bank`;
  const [bank, setBank] = useState<BankOut | null>(null);
  const canEdit = useCanEditBank(bank); // Phase 9 S2: `bank.can_edit`
  const [trash, setTrash] = useState(false);
  const [items, setItems] = useState<PassageSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [toDelete, setToDelete] = useState<PassageSummaryOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  useEffect(() => { getBank(course.id, bankId).then(setBank).catch(setError); }, [course.id, bankId]);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listPassages(course.id, bankId, { deleted: trash || undefined, cursor: next, limit: 50 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, bankId, trash]);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      setToDelete(null);
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <BankHeader courseId={course.id} bank={bank} active="passages"
        secondaryActions={<Button variant="secondary" onClick={() => setTrash((s) => !s)}>{trash ? t("bank.list.hideTrash") : t("bank.list.showTrash")}</Button>}
        primaryAction={canEdit ? <LinkButton href={`${base}/${bankId}/passages/new`}>{t("bank.passages.new")}</LinkButton> : undefined} />
      <ContentError error={error || (!toDelete ? actionError : null)} onRetry={error ? () => load() : undefined} />
      {loading && items.length === 0 && !error && <LoadingState rows={2} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title={t("bank.passages.empty")}
          action={canEdit && !trash ? <LinkButton href={`${base}/${bankId}/passages/new`}>{t("bank.passages.new")}</LinkButton> : undefined} />
      )}
      {items.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
          {items.map((p) => (
            <li key={p.id} className="flex flex-wrap items-start gap-3 px-4 py-3 sm:flex-nowrap">
              <div className="min-w-0 flex-1">
                <Link href={`${base}/p/${p.id}`} className="font-semibold text-slate-900 hover:text-brand-700">{p.title || t("bank.passages.untitled")}</Link>
                <p className="mt-0.5 line-clamp-2 break-words text-sm text-slate-600">{excerptText(p.body_excerpt)}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {t(`courses.languages.${p.language}`)} · {t("bank.passages.questionCount", { n: p.question_count })}
                  {p.deleted_at && <Badge tone="danger" className="ml-2">{t("bank.list.deletedBadge")}</Badge>}
                </p>
              </div>
              {canEdit && (p.deleted_at ? (
                <button type="button" disabled={busy} className={btnSmall} onClick={() => void act(() => restorePassage(course.id, p.id))}>{t("bank.list.restore")}</button>
              ) : (
                <button type="button" disabled={busy} className={btnSmall} onClick={() => { setActionError(null); setToDelete(p); }}>{t("bank.passages.delete")}</button>
              ))}
            </li>
          ))}
        </ul>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <ConfirmDialog open={!!toDelete} tone="danger" busy={busy} title={t("bank.passages.deleteTitle")}
        object={toDelete ? toDelete.title || excerptText(toDelete.body_excerpt, 80) : undefined} effect={t("bank.passages.deleteBody")}
        confirmLabel={t("bank.passages.delete")} onConfirm={() => toDelete && void act(() => deletePassage(course.id, toDelete.id))}
        onCancel={() => setToDelete(null)} error={actionError ? <ContentError error={actionError} /> : undefined} />
    </div>
  );
}
