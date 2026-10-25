"use client";

import React from "react";
import { Check, CloudOff, Loader2, AlertTriangle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { QueueSnapshot } from "@/lib/lms/attemptClient";
import { Button } from "@/components/ui";

export function SaveStatus({ snap, onRetry }: { snap: QueueSnapshot; onRetry?: () => void }) {
  const { t } = useTranslation();
  let icon = <Check className="h-3.5 w-3.5" aria-hidden="true" />;
  let text = t("player.save.saved");
  let tone = "text-emerald-700 bg-emerald-50 border-emerald-200";
  const retry = snap.status === "offline" || snap.status === "error" || snap.status === "auth";
  if (snap.status === "saving" || (snap.status === "idle" && snap.pending > 0)) {
    icon = <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />;
    text = t("player.save.saving");
    tone = "text-slate-600 bg-slate-50 border-slate-200";
  } else if (snap.status === "offline") {
    icon = <CloudOff className="h-3.5 w-3.5" aria-hidden="true" />;
    text = t("player.save.offline", { n: snap.pending });
    tone = "text-amber-800 bg-amber-50 border-amber-200";
  } else if (snap.status === "auth") {
    icon = <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />;
    text = t("player.save.auth", { n: snap.pending });
    tone = "text-red-700 bg-red-50 border-red-200";
  } else if (snap.status === "error" || snap.status === "closed") {
    icon = <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />;
    text = t("player.save.error", { n: snap.pending });
    tone = "text-red-700 bg-red-50 border-red-200";
  }
  return (
    <div className="flex min-w-0 items-center gap-2" role="status" aria-live="polite">
      <span className={`inline-flex min-w-0 items-center gap-1.5 rounded-2xl border px-2.5 py-1 text-xs font-medium leading-4 ${tone}`}>
        <span className="shrink-0">{icon}</span>
        <span className="min-w-0">{text}</span>
      </span>
      {retry && onRetry ? (
        <Button variant="link" size="sm" onClick={onRetry} className="shrink-0 text-xs">
          {t("lms.common.retry")}
        </Button>
      ) : null}
    </div>
  );
}
