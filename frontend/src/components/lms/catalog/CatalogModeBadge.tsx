"use client";

// Phase 9 S4: how a student joins a catalog course, as a badge (open, application, code, closed).
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { EnrollmentMode } from "@/lib/lms/types";
import { Badge, type BadgeTone } from "@/components/ui";

const TONE: Record<EnrollmentMode, BadgeTone> = {
  open: "success",
  form_auto: "info",
  form_review: "info",
  invite_code: "neutral",
  closed: "neutral",
};

export function CatalogModeBadge({ mode }: { mode: EnrollmentMode }) {
  const { t } = useTranslation();
  return <Badge tone={TONE[mode]}>{t(`catalog.modes.${mode}`)}</Badge>;
}
