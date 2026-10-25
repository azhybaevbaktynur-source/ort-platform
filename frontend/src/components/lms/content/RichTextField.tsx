"use client";

import React, { useId, useRef } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { inputCls, labelCls } from "./ui";
import { btnSmall } from "@/components/lms/course/staffUi"; // Phase 6b S5c

/** Textarea with ORT rich text helpers ($math$, <u>, <b>) and a live KaTeX preview. */
export function RichTextField({
  label,
  value,
  onChange,
  rows = 4,
  maxLength,
  disabled,
  compact = false,
}: {
  label?: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  maxLength?: number;
  disabled?: boolean;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const ref = useRef<HTMLTextAreaElement>(null);

  const wrap = (before: string, after: string) => {
    const el = ref.current;
    if (!el) return;
    const s = el.selectionStart ?? value.length;
    const e = el.selectionEnd ?? value.length;
    const next = value.slice(0, s) + before + value.slice(s, e) + after + value.slice(e);
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(s + before.length, e + before.length);
    });
  };

  return (
    <div>
      {label && <label htmlFor={id} className={labelCls}>{label}</label>}
      {!compact && (
        // Phase 6b S5c: an even 2 x 2 grid of 44 px buttons at 375 px instead of ragged wrapped rows; one row from `sm`.
        <div role="toolbar" aria-label={t("teaching.formatToolbar")} className="mb-1.5 grid grid-cols-2 gap-1.5 sm:flex sm:flex-wrap">
          <button type="button" disabled={disabled} className={btnSmall} onClick={() => wrap("$", "$")}>{t("bank.rich.math")}</button>
          <button type="button" disabled={disabled} className={btnSmall} onClick={() => wrap("$$", "$$")}>{t("bank.rich.mathBlock")}</button>
          <button type="button" disabled={disabled} className={btnSmall} onClick={() => wrap("<u>", "</u>")}>{t("bank.rich.underline")}</button>
          <button type="button" disabled={disabled} className={btnSmall} onClick={() => wrap("<b>", "</b>")}>{t("bank.rich.bold")}</button>
        </div>
      )}
      <textarea id={id} ref={ref} rows={rows} value={value} maxLength={maxLength} disabled={disabled}
        onChange={(e) => onChange(e.target.value)} className={`${inputCls} font-mono`} />
      {value.trim() && (
        <div className="mt-1.5 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-2">
          <p className="mb-0.5 text-xs font-medium uppercase tracking-wide text-slate-400">{t("bank.rich.preview")}</p>
          <MathRenderer content={value} />
        </div>
      )}
    </div>
  );
}
