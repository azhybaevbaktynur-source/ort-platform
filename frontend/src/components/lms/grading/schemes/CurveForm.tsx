"use client";

import React from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { CurveParams, CurveSegment, SchemeParams } from "@/lib/lms/gradingTypes";
import { MathRenderer } from "@/components/math/MathRenderer";
import { btnSmall, cardCls } from "@/components/lms/content/ui";
import { NumField, NumInput, RowActions } from "./fields";
import { CAPS, splitLastSegment } from "./params";

const FORMULA =
  "$$v = v_0 + (v_1 - v_0)\\cdot\\left(\\dfrac{r - r_0}{r_1 - r_0}\\right)^{k},\\qquad r = \\dfrac{\\text{raw}}{\\text{possible}}$$";

const COLS: (keyof CurveSegment)[] = ["from_ratio", "to_ratio", "from_value", "to_value", "exponent"];

/** `piecewise_curve`: scale plus a contiguous chain of power segments over the ratio 0..1. */
export function CurveForm({
  params, onChange, readOnly,
}: {
  params: CurveParams;
  onChange: (p: SchemeParams) => void;
  readOnly: boolean;
}) {
  const { t } = useTranslation();
  const segs = params.segments ?? [];
  const setSegs = (next: CurveSegment[]) => onChange({ ...params, segments: next });
  const patch = (i: number, k: keyof CurveSegment, v: number | null) =>
    setSegs(segs.map((s, j) => (j === i ? { ...s, [k]: v as number } : s)));
  const remove = (i: number) => {
    // keep the chain contiguous: the next segment (or the previous one, for the last) absorbs the gap
    const next = segs.filter((_, j) => j !== i);
    if (next.length && i < segs.length) {
      if (i === 0) next[0] = { ...next[0], from_ratio: 0, from_value: segs[0].from_value };
      else if (i === segs.length - 1) next[i - 1] = { ...next[i - 1], to_ratio: 1, to_value: segs[i].to_value };
      else next[i] = { ...next[i], from_ratio: segs[i - 1].to_ratio, from_value: segs[i - 1].to_value };
    }
    setSegs(next);
  };

  return (
    <div className={`${cardCls} space-y-4`}>
      <p className="text-sm text-slate-600">{t("schemes.typeHints.piecewise_curve")}</p>
      <div className="grid max-w-md grid-cols-2 gap-3">
        <NumField label={t("schemes.fields.scaleMin")} value={params.scale_min} onChange={(v) => onChange({ ...params, scale_min: v as number })} />
        <NumField label={t("schemes.fields.scaleMax")} value={params.scale_max} onChange={(v) => onChange({ ...params, scale_max: v as number })} />
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
        <MathRenderer content={FORMULA} />
        <p className="mt-1 text-xs text-slate-500">{t("schemes.curve.formulaHint")}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] text-sm">
          <caption className="sr-only">{t("schemes.curve.segments")}</caption>
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th scope="col" className="px-1 py-1 font-medium">#</th>
              {COLS.map((c) => <th key={c} scope="col" className="px-1 py-1 font-medium">{t(`schemes.curve.${c}`)}</th>)}
              <th scope="col" className="px-1 py-1"><span className="sr-only">{t("schemes.editor.actions")}</span></th>
            </tr>
          </thead>
          <tbody>
            {segs.map((s, i) => (
              <tr key={i} className="align-top">
                <td className="px-1 py-1 pt-3 text-xs text-slate-500">{i + 1}</td>
                {COLS.map((c) => (
                  <td key={c} className="px-1 py-1">
                    <NumInput value={s[c]} ariaLabel={`${t(`schemes.curve.${c}`)} ${i + 1}`} onChange={(v) => patch(i, c, v)}
                      className="w-full min-w-[4.5rem] rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-50" />
                  </td>
                ))}
                <td className="px-1 py-1"><RowActions index={i} count={segs.length} onRemove={remove} disabled={readOnly} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!readOnly && (
        <button type="button" className={`${btnSmall} inline-flex items-center gap-1`} disabled={segs.length >= CAPS.segments}
          onClick={() => setSegs(splitLastSegment(segs, params.scale_min ?? null, params.scale_max ?? null))}>
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />{t("schemes.curve.add")}
        </button>
      )}
      <p className="text-xs text-slate-500">{t("schemes.curve.hint")}</p>
    </div>
  );
}
