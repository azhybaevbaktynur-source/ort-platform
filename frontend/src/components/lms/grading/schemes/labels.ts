"use client";

import { useCallback } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { KNOWN_THRESHOLD_KEYS } from "@/lib/lms/gradingTypes";

const THRESHOLDS = new Set<string>(KNOWN_THRESHOLD_KEYS);

/**
 * Text for a grade label or threshold key: `pass`/`fail` and known thresholds are translated,
 * anything else (lookup labels, custom keys) is shown as stored.
 */
export function useSchemeLabel(): (key: string) => string {
  const { t } = useTranslation();
  return useCallback(
    (key: string) => {
      if (key === "pass" || key === "fail") return t(`schemes.labels.${key}`);
      if (THRESHOLDS.has(key)) return t(`schemes.thresholdKeys.${key}`);
      return key;
    },
    [t],
  );
}
