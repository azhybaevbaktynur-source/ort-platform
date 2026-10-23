"use client";

import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { previewScheme } from "@/lib/lms/grading";
import type { SchemeParams, SchemePreviewRow, SchemeType } from "@/lib/lms/gradingTypes";
import { cardCls, inputCls, labelCls } from "@/components/lms/content/ui";
import { NumInput } from "./fields";
import { bandLabels, fmtNum, fmtPercentile, previewRaws, stableStringify } from "./params";
import { SchemeError } from "./SchemeError";
import { useSchemeLabel } from "./labels";

const DEBOUNCE_MS = 400;

/**
 * Live preview: POST /grading-schemes/preview (debounced 400 ms) over raw scores 0..N or a step.
 * Not called while the params have client-side issues (`blocked`).
 */
export function SchemePreview({
  type, params, blocked, defaultPossible,
}: {
  type: SchemeType;
  params: SchemeParams;
  blocked: boolean;
  defaultPossible?: number | null;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [possible, setPossible] = useState<number | null>(defaultPossible ?? 30);
  const [useStep, setUseStep] = useState(false);
  const [step, setStep] = useState<number | null>(5);
  const [rows, setRows] = useState<SchemePreviewRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const lastKey = useRef("");
  const labelOf = useSchemeLabel();
  const bands = useMemo(() => bandLabels(params), [params]);

  const raws = useMemo(() => previewRaws(possible, useStep ? step : null), [possible, useStep, step]);
  const key = useMemo(() => stableStringify({ type, params, possible, raws }), [type, params, possible, raws]);

  useEffect(() => {
    if (blocked || !raws.length || possible === null) return;
    if (key === lastKey.current) return;
    const ctl = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await previewScheme({ type, params, possible, raws }, ctl.signal);
        lastKey.current = key;
        setRows(res.rows);
        setError(null);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e);
      } finally {
        if (!ctl.signal.aborted) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => { clearTimeout(timer); ctl.abort(); setLoading(false); };
    // `key` covers type/params/possible/raws
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, blocked]);

  const label = (r: SchemePreviewRow) => (r.label ? labelOf(r.label, type === "bands" ? bands : null) : "");
  const showPct = rows?.some((r) => r.percentile !== null && r.percentile !== undefined);
  const showPassed = rows?.some((r) => r.passed !== null && r.passed !== undefined);
  const showLabel = rows?.some((r) => !!r.label);
  const thresholdKeys = Array.from(new Set((rows ?? []).flatMap((r) => Object.keys(r.thresholds ?? {}))));

  return (
    <section aria-labelledby={`${id}-h`} className={`${cardCls} space-y-3`}>
      <h2 id={`${id}-h`} className="text-base font-semibold text-slate-900">{t("schemes.preview.title")}</h2>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-32">
          <label htmlFor={`${id}-poss`} className={labelCls}>{t("schemes.preview.possible")}</label>
          <NumInput id={`${id}-poss`} value={possible} onChange={setPossible} />
        </div>
        <div className="w-40">
          <label htmlFor={`${id}-mode`} className={labelCls}>{t("schemes.preview.rows")}</label>
          <select id={`${id}-mode`} className={inputCls} value={useStep ? "step" : "all"} onChange={(e) => setUseStep(e.target.value === "step")}>
            <option value="all">{t("schemes.preview.everyPoint")}</option>
            <option value="step">{t("schemes.preview.withStep")}</option>
          </select>
        </div>
        {useStep && (
          <div className="w-24">
            <label htmlFor={`${id}-step`} className={labelCls}>{t("schemes.preview.step")}</label>
            <NumInput id={`${id}-step`} value={step} onChange={setStep} />
          </div>
        )}
        {loading && <span role="status" className="pb-2 text-xs text-slate-500">{t("lms.common.loading")}</span>}
      </div>

      {blocked && <p className="text-sm text-slate-500">{t("schemes.preview.blocked")}</p>}
      {!blocked && !raws.length && <p className="text-sm text-slate-500">{t("schemes.preview.needPossible")}</p>}
      {!blocked && error ? <SchemeError error={error} /> : null}

      {!blocked && rows && rows.length > 0 && raws.length > 0 && (
        <div className={`max-h-96 overflow-auto rounded-xl border border-slate-200 ${loading ? "opacity-60" : ""}`}>
          <table className="w-full text-sm">
            <caption className="sr-only">{t("schemes.preview.title")}</caption>
            <thead className="sticky top-0 bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">{t("schemes.preview.raw")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("schemes.preview.value")}</th>
                {showLabel && <th scope="col" className="px-3 py-2 font-medium">{t("schemes.preview.label")}</th>}
                {showPct && <th scope="col" className="px-3 py-2 font-medium">{t("schemes.preview.percentile")}</th>}
                {showPassed && <th scope="col" className="px-3 py-2 font-medium">{t("schemes.preview.passed")}</th>}
                {thresholdKeys.map((k) => <th key={k} scope="col" className="px-3 py-2 font-medium">{labelOf(k)}</th>)}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="px-3 py-1.5 text-slate-600">{fmtNum(r.raw)}</td>
                  <td className="px-3 py-1.5 font-semibold text-slate-900">{fmtNum(r.display_value)}</td>
                  {showLabel && <td className="px-3 py-1.5">{label(r)}</td>}
                  {showPct && <td className="px-3 py-1.5">{fmtPercentile(r.percentile)}</td>}
                  {showPassed && <td className="px-3 py-1.5"><YesNo v={r.passed} /></td>}
                  {thresholdKeys.map((k) => <td key={k} className="px-3 py-1.5"><YesNo v={r.thresholds?.[k] ?? null} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function YesNo({ v }: { v: boolean | null | undefined }) {
  const { t } = useTranslation();
  if (v === null || v === undefined) return null;
  return v ? (
    <span className="inline-flex items-center gap-1 text-emerald-700"><Check className="h-4 w-4" aria-hidden="true" />{t("schemes.preview.yes")}</span>
  ) : (
    <span className="inline-flex items-center gap-1 text-slate-500"><X className="h-4 w-4" aria-hidden="true" />{t("schemes.preview.no")}</span>
  );
}
