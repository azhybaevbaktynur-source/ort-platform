"use client";

import React, { useId } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { AGE_BANDS, type AgeBand } from "@/components/privacy/privacyApi";
import { cn, focusRing } from "@/components/ui";

/** One compact row of three pills (the same bands as `AgeButtons`, never a birth date). Nothing is preselected. */
export function AgeRow({ value, onChoose }: { value: AgeBand | null; onChoose: (band: AgeBand) => void }) {
  const { t } = useTranslation();
  const labelId = useId();
  return (
    <div role="group" aria-labelledby={labelId}>
      <p id={labelId} className="mb-1.5 text-sm font-medium text-slate-800">{t("auth.ageRowLabel")}</p>
      <div className="grid grid-cols-3 gap-2">
        {AGE_BANDS.map((band) => (
          <button key={band} type="button" aria-pressed={value === band} onClick={() => onChoose(band)}
            className={cn("min-h-11 rounded-xl border px-1 text-sm font-semibold transition-colors", focusRing,
              value === band ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50")}>
            {t(`privacy.age.${band}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
