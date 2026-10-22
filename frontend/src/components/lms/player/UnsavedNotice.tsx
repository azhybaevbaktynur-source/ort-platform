"use client";

import React, { useState } from "react";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { parseUnsavedParam } from "@/lib/lms/attemptClient";

/**
 * Non-blocking after-submit notice (B2): how many answers from the final submit were not stored, per reason.
 * `value` is the `?unsaved=` parameter written by the player (see `unsavedParam`).
 */
export function UnsavedNotice({ value }: { value: string | null }) {
  const { t } = useTranslation();
  const [hidden, setHidden] = useState(false);
  const groups = parseUnsavedParam(value);
  if (hidden || groups.length === 0) return null;
  return (
    <div role="status" className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <ul className="flex-1 space-y-1">
        {groups.map(([group, n]) => (
          <li key={group}>{t(`player.unsaved.${group}`, { n })}</li>
        ))}
      </ul>
      <button type="button" className="font-semibold underline" onClick={() => setHidden(true)}>
        {t("player.dismiss")}
      </button>
    </div>
  );
}
