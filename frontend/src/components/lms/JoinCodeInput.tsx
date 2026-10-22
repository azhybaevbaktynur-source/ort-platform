"use client";

import React, { useId } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { formatJoinCode, normalizeJoinCode } from "@/lib/lms/courses";

/** Controlled input; `value` is the normalized code (uppercase, no spaces/dashes), displayed as ABCD-EFGH. */
export function JoinCodeInput({
  value,
  onChange,
  disabled,
  invalid,
  describedBy,
}: {
  value: string;
  onChange: (normalized: string) => void;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
}) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">{t("courses.join.codeLabel")}</label>
      <input
        id={id}
        type="text"
        inputMode="text"
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        maxLength={12}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        value={formatJoinCode(value)}
        onChange={(e) => onChange(normalizeJoinCode(e.target.value).slice(0, 8))}
        placeholder="ABCD-EFGH"
        className="w-full rounded-xl border border-slate-300 px-4 py-3 text-center font-mono text-2xl font-bold tracking-widest text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-100"
      />
    </div>
  );
}
