"use client";

import React, { useId, useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { LookupRow, LookupTableParams, SchemeParams } from "@/lib/lms/gradingTypes";
import { btnSecondary, btnSmall, cardCls, inputCls, labelCls } from "@/components/lms/content/ui";
import { NumField, NumInput, RowActions } from "./fields";
import { CAPS, lookupToCsv, nextRow, parseLookupCsv } from "./params";

const cellCls =
  "w-full min-w-[4.5rem] rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-50";

/** `lookup_table`: raw-point ranges mapped to values; rows can be pasted as CSV `raw_from,raw_to,value,label`. */
export function LookupTableForm({
  params, onChange, readOnly,
}: {
  params: LookupTableParams;
  onChange: (p: SchemeParams) => void;
  readOnly: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const rows = params.rows ?? [];
  const setRows = (next: LookupRow[]) => onChange({ ...params, rows: next });
  const patch = (i: number, r: Partial<LookupRow>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...r } : x)));
  const [csvOpen, setCsvOpen] = useState(false);
  const [csv, setCsv] = useState("");
  const [badLines, setBadLines] = useState<number[]>([]);
  const [tooMany, setTooMany] = useState(false);

  const applyCsv = () => {
    const res = parseLookupCsv(csv);
    setBadLines(res.badLines);
    setTooMany(res.rows.length > CAPS.rows);
    if (res.badLines.length || !res.rows.length || res.rows.length > CAPS.rows) return;
    setRows(res.rows);
    setCsvOpen(false);
  };

  return (
    <div className={`${cardCls} space-y-4`}>
      <p className="text-sm text-slate-600">{t("schemes.typeHints.lookup_table")}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <NumField label={t("schemes.lookup.expectedPossible")} value={params.expected_possible ?? null}
          hint={t("schemes.lookup.expectedPossibleHint")} onChange={(v) => onChange({ ...params, expected_possible: v })} />
      </div>

      <div className="max-h-[28rem] overflow-auto rounded-xl border border-slate-200">
        <table className="w-full min-w-[30rem] text-sm">
          <caption className="sr-only">{t("schemes.lookup.rows")}</caption>
          <thead className="sticky top-0 bg-slate-50">
            <tr className="text-left text-xs text-slate-500">
              <th scope="col" className="px-2 py-1.5 font-medium">#</th>
              <th scope="col" className="px-1 py-1.5 font-medium">{t("schemes.lookup.rawFrom")}</th>
              <th scope="col" className="px-1 py-1.5 font-medium">{t("schemes.lookup.rawTo")}</th>
              <th scope="col" className="px-1 py-1.5 font-medium">{t("schemes.lookup.value")}</th>
              <th scope="col" className="px-1 py-1.5 font-medium">{t("schemes.lookup.label")}</th>
              <th scope="col" className="px-1 py-1.5"><span className="sr-only">{t("schemes.editor.actions")}</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="px-2 py-1 text-xs text-slate-500">{i + 1}</td>
                <td className="px-1 py-1"><NumInput className={cellCls} value={r.raw_from} ariaLabel={`${t("schemes.lookup.rawFrom")} ${i + 1}`} onChange={(v) => patch(i, { raw_from: v as number })} /></td>
                <td className="px-1 py-1"><NumInput className={cellCls} value={r.raw_to} ariaLabel={`${t("schemes.lookup.rawTo")} ${i + 1}`} onChange={(v) => patch(i, { raw_to: v as number })} /></td>
                <td className="px-1 py-1"><NumInput className={cellCls} value={r.value} ariaLabel={`${t("schemes.lookup.value")} ${i + 1}`} onChange={(v) => patch(i, { value: v as number })} /></td>
                <td className="px-1 py-1">
                  <input type="text" className={cellCls} value={r.label ?? ""} maxLength={CAPS.labelChars} aria-label={`${t("schemes.lookup.label")} ${i + 1}`}
                    onChange={(e) => patch(i, { label: e.target.value })} />
                </td>
                <td className="px-1 py-1"><RowActions index={i} count={rows.length} onRemove={(k) => setRows(rows.filter((_, j) => j !== k))} disabled={readOnly} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={`${btnSmall} inline-flex items-center gap-1`} disabled={rows.length >= CAPS.rows}
            onClick={() => setRows([...rows, nextRow(rows)])}>
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />{t("schemes.lookup.add")}
          </button>
          <button type="button" className={btnSmall} aria-expanded={csvOpen}
            onClick={() => { setCsv(lookupToCsv(rows)); setBadLines([]); setTooMany(false); setCsvOpen((o) => !o); }}>
            {t("schemes.lookup.csv")}
          </button>
        </div>
      )}
      {csvOpen && !readOnly && (
        <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <label htmlFor={`${id}-csv`} className={labelCls}>{t("schemes.lookup.csv")}</label>
          <textarea id={`${id}-csv`} rows={8} className={`${inputCls} font-mono`} value={csv} onChange={(e) => setCsv(e.target.value)}
            placeholder="0,9,60&#10;10,19,90" spellCheck={false} />
          <p className="text-xs text-slate-500">{t("schemes.lookup.csvHint")}</p>
          {badLines.length > 0 && (
            <p role="alert" className="text-sm text-red-700">{t("schemes.lookup.csvBadLines", { lines: badLines.slice(0, 20).join(", ") })}</p>
          )}
          {tooMany && <p role="alert" className="text-sm text-red-700">{t("schemes.validation.tooMany", { max: CAPS.rows })}</p>}
          <div className="flex gap-2">
            <button type="button" className={btnSecondary} onClick={() => setCsvOpen(false)}>{t("lms.common.cancel")}</button>
            <button type="button" className={btnSecondary} onClick={applyCsv} disabled={!csv.trim()}>{t("schemes.lookup.csvApply")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
