"use client";

import React, { useId } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { Band, BandsParams, SchemeParams } from "@/lib/lms/gradingTypes";
import { LMS_LANGS, type Lang } from "@/lib/lms/types";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { moveIndex } from "@/components/lms/assessments/format";
import { useDragReorder } from "@/components/lms/assessments/useDragReorder";
import { btnSmall, cardCls, inputCls, labelCls } from "@/components/lms/content/ui";
import { NumInput, RowActions } from "./fields";
import { CAPS, nextBand } from "./params";

/** `bands`: ordered rows from the highest band down; the last one starts at 0 %. Labels are trilingual. */
export function BandsForm({
  params, onChange, readOnly,
}: {
  params: BandsParams;
  onChange: (p: SchemeParams) => void;
  readOnly: boolean;
}) {
  const { lang, t } = useTranslation();
  const id = useId();
  const bands = params.bands ?? [];
  const setBands = (next: Band[]) => onChange({ ...params, bands: next });
  const patch = (i: number, b: Partial<Band>) => setBands(bands.map((x, j) => (j === i ? { ...x, ...b } : x)));
  const move = (from: number, to: number) => setBands(moveIndex(bands, from, to));
  const drag = useDragReorder(move, !readOnly);
  const sortDesc = () =>
    setBands([...bands].sort((a, b) => (Number.isFinite(b.min_percent) ? b.min_percent : -1) - (Number.isFinite(a.min_percent) ? a.min_percent : -1)));

  return (
    <div className={`${cardCls} space-y-3`}>
      <p className="text-sm text-slate-600">{t("schemes.typeHints.bands")}</p>
      <ol className="space-y-3">
        {bands.map((b, i) => (
          <li key={i} {...drag(i)} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("schemes.bands.row", { n: i + 1 })}</span>
              <RowActions index={i} count={bands.length} onMove={move} onRemove={(k) => setBands(bands.filter((_, j) => j !== k))} disabled={readOnly} />
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-[8rem_8rem_auto]">
              <div>
                <label htmlFor={`${id}-k${i}`} className={labelCls}>{t("schemes.bands.key")}</label>
                <input id={`${id}-k${i}`} type="text" className={inputCls} value={b.key} maxLength={CAPS.keyChars}
                  onChange={(e) => patch(i, { key: e.target.value })} />
              </div>
              <div>
                <label htmlFor={`${id}-m${i}`} className={labelCls}>{t("schemes.bands.minPercent")}</label>
                <NumInput id={`${id}-m${i}`} value={b.min_percent} onChange={(v) => patch(i, { min_percent: v as number })} />
              </div>
              <label htmlFor={`${id}-p${i}`} className="col-span-2 flex items-center gap-2 self-end pb-2 text-sm text-slate-700 sm:col-span-1">
                <input id={`${id}-p${i}`} type="checkbox" checked={b.passed} onChange={(e) => patch(i, { passed: e.target.checked })} />
                {t("schemes.bands.passed")}
              </label>
            </div>
            <div className="mt-3">
              <LocalizedTextInput label={t("schemes.bands.label")} languages={LMS_LANGS} defaultLanguage={lang as Lang}
                value={b.label ?? {}} onChange={(v) => patch(i, { label: v })} maxLength={CAPS.labelChars} disabled={readOnly} />
            </div>
          </li>
        ))}
      </ol>
      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={`${btnSmall} inline-flex items-center gap-1`} disabled={bands.length >= CAPS.bands}
            onClick={() => setBands([...bands, nextBand()])}>
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />{t("schemes.bands.add")}
          </button>
          <button type="button" className={btnSmall} disabled={bands.length < 2} onClick={sortDesc}>{t("schemes.bands.sort")}</button>
        </div>
      )}
      <p className="text-xs text-slate-500">{t("schemes.bands.hint")}</p>
    </div>
  );
}
