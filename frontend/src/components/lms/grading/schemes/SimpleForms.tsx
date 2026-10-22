"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { PassFailParams, PercentParams, PointsParams, SchemeParams } from "@/lib/lms/gradingTypes";
import { cardCls } from "@/components/lms/content/ui";
import { NumField } from "./fields";

type FormProps<P> = { params: P; onChange: (p: SchemeParams) => void };

function OptionalPass({ params, onChange, hintKey }: FormProps<PointsParams | PercentParams> & { hintKey: string }) {
  const { t } = useTranslation();
  return (
    <div className={`${cardCls} space-y-3`}>
      <p className="text-sm text-slate-600">{t(hintKey)}</p>
      <div className="max-w-xs">
        <NumField label={t("schemes.fields.passThresholdOptional")} value={params.pass_threshold_percent ?? null}
          hint={t("schemes.fields.passThresholdHint")}
          onChange={(v) => onChange({ ...params, pass_threshold_percent: v })} />
      </div>
    </div>
  );
}

/** `points`: the display value is the points themselves. */
export function PointsForm(props: FormProps<PointsParams>) {
  return <OptionalPass {...props} hintKey="schemes.typeHints.points" />;
}

/** `percent`: the display value is raw / possible x 100. */
export function PercentForm(props: FormProps<PercentParams>) {
  return <OptionalPass {...props} hintKey="schemes.typeHints.percent" />;
}

/** `pass_fail`: pass at or above the threshold percent. */
export function PassFailForm({ params, onChange }: FormProps<PassFailParams>) {
  const { t } = useTranslation();
  return (
    <div className={`${cardCls} space-y-3`}>
      <p className="text-sm text-slate-600">{t("schemes.typeHints.pass_fail")}</p>
      <div className="max-w-xs">
        <NumField label={t("schemes.fields.passThreshold")} value={params.pass_threshold_percent}
          hint={t("schemes.fields.passThresholdHint")}
          onChange={(v) => onChange({ ...params, pass_threshold_percent: v as number })} />
      </div>
    </div>
  );
}
