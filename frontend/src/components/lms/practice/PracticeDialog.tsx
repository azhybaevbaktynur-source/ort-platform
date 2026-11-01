"use client";

// Phase 10 S3: create / edit a practice set: title and 1..5 blocks (bank, section, topic, difficulty, count).
import React, { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Dialog, Input, Select } from "@/components/ui";
import { listBanks } from "@/lib/lms/content";
import { isLmsApiError } from "@/lib/lms/client";
import { pickLocalized } from "@/lib/lms/localized";
import {
  createPractice, practiceFacets, updatePractice,
  type PracticeBlock, type PracticeDifficulty, type PracticeFacets, type PracticeSetOut,
} from "@/lib/lms/practice";
import type { BankOut } from "@/lib/lms/contentTypes";
import type { Lang } from "@/lib/lms/types";

const DIFFS: PracticeDifficulty[] = ["easy", "medium", "hard"];
type Draft = { bank_id: string; count: string; section: string; topic: string; difficulty: string };
const blank = (bank_id = ""): Draft => ({ bank_id, count: "10", section: "", topic: "", difficulty: "" });

function BlockFields({ n, courseId, draft, banks, canRemove, onChange, onRemove }: {
  n: number; courseId: string; draft: Draft; banks: BankOut[]; canRemove: boolean;
  onChange: (d: Draft) => void; onRemove: () => void;
}) {
  const { t } = useTranslation();
  const [facets, setFacets] = useState<PracticeFacets | null>(null);
  useEffect(() => {
    if (!draft.bank_id) { setFacets(null); return; }
    let alive = true;
    practiceFacets(courseId, draft.bank_id).then((f) => { if (alive) setFacets(f); }).catch(() => { if (alive) setFacets(null); });
    return () => { alive = false; };
  }, [courseId, draft.bank_id]);
  const opts = (xs: string[]) => xs.map((x) => ({ value: x, label: x }));
  return (
    <fieldset className="space-y-3 rounded-xl border border-slate-200 p-3">
      <legend className="px-1 text-sm font-semibold text-slate-800">{t("practice.dialog.block", { n })}</legend>
      <Select label={t("practice.dialog.bank")} value={draft.bank_id} placeholder={t("practice.dialog.chooseBank")}
        options={banks.map((b) => ({ value: b.id, label: b.title }))}
        onChange={(e) => onChange({ ...draft, bank_id: e.target.value, section: "", topic: "", difficulty: "" })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label={t("practice.dialog.section")} optional value={draft.section} placeholder={t("practice.dialog.any")}
          options={opts(facets?.sections ?? [])} onChange={(e) => onChange({ ...draft, section: e.target.value })} />
        <Select label={t("practice.dialog.topic")} optional value={draft.topic} placeholder={t("practice.dialog.any")}
          options={opts(facets?.topics ?? [])} onChange={(e) => onChange({ ...draft, topic: e.target.value })} />
        <Select label={t("practice.dialog.difficulty")} optional value={draft.difficulty} placeholder={t("practice.dialog.any")}
          options={DIFFS.map((d) => ({ value: d, label: t(`practice.difficulty.${d}`) }))}
          onChange={(e) => onChange({ ...draft, difficulty: e.target.value })} />
        <Input label={t("practice.dialog.count")} type="number" inputMode="numeric" min={1} max={200} value={draft.count}
          onChange={(e) => onChange({ ...draft, count: e.target.value })} />
      </div>
      {canRemove && (
        <Button variant="link" size="sm" className="text-danger-700" onClick={onRemove} leftIcon={<Trash2 className="h-4 w-4" aria-hidden="true" />}>
          {t("practice.dialog.removeBlock")}
        </Button>
      )}
    </fieldset>
  );
}

export function PracticeDialog({ open, courseId, languages, defaultLanguage, set, onClose, onSaved }: {
  open: boolean;
  courseId: string;
  languages: Lang[];
  defaultLanguage: Lang;
  /** set to edit; null = create */
  set: PracticeSetOut | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { lang, t } = useTranslation();
  const [title, setTitle] = useState("");
  const [blocks, setBlocks] = useState<Draft[]>([blank()]);
  const [banks, setBanks] = useState<BankOut[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setTitle(set ? pickLocalized(set.title, lang, defaultLanguage) : "");
    setBlocks(set && set.blocks.length
      ? set.blocks.map((b) => ({ bank_id: b.bank_id, count: String(b.count), section: b.section ?? "", topic: b.topic ?? "", difficulty: b.difficulty ?? "" }))
      : [blank()]);
    let alive = true;
    listBanks(courseId, { limit: 100 }).then((p) => {
      if (!alive) return;
      setBanks(p.items);
      setBlocks((bs) => bs.map((b) => (b.bank_id || p.items.length !== 1 ? b : { ...b, bank_id: p.items[0].id })));
    }).catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [open, set, courseId, lang, defaultLanguage]);

  const set1 = (i: number, d: Draft) => setBlocks((bs) => bs.map((b, j) => (j === i ? d : b)));
  const valid = title.trim() !== "" && blocks.every((b) => b.bank_id && Number(b.count) >= 1);

  const save = async () => {
    setBusy(true);
    setError(null);
    const out: PracticeBlock[] = blocks.map((b) => ({
      bank_id: b.bank_id, count: Math.max(1, Math.floor(Number(b.count))),
      section: b.section || null, topic: b.topic || null, difficulty: (b.difficulty || null) as PracticeDifficulty | null,
    }));
    const text = Object.fromEntries(languages.map((l) => [l, title.trim()]));
    try {
      if (set) await updatePractice(courseId, set.id, { title: text, blocks: out });
      else await createPractice(courseId, { title: text, languages, blocks: out });
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} busy={busy} size="lg" title={t(set ? "practice.dialog.editTitle" : "practice.dialog.createTitle")}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={busy}>{t("common.cancel")}</Button>
        <Button onClick={() => void save()} loading={busy} disabled={!valid}>{t(set ? "practice.dialog.save" : "practice.dialog.create")}</Button>
      </>}>
      <div className="space-y-4">
        <Input label={t("practice.dialog.name")} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
        {blocks.map((b, i) => (
          <BlockFields key={i} n={i + 1} courseId={courseId} draft={b} banks={banks} canRemove={blocks.length > 1}
            onChange={(d) => set1(i, d)} onRemove={() => setBlocks((bs) => bs.filter((_, j) => j !== i))} />
        ))}
        {blocks.length < 5 && (
          <Button variant="secondary" size="sm" onClick={() => setBlocks((bs) => [...bs, blank()])} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>
            {t("practice.dialog.addBlock")}
          </Button>
        )}
        {isLmsApiError(error) && error.code === "pick_pool_too_small"
          ? <p role="alert" className="text-sm text-danger-700">{t("practice.dialog.poolTooSmall")}</p>
          : error ? <ErrorMessage error={error} /> : null}
      </div>
    </Dialog>
  );
}
