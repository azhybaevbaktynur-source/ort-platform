"use client";

// F5b (COURSE_LESSONS_DESIGN 5, 7.2): a lesson of a Pro module for a student without access. The Тесты page's lock
// cover (`LockOverlay`) over an empty 16:9 card, with the gold "Открыть доступ" pill (gold only for money,
// STUDENT_UI_FIX_PLAN 4.1). The server sent no address, video id, page id or file id for this row, so there is
// nothing to load behind the cover.
import React from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { GoldPill, LockOverlay } from "@/components/ui";

export function ProLockCard() {
  const { lang, t } = useTranslation();
  return (
    <LockOverlay locked title={t("modules.overview.proLockTitle")} body={t("modules.overview.proLockBody")}
      action={<GoldPill href={`/${lang}/unlock`} icon={<Lock />}>{t("modules.overview.unlock")}</GoldPill>}>
      <div className="aspect-video min-h-[16rem] w-full rounded-card bg-gradient-to-br from-navy-800 to-[#13698f]" />
    </LockOverlay>
  );
}

/** The gold "Pro" chip of a Pro module the student cannot open yet. */
export function ProChip() {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-gold-300 bg-gold-100 px-2 py-0.5 text-xs font-semibold leading-5 text-gold-900">
      <Lock aria-hidden="true" className="h-3.5 w-3.5 text-gold-700" />{t("modules.overview.pro")}
    </span>
  );
}
