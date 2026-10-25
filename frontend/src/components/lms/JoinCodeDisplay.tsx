"use client";

import React, { useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { formatJoinCode } from "@/lib/lms/courses";
import { Button } from "@/components/ui";

/** Join code with a copy button. Phase 6b S5c (UX T20): the code never wraps ("VDMW-YX3H" stays on one line at 375 px). */
export function JoinCodeDisplay({ code }: { code: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const formatted = formatJoinCode(code);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(formatted);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable: the code stays selectable */
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-3">
      <code className="select-all whitespace-nowrap rounded-xl bg-slate-100 px-3 py-2 font-mono text-lg font-bold tracking-wider text-slate-900 sm:px-4 sm:text-xl sm:tracking-widest">{formatted}</code>
      <Button variant="secondary" size="sm" onClick={copy}
        leftIcon={copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}>
        <span aria-live="polite">{copied ? t("lms.common.copied") : t("lms.common.copy")}</span>
      </Button>
    </div>
  );
}
