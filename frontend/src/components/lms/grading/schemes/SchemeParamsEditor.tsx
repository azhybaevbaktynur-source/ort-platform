"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type {
  BandsParams, CurveParams, LookupTableParams, PassFailParams, PercentParams, PointsParams, SchemeParams, SchemeType,
} from "@/lib/lms/gradingTypes";
import { BandsForm } from "./BandsForm";
import { CommonBlocks } from "./CommonBlocks";
import { CurveForm } from "./CurveForm";
import { LookupTableForm } from "./LookupTableForm";
import { PassFailForm, PercentForm, PointsForm } from "./SimpleForms";
import type { ParamIssue } from "./params";

/** Type-specific form plus the common optional blocks. `readOnly` disables every input (system schemes, viewers). */
export function SchemeParamsEditor({
  type, params, onChange, readOnly,
}: {
  type: SchemeType;
  params: SchemeParams;
  onChange: (p: SchemeParams) => void;
  readOnly: boolean;
}) {
  let form: React.ReactNode;
  switch (type) {
    case "points": form = <PointsForm params={params as PointsParams} onChange={onChange} />; break;
    case "percent": form = <PercentForm params={params as PercentParams} onChange={onChange} />; break;
    case "pass_fail": form = <PassFailForm params={params as PassFailParams} onChange={onChange} />; break;
    case "bands": form = <BandsForm params={params as BandsParams} onChange={onChange} readOnly={readOnly} />; break;
    case "piecewise_curve": form = <CurveForm params={params as CurveParams} onChange={onChange} readOnly={readOnly} />; break;
    case "lookup_table": form = <LookupTableForm params={params as LookupTableParams} onChange={onChange} readOnly={readOnly} />; break;
  }
  return (
    <fieldset disabled={readOnly} className="min-w-0 space-y-4">
      {form}
      <CommonBlocks params={params} onChange={onChange} defaultOpen={type === "piecewise_curve"} />
    </fieldset>
  );
}

/** Client-side problems found in the params (labels `schemes.blocks.*` + `schemes.validation.*`). */
export function ParamIssues({ issues }: { issues: ParamIssue[] }) {
  const { t } = useTranslation();
  if (!issues.length) return null;
  return (
    <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-900">
      <p className="flex items-center gap-2 font-semibold">
        <AlertTriangle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />{t("schemes.editor.fixIssues")}
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-6">
        {issues.slice(0, 20).map((x, i) => (
          <li key={i}>
            {t(`schemes.blocks.${x.block}`)}{x.row ? ` ${t("schemes.editor.rowN", { n: x.row })}` : ""}: {t(`schemes.validation.${x.code}`, { max: x.max ?? 0 })}
          </li>
        ))}
      </ul>
    </div>
  );
}
