"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getQuestionVersion, listQuestionVersions, revertQuestion } from "@/lib/lms/content";
import type { QuestionStaffOut, VersionOut, VersionSummaryOut } from "@/lib/lms/contentTypes";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { fmtApiDateTime } from "@/lib/format";
import { Pager } from "@/components/lms/Pager";
import { ContentError } from "./ContentError";
import { VersionView } from "./VersionView";
import { btnPrimary, btnSecondary, cardCls } from "./ui";

/** Question version history: list, view a version next to the current one, revert (creates a new version). */
export function VersionHistory({
  courseId, question, canEdit, onReverted, onConflict,
}: {
  courseId: string;
  question: QuestionStaffOut;
  canEdit: boolean;
  onReverted: (q: QuestionStaffOut) => void;
  onConflict: () => void;
}) {
  const { t } = useTranslation();
  const [items, setItems] = useState<VersionSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<VersionOut | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revertError, setRevertError] = useState<unknown>(null);
  const currentId = question.current_version.id;

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listQuestionVersions(courseId, question.id, { cursor: next, limit: 30 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId, question.id]);
  // Reload the list whenever the current version changes (after save or revert).
  useEffect(() => { void load(); }, [load, currentId]);

  const view = async (id: string) => {
    setError(null);
    try {
      setSelected(await getQuestionVersion(courseId, question.id, id));
    } catch (e) {
      setError(e);
    }
  };

  const revert = async () => {
    if (!selected) return;
    setBusy(true);
    setRevertError(null);
    try {
      const q = await revertQuestion(courseId, question.id, selected.id, { base_version_id: currentId });
      setConfirm(false);
      setSelected(null);
      onReverted(q);
    } catch (e) {
      if ((e as { code?: string }).code === "version_conflict") {
        setConfirm(false);
        onConflict();
      } else {
        setRevertError(e);
      }
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
              <button type="button" onClick={() => void view(v.id)}
                className={`w-full rounded-xl border px-3 py-2 text-left text-sm ${selected?.id === v.id ? "border-brand-400 bg-brand-50" : "border-slate-200 bg-white hover:bg-slate-50"}`}>
                <span className="font-semibold">{t("bank.history.version", { n: v.version_no })}</span>
                {v.id === currentId && <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">{t("bank.history.current")}</span>}
                <span className="block text-xs text-slate-500">
                  {t(`bank.history.origin.${v.origin}`)} · {fmtApiDateTime(v.created_at)}
                  {v.created_by_name ? ` · ${v.created_by_name}` : ""}
                </span>
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
            <div className="grid gap-3 md:grid-cols-2">
              <div className={cardCls}>
                <h3 className="mb-2 text-sm font-bold text-slate-900">{t("bank.history.selected", { n: selected.version_no })}</h3>
                <VersionView v={selected} />
              </div>
              <div className={cardCls}>
                <h3 className="mb-2 text-sm font-bold text-slate-900">{t("bank.history.currentTitle", { n: question.current_version.version_no })}</h3>
                <VersionView v={question.current_version} />
              </div>
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
