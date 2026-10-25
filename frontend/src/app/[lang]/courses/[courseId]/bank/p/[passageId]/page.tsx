"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getPassage } from "@/lib/lms/content";
import type { PassageOut } from "@/lib/lms/contentTypes";
import { useCourse } from "@/components/lms/CourseContext";
import { ConflictDialog } from "@/components/lms/content/ConflictDialog";
import { ContentError } from "@/components/lms/content/ContentError";
import { PassageEditor, PassageHistory } from "@/components/lms/content/PassageEditor";
import { useCanEditContent } from "@/components/lms/content/StaffGate";

type Tab = "edit" | "questions" | "history";

export default function PassagePage() {
  const { lang, t } = useTranslation();
  const { passageId } = useParams<{ passageId: string }>();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const [p, setP] = useState<PassageOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("edit");
  const [status, setStatus] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  const load = useCallback(async () => {
    try { setP(await getPassage(course.id, passageId)); setError(null); } catch (e) { setError(e); }
  }, [course.id, passageId]);
  useEffect(() => { void load(); }, [load]);

  const base = `/${lang}/courses/${course.id}/bank`;
  if (error && !p) return <ContentError error={error} onRetry={load} />;
  if (!p) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  const bankId = p.bank_id || p.questions[0]?.bank_id;
  const editable = canEdit && !p.deleted_at;

  return (
    <div className="space-y-4">
      <Link href={bankId ? `${base}/${bankId}/passages` : base} className="text-sm font-medium text-brand-700 hover:underline">{t("bank.passages.back")}</Link>
      <h2 className="text-xl font-bold text-slate-900">{p.current_version.title || t("bank.passages.untitled")}</h2>
      {/* Phase 6 S8: the tab row wraps at 375 px instead of widening the page. */}
      <div role="tablist" aria-label={t("bank.editor.tabsLabel")} className="flex flex-wrap gap-x-1 border-b border-slate-200">
        {(["edit", "questions", "history"] as Tab[]).map((id) => (
          <button key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${tab === id ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t(`bank.passages.tabs.${id}`)}
          </button>
        ))}
      </div>
      {status && <p role="status" className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{status}</p>}
      {tab === "edit" && (
        <PassageEditor courseId={course.id} bankId={bankId || ""} passage={p} courseLanguages={course.languages} defaultLanguage={course.default_language}
          readOnly={!editable} onSaved={(np) => { setP(np); setStatus(t("bank.editor.saved")); }} onConflict={() => setConflict(true)} />
      )}
      {tab === "questions" && (
        p.questions.length === 0 ? <p className="text-sm text-slate-500">{t("bank.passages.noQuestions")}</p> : (
          <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
            {p.questions.map((q) => (
              <li key={q.id} className="px-4 py-3 text-sm">
                <Link href={`${base}/q/${q.id}`} className="font-medium text-brand-700 hover:underline">{q.stem_excerpt || t("bank.questions.noStem")}</Link>
              </li>
            ))}
          </ul>
        )
      )}
      {tab === "history" && (
        <PassageHistory courseId={course.id} passage={p} canEdit={editable}
          onReverted={(np) => { setP(np); setStatus(t("bank.history.reverted")); setTab("edit"); }} onConflict={() => setConflict(true)} />
      )}
      <ConflictDialog open={conflict} onReload={() => { setConflict(false); setStatus(null); void load(); }} onClose={() => setConflict(false)} />
    </div>
  );
}
