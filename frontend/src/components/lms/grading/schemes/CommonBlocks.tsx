"use client";

import React, { useId } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  KNOWN_THRESHOLD_KEYS, ROUNDING_MODES, type CommonParams, type RoundingMode, type SchemeParams, type ThresholdParams,
} from "@/lib/lms/gradingTypes";
import { btnSmall, inputCls, labelCls } from "@/components/lms/content/ui";
import { GroupTitle, NumField, NumInput, RowActions } from "./fields";
import { CAPS } from "./params";

/**
 * Optional blocks every scheme type supports (P4-3): rounding, percentile, thresholds, zero-raw value,
 * per-section application. Each block is off (absent) until enabled.
 */
export function CommonBlocks({
  params, onChange, defaultOpen = false,
}: {
  params: SchemeParams;
  onChange: (p: SchemeParams) => void;
  defaultOpen?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const p = params as CommonParams;
  const set = (patch: Partial<CommonParams>) => onChange({ ...params, ...patch } as SchemeParams);
  const toggle = (key: string, label: string, on: boolean, enable: () => void, disable: () => void) => (
    <label htmlFor={`${id}-${key}`} className="flex items-center gap-2 text-sm font-medium text-slate-800">
      <input id={`${id}-${key}`} type="checkbox" checked={on} onChange={(e) => (e.target.checked ? enable() : disable())} />
      {label}
    </label>
  );
  const th: ThresholdParams[] = p.thresholds ?? [];
  const setTh = (next: ThresholdParams[]) => set({ thresholds: next });
  const active = [p.rounding, p.percentile, th.length > 0, p.zero_raw, p.apply_to_sections].filter(Boolean).length;

  return (
    <details open={defaultOpen || active > 0} className="rounded-2xl border border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-semibold text-slate-900">
        {t("schemes.common.advanced")}
        {active > 0 && <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{active}</span>}
      </summary>
      <div className="mt-4 space-y-5">
        {/* rounding */}
        <section className="space-y-2">
          {toggle("rounding", t("schemes.common.rounding"), !!p.rounding,
            () => set({ rounding: { mode: "half_up", decimals: 0 } }), () => set({ rounding: undefined }))}
          {!p.rounding && <p className="text-xs text-slate-500">{t("schemes.common.roundingDefault")}</p>}
          {p.rounding && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor={`${id}-rmode`} className={labelCls}>{t("schemes.common.roundingMode")}</label>
                <select id={`${id}-rmode`} className={inputCls} value={p.rounding.mode}
                  onChange={(e) => set({ rounding: { ...p.rounding!, mode: e.target.value as RoundingMode } })}>
                  {ROUNDING_MODES.map((m) => <option key={m} value={m}>{t(`schemes.common.modes.${m}`)}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor={`${id}-rdec`} className={labelCls}>{t("schemes.common.decimals")}</label>
                <select id={`${id}-rdec`} className={inputCls} value={p.rounding.decimals}
                  onChange={(e) => set({ rounding: { ...p.rounding!, decimals: Number(e.target.value) } })}>
                  {[0, 1, 2].map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
            </div>
          )}
        </section>

        {/* percentile */}
        <section className="space-y-2">
          {toggle("pct", t("schemes.common.percentile"), !!p.percentile,
            () => set({ percentile: { mean: 50, sd: 15, min: 1, max: 99.9, decimals: 1 } }), () => set({ percentile: undefined }))}
          <p className="text-xs text-slate-500">{t("schemes.common.percentileHint")}</p>
          {p.percentile && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <NumField label={t("schemes.common.mean")} value={p.percentile.mean} onChange={(v) => set({ percentile: { ...p.percentile!, mean: v as number } })} />
              <NumField label={t("schemes.common.sd")} value={p.percentile.sd} onChange={(v) => set({ percentile: { ...p.percentile!, sd: v as number } })} />
              <NumField label={t("schemes.common.pctMin")} value={p.percentile.min} onChange={(v) => set({ percentile: { ...p.percentile!, min: v as number } })} />
              <NumField label={t("schemes.common.pctMax")} value={p.percentile.max} onChange={(v) => set({ percentile: { ...p.percentile!, max: v as number } })} />
              <div>
                <label htmlFor={`${id}-pdec`} className={labelCls}>{t("schemes.common.decimals")}</label>
                <select id={`${id}-pdec`} className={inputCls} value={p.percentile.decimals}
                  onChange={(e) => set({ percentile: { ...p.percentile!, decimals: Number(e.target.value) } })}>
                  {[0, 1, 2].map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
            </div>
          )}
        </section>

        {/* thresholds */}
        <section className="space-y-2">
          <GroupTitle>{t("schemes.common.thresholds")}</GroupTitle>
          <p className="text-xs text-slate-500">{t("schemes.common.thresholdsHint")}</p>
          {th.map((x, i) => (
            <div key={i} className="grid grid-cols-[1fr_7rem_auto] items-end gap-2">
              <div>
                {i === 0 && <span className={labelCls}>{t("schemes.common.thresholdKey")}</span>}
                <input type="text" list={`${id}-thkeys`} className={inputCls} value={x.key} maxLength={CAPS.keyChars}
                  aria-label={`${t("schemes.common.thresholdKey")} ${i + 1}`}
                  onChange={(e) => setTh(th.map((y, j) => (j === i ? { ...y, key: e.target.value } : y)))} />
              </div>
              <div>
                {i === 0 && <span className={labelCls}>{t("schemes.common.thresholdMin")}</span>}
                <NumInput value={x.min_value} ariaLabel={`${t("schemes.common.thresholdMin")} ${i + 1}`}
                  onChange={(v) => setTh(th.map((y, j) => (j === i ? { ...y, min_value: v as number } : y)))} />
              </div>
              <RowActions index={i} count={th.length} minRows={0} onRemove={(k) => setTh(th.filter((_, j) => j !== k))} />
            </div>
          ))}
          <datalist id={`${id}-thkeys`}>
            {KNOWN_THRESHOLD_KEYS.map((k) => <option key={k} value={k}>{t(`schemes.thresholdKeys.${k}`)}</option>)}
          </datalist>
          <button type="button" className={`${btnSmall} inline-flex items-center gap-1`} disabled={th.length >= CAPS.thresholds}
            onClick={() => setTh([...th, { key: "", min_value: 0 }])}>
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />{t("schemes.common.addThreshold")}
          </button>
        </section>

        {/* zero raw */}
        <section className="space-y-2">
          {toggle("zero", t("schemes.common.zeroRaw"), !!p.zero_raw,
            () => set({ zero_raw: { value: 0, percentile: 0 } }), () => set({ zero_raw: undefined }))}
          <p className="text-xs text-slate-500">{t("schemes.common.zeroRawHint")}</p>
          {p.zero_raw && (
            <div className="grid grid-cols-2 gap-3">
              <NumField label={t("schemes.common.zeroValue")} value={p.zero_raw.value} onChange={(v) => set({ zero_raw: { ...p.zero_raw!, value: v as number } })} />
              <NumField label={t("schemes.common.zeroPercentile")} value={p.zero_raw.percentile} onChange={(v) => set({ zero_raw: { ...p.zero_raw!, percentile: v as number } })} />
            </div>
          )}
        </section>

        {/* sections */}
        <section className="space-y-1">
          {toggle("sections", t("schemes.common.applyToSections"), !!p.apply_to_sections,
            () => set({ apply_to_sections: true }), () => set({ apply_to_sections: undefined }))}
          <p className="text-xs text-slate-500">{t("schemes.common.applyToSectionsHint")}</p>
        </section>
      </div>
    </details>
  );
}
