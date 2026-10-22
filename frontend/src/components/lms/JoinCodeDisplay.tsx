"use client";

import React, { useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { formatJoinCode } from "@/lib/lms/courses";

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
    <div className="flex items-center gap-3">
      <code className="select-all rounded-xl bg-slate-100 px-4 py-2 font-mono text-xl font-bold tracking-widest text-slate-900">{formatted}</code>
      <button type="button" onClick={copy}
        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
        {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
        <span aria-live="polite">{copied ? t("lms.common.copied") : t("lms.common.copy")}</span>
      </button>
    </div>
  );
}
