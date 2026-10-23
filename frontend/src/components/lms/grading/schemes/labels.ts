"use client";

import { useCallback } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { KNOWN_THRESHOLD_KEYS, type SchemeLabelValue } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";

const THRESHOLDS = new Set<string>(KNOWN_THRESHOLD_KEYS);

/** Text of one `SchemeVersionOut.labels` value: lookup labels are plain strings, band labels localized text. */
export function labelText(value: SchemeLabelValue | null | undefined, lang: Lang): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return pickLocalized(value, lang);
}

/**
 * Text for a grade label or threshold key: a key found in `labels` (a scheme ref's / grade's `labels` map, or band
 * labels) is rendered with `labelText`; otherwise `pass`/`fail` and known thresholds are translated; anything else
 * is shown as stored.
 */
export function useSchemeLabel(): (key: string, labels?: Record<string, SchemeLabelValue> | null) => string {
  const { lang, t } = useTranslation();
  return useCallback(
    (key: string, labels?: Record<string, SchemeLabelValue> | null) => {
      if (labels && Object.prototype.hasOwnProperty.call(labels, key)) {
        const text = labelText(labels[key], lang as Lang);
        if (text) return text;
      }
      if (key === "pass" || key === "fail") return t(`schemes.labels.${key}`);
      if (THRESHOLDS.has(key)) return t(`schemes.thresholdKeys.${key}`);
      return key;
    },
    [lang, t],
  );
}
