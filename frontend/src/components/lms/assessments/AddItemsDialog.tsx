"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { addItem, addItemsBulk } from "@/lib/lms/assessments";
import { listPassages, listQuestions } from "@/lib/lms/content";
import {
  DIFFICULTIES, QUESTION_TYPES, type Difficulty, type PassageSummaryOut, type QuestionSummaryOut, type QuestionType,
} from "@/lib/lms/contentTypes";
import { useTemplateUi } from "@/lib/lms/templates";
import type { BulkAddOut } from "@/lib/lms/assessmentTypes";
import { LMS_LANGS, type Lang } from "@/lib/lms/types";
import { Pager } from "@/components/lms/Pager";
import { inputCls, labelCls } from "@/components/lms/content/ui";
import { btnPrimary, btnSecondary } from "@/components/lms/course/staffUi"; // Phase 6b S5c
import { ContentError } from "@/components/lms/content/ContentError";
import { AssessmentError } from "./AssessmentError";
import { Modal } from "./Modal";
import { BankSelect, PickFields, useBanks, type PickValue } from "./PickFields";

export type AddItemsTab = "questions" | "passage" | "pick";
type Tab = AddItemsTab;

interface Filters { q: string; type: QuestionType | ""; language: Lang | ""; section: string; topic: string; difficulty: Difficulty | "" }
const EMPTY: Filters = { q: "", type: "", language: "", section: "", topic: "", difficulty: "" };

/** Add items to a section: questions (multi-select or all filtered), a passage group, or a random pick from a bank. */
export function AddItemsDialog({
  open, courseId, assessmentId, sectionId, onClose, onAdded, initialTab = "questions",
}: {
  open: boolean;
  courseId: string;
  assessmentId: string;
  sectionId: string;
  onClose: () => void;
  onAdded: () => void | Promise<void>;
  /** Phase 7c S3: the tab shown when the dialog opens (the quiz editor opens it on "Passage" or "Random group"). */
  initialTab?: AddItemsTab;
}) {
  const { t } = useTranslation();
  const ui = useTemplateUi();
  const [tab, setTab] = useState<Tab>("questions");
  const { banks, error: banksError } = useBanks(courseId, open);
  const [bankId, setBankId] = useState("");
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [rows, setRows] = useState<QuestionSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<unknown>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [passages, setPassages] = useState<PassageSummaryOut[]>([]);
  const [passageId, setPassageId] = useState("");
  const [pick, setPick] = useState<PickValue>({ bank_id: "", count: 5, filter: {} });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [report, setReport] = useState<BulkAddOut | null>(null);

  useEffect(() => {
    if (open) {
      setTab(initialTab); setBankId(""); setFilters(EMPTY); setRows([]); setSelected(new Set()); setPassageId("");
      setPick({ bank_id: "", count: 5, filter: {} }); setError(null); setReport(null);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async (next?: string | null) => {
    if (!bankId) { setRows([]); setCursor(null); return; }
    setLoading(true);
    setListError(null);
    try {
      const page = await listQuestions(courseId, bankId, {
        q: filters.q || undefined, type: filters.type, language: filters.language, section: filters.section || undefined,
        topic: filters.topic || undefined, difficulty: filters.difficulty, cursor: next, limit: 50,
      });
      setRows((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setListError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId, bankId, filters]);
  useEffect(() => {
    if (!open || tab !== "questions") return;
    const h = setTimeout(() => void load(), 250);
    return () => clearTimeout(h);
  }, [open, tab, load]);

  useEffect(() => {
    if (!open || tab !== "passage" || !bankId) { setPassages([]); return; }
    let alive = true;
    listPassages(courseId, bankId, { limit: 100 }).then((p) => { if (alive) setPassages(p.items); }).catch((e) => { if (alive) setListError(e); });
    return () => { alive = false; };
  }, [open, tab, bankId, courseId]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) { setError(e); } finally { setBusy(false); }
  };

  const addSelected = () => run(async () => {
    const out = await addItemsBulk(courseId, assessmentId, sectionId, { question_ids: Array.from(selected), group_passages: true });
    setReport(out);
    setSelected(new Set());
    await onAdded();
  });
  const addAllFiltered = () => run(async () => {
    const out = await addItemsBulk(courseId, assessmentId, sectionId, {
      bank_id: bankId,
      filter: {
        ...(filters.q ? { q: filters.q } : {}), ...(filters.type ? { type: filters.type } : {}),
        ...(filters.language ? { language: filters.language } : {}), ...(filters.section ? { section: filters.section } : {}),
        ...(filters.topic ? { topic: filters.topic } : {}), ...(filters.difficulty ? { difficulty: filters.difficulty } : {}),
      },
      group_passages: true,
    });
    setReport(out);
    await onAdded();
  });
  const addPassage = () => run(async () => {
    const ids: string[] = [];
    let cur: string | null | undefined;
    do {
      const page = await listQuestions(courseId, bankId, { passage_id: passageId, cursor: cur, limit: 100 });
      ids.push(...page.items.map((q) => q.id));
      cur = page.next_cursor;
    } while (cur);
    await addItem(courseId, assessmentId, sectionId, { kind: "passage", passage_id: passageId, question_ids: ids });
    await onAdded();
    onClose();
  });
  const addPick = () => run(async () => {
    await addItem(courseId, assessmentId, sectionId, { kind: "pick", pick: { bank_id: pick.bank_id, count: pick.count, filter: pick.filter } });
    await onAdded();
    onClose();
  });

  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const set = (p: Partial<Filters>) => setFilters((f) => ({ ...f, ...p }));
  const tabBtn = (k: Tab, label: string) => (
    <button type="button" role="tab" aria-selected={tab === k} onClick={() => { setTab(k); setError(null); setReport(null); }}
      className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${tab === k ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{label}</button>
  );

  return (
    <Modal open={open} title={t("assessments.add.title")} onClose={onClose} busy={busy} wide>
      <div role="tablist" aria-label={t("assessments.add.title")} className="mb-4 flex flex-wrap gap-2">
        {tabBtn("questions", t("assessments.add.tabQuestions"))}
        {tabBtn("passage", t("assessments.add.tabPassage"))}
        {tabBtn("pick", t("assessments.add.tabPick"))}
      </div>
      <ContentError error={banksError} />
      {tab !== "pick" && <BankSelect id="add-bank" banks={banks} value={bankId} onChange={(v) => { setBankId(v); setSelected(new Set()); setPassageId(""); }} />}

      {tab === "questions" && bankId && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-slate-500">{t("assessments.add.translationHint")}</p>
          <input type="search" aria-label={t("bank.filters.search")} placeholder={t("bank.filters.search")} className={inputCls} value={filters.q} onChange={(e) => set({ q: e.target.value })} />
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <label className="text-xs font-medium text-slate-600">{t("bank.filters.type")}
              <select className={`${inputCls} mt-0.5`} value={filters.type} onChange={(e) => set({ type: e.target.value as QuestionType | "" })}>
                <option value="">{t("bank.filters.all")}</option>
                {QUESTION_TYPES.map((q) => <option key={q} value={q}>{t(`bank.types.${q}.name`)}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-600">{t("bank.filters.language")}
              <select className={`${inputCls} mt-0.5`} value={filters.language} onChange={(e) => set({ language: e.target.value as Lang | "" })}>
                <option value="">{t("bank.filters.all")}</option>
                {LMS_LANGS.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-600">{t("bank.filters.section")}
              <input list={ui.sectionKeys.length ? "add-sections" : undefined} className={`${inputCls} mt-0.5`} value={filters.section} onChange={(e) => set({ section: e.target.value })} />
              {ui.sectionKeys.length > 0 && <datalist id="add-sections">{ui.sectionKeys.map((s) => <option key={s} value={s}>{t(`sections.${s}`)}</option>)}</datalist>}
            </label>
            <label className="text-xs font-medium text-slate-600">{t("bank.filters.topic")}
              <input className={`${inputCls} mt-0.5`} value={filters.topic} onChange={(e) => set({ topic: e.target.value })} />
            </label>
            <label className="text-xs font-medium text-slate-600">{t("bank.filters.difficulty")}
              <select className={`${inputCls} mt-0.5`} value={filters.difficulty} onChange={(e) => set({ difficulty: e.target.value as Difficulty | "" })}>
                <option value="">{t("bank.filters.all")}</option>
                {DIFFICULTIES.map((d) => <option key={d} value={d}>{t(`bank.difficulty.${d}`)}</option>)}
              </select>
            </label>
          </div>
          <ContentError error={listError} onRetry={() => load()} />
          {loading && rows.length === 0 && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
          {!loading && rows.length === 0 && !listError && <p className="text-sm text-slate-500">{t("assessments.add.noQuestions")}</p>}
          <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200">
            {rows.map((q) => (
              <li key={q.id}>
                <label className="flex cursor-pointer items-start gap-2 px-3 py-2 text-sm hover:bg-slate-50">
                  <input type="checkbox" className="mt-1" checked={selected.has(q.id)} onChange={() => toggle(q.id)} />
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-slate-800">{q.stem_excerpt || t("assessments.add.noStem")}</span>
                    <span className="text-xs text-slate-500">
                      {t(`bank.types.${q.type}.name`)} · {q.language.toUpperCase()}{q.section ? ` · ${q.section}` : ""}{q.passage_id ? ` · ${t("assessments.add.hasPassage")}` : ""}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
          {report && (
            <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-2 text-sm text-emerald-900">
              {t("assessments.add.report", { added: report.added, skipped: report.skipped.length })}
              {report.skipped.length > 0 && (
                <ul className="mt-1 list-disc pl-5 text-xs">
                  {report.skipped.slice(0, 10).map((s) => <li key={s.question_id}>{t(`lms.errors.${s.code}`)}</li>)}
                </ul>
              )}
            </div>
          )}
          <AssessmentError error={error} />
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className={btnSecondary} disabled={busy} onClick={onClose}>{t("assessments.add.close")}</button>
            <button type="button" className={btnSecondary} disabled={busy || rows.length === 0} onClick={() => void addAllFiltered()}>{t("assessments.add.addAllFiltered")}</button>
            <button type="button" className={btnPrimary} disabled={busy || selected.size === 0} onClick={() => void addSelected()}>{t("assessments.add.addSelected", { n: selected.size })}</button>
          </div>
        </div>
      )}

      {tab === "passage" && bankId && (
        <div className="mt-3 space-y-3">
          <ContentError error={listError} />
          <div>
            <label className={labelCls} htmlFor="add-passage">{t("assessments.add.passage")}</label>
            <select id="add-passage" className={inputCls} value={passageId} onChange={(e) => setPassageId(e.target.value)}>
              <option value="">{t("assessments.add.choosePassage")}</option>
              {passages.map((p) => <option key={p.id} value={p.id}>{(p.title || p.body_excerpt).slice(0, 80)} ({p.language.toUpperCase()}, {p.question_count})</option>)}
            </select>
          </div>
          <p className="text-xs text-slate-500">{t("assessments.add.passageHint")}</p>
          <AssessmentError error={error} />
          <div className="flex justify-end gap-2">
            <button type="button" className={btnSecondary} disabled={busy} onClick={onClose}>{t("assessments.add.close")}</button>
            <button type="button" className={btnPrimary} disabled={busy || !passageId} onClick={() => void addPassage()}>{t("assessments.add.addPassage")}</button>
          </div>
        </div>
      )}

      {tab === "pick" && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-slate-500">{t("assessments.pick.hint")}</p>
          <PickFields courseId={courseId} value={pick} onChange={setPick} />
          <AssessmentError error={error} />
          <div className="flex justify-end gap-2">
            <button type="button" className={btnSecondary} disabled={busy} onClick={onClose}>{t("assessments.add.close")}</button>
            <button type="button" className={btnPrimary} disabled={busy || !pick.bank_id} onClick={() => void addPick()}>{t("assessments.pick.add")}</button>
          </div>
        </div>
      )}
    </Modal>
  );
}
