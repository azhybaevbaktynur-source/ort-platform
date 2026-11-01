"use client";

import React, { useId } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Button } from "@/components/ui";
import { AGE_BANDS, type AgeBand } from "./privacyApi";

/** One choice of three buttons, never a birth date (PHASE_11_DESIGN 3.2). `value` marks the chosen one. */
export function AgeButtons({ value, onChoose }: { value?: AgeBand | null; onChoose: (band: AgeBand) => void }) {
  const { t } = useTranslation();
  const labelId = useId();
  return (
    <div role="group" aria-labelledby={labelId}>
      <p id={labelId} className="mb-3 text-base font-semibold text-slate-900">{t("privacy.age.question")}</p>
      <div className="space-y-2">
        {AGE_BANDS.map((band) => (
          <Button key={band} type="button" size="lg" fullWidth variant={value === band ? "primary" : "secondary"}
            aria-pressed={value === undefined ? undefined : value === band} onClick={() => onChoose(band)}>
            {t(`privacy.age.${band}`)}
          </Button>
        ))}
      </div>
    </div>
  );
}
