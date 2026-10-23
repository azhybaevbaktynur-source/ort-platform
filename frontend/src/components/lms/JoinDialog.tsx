"use client";

import React, { useEffect, useId } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { JoinOut } from "@/lib/lms/types";
import { JoinCodeForm } from "./JoinCodeForm";

export function JoinDialog({ open, onClose, onJoined }: { open: boolean; onClose: () => void; onJoined: (r: JoinOut) => void }) {
  const { t } = useTranslation();
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 id={titleId} className="mb-4 text-lg font-bold text-slate-900">{t("courses.join.title")}</h2>
        <JoinCodeForm onJoined={onJoined} />
        <button type="button" onClick={onClose} className="mt-3 w-full rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
          {t("lms.common.cancel")}
        </button>
      </div>
    </div>
  );
}
