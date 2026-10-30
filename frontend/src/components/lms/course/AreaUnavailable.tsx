"use client";

// Phase 8c S1 (PHASE_8C_DESIGN §2.3): what a student sees when opening a course area whose link is hidden (no
// published announcements or files yet). A courtesy page, not a security boundary: the server returns only
// published rows anyway.
import React from "react";
import { EyeOff } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { EmptyState, LinkButton } from "@/components/ui";

export function AreaUnavailable({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  return (
    <EmptyState icon={<EyeOff />} title={t("courseNav.unavailable.title")} description={t("courseNav.unavailable.body")}
      action={<LinkButton href={`/${lang}/courses/${courseId}`} variant="secondary">{t("courseNav.unavailable.back")}</LinkButton>} />
  );
}
