"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { addTranslation, linkTranslation, listQuestions, unlinkTranslation } from "@/lib/lms/content";
import type { QuestionStaffOut, QuestionSummaryOut } from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";
import { ConfirmDialog } from "@/components/ui";
import { ContentError } from "./ContentError";
import { cardCls, inputCls } from "./ui";
import { btnSecondary, btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c

/** Translation variants of a question (D15): add a copy in another course language, link an existing question, unlink. */
export function TranslationPanel({
  courseId, question, courseLanguages, canEdit, onChanged,
}: {
  courseId: string;
  question: QuestionStaffOut;
  courseLanguages: Lang[];
  canEdit: boolean;
  onChanged: () => Promise<void> | void;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const base = `/${lang}/courses/${courseId}/bank/q`;
  const taken = new Set<Lang>([question.language, ...question.translations.map((x) => x.language)]);
  const missing = courseLanguages.filter((l) => !taken.has(l));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [linkLang, setLinkLang] = useState<Lang | "">("");
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<QuestionSummaryOut[] | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState(false);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const add = (l: Lang) => run(`add-${l}`, async () => {
    const q = await addTranslation(courseId, question.id, { language: l });
    router.push(`${base}/${q.id}`);
  });

  const doSearch = (l: Lang) => run("search", async () => {
    const page = await listQuestions(courseId, question.bank_id, { q: search, type: question.type, language: l, limit: 20 });
    setResults(page.items.filter((x) => x.id !== question.id && !x.translation_group_id));
  });

  const link = (other: QuestionSummaryOut) => run(`link-${other.id}`, async () => {
    await linkTranslation(courseId, question.id, other.id);
    setResults(null);
    setLinkLang("");
    await onChanged();
  });

  const unlink = () => run("unlink", async () => {
    await unlinkTranslation(courseId, question.id);
    setConfirmUnlink(false);
    await onChanged();
  });

  return (
    <div className="space-y-4">
      <ContentError error={error} />
      <div className={cardCls}>
        <h3 className="mb-2 text-sm font-bold text-slate-900">{t("bank.translations.variants")}</h3>
        <ul className="space-y-1.5 text-sm">
          <li className="flex items-center gap-2">
            <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">{t(`courses.languages.${question.language}`)}</span>
            <span className="text-slate-500">{t("bank.translations.thisOne")}</span>
          </li>
          {question.translations.map((tr) => (
            <li key={tr.question_id} className="flex items-center gap-2">
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{t(`courses.languages.${tr.language}`)}</span>
              <Link href={`${base}/${tr.question_id}`} className="font-medium text-brand-700 hover:underline">{t("bank.translations.open")}</Link>
            </li>
          ))}
        </ul>
        {question.translations.length === 0 && <p className="mt-2 text-sm text-slate-500">{t("bank.translations.none")}</p>}
        {canEdit && question.translation_group_id && (
          <button type="button" className={`${btnSmall} mt-3`} onClick={() => setConfirmUnlink(true)}>{t("bank.translations.unlink")}</button>
        )}
      </div>

      {canEdit && missing.length > 0 && (
        <div className={cardCls}>
          <h3 className="mb-2 text-sm font-bold text-slate-900">{t("bank.translations.addTitle")}</h3>
          <p className="mb-3 text-xs text-slate-500">{t("bank.translations.addHint")}</p>
          <div className="flex flex-wrap gap-2">
            {missing.map((l) => (
              <button key={l} type="button" disabled={busy !== null} className={btnSecondary} onClick={() => void add(l)}>
                {busy === `add-${l}` ? t("lms.common.loading") : t("bank.translations.addIn", { language: t(`courses.languages.${l}`) })}
              </button>
            ))}
          </div>
          <div className="mt-4 border-t border-slate-100 pt-3">
            <h4 className="mb-2 text-sm font-semibold text-slate-800">{t("bank.translations.linkTitle")}</h4>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-slate-600">{t("bank.filters.language")}
                <select className={`${inputCls} mt-0.5 w-auto`} value={linkLang} onChange={(e) => { setLinkLang(e.target.value as Lang | ""); setResults(null); }}>
                  <option value="">{t("bank.translations.pickLanguage")}</option>
                  {missing.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
                </select>
              </label>
              <label className="text-xs text-slate-600">{t("lms.common.search")}
                <input className={`${inputCls} mt-0.5 w-56`} value={search} onChange={(e) => setSearch(e.target.value)} />
              </label>
              <button type="button" disabled={!linkLang || busy !== null} className={btnSecondary} onClick={() => linkLang && void doSearch(linkLang)}>
                {t("lms.common.search")}
              </button>
            </div>
            {results && results.length === 0 && <p className="mt-2 text-sm text-slate-500">{t("bank.translations.noResults")}</p>}
            {results && results.length > 0 && (
              <ul className="mt-2 divide-y divide-slate-100 rounded-xl border border-slate-200">
                {results.map((r) => (
                  <li key={r.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                    <span className="flex-1 truncate text-slate-800">{r.stem_excerpt || "-"}</span>
                    <button type="button" disabled={busy !== null} className={btnSmall} onClick={() => void link(r)}>{t("bank.translations.link")}</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <ConfirmDialog open={confirmUnlink} busy={busy === "unlink"} title={t("bank.translations.unlinkTitle")}
        effect={t("bank.translations.unlinkBody")} confirmLabel={t("bank.translations.unlink")}
        onConfirm={() => void unlink()} onCancel={() => setConfirmUnlink(false)} />
    </div>
  );
}
