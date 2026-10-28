"use client";

import React, { useId, useLayoutEffect, useRef, useState } from "react";
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
  onKeyDown,
  inputRef,
  ariaLabel,
  smartPreview = false,
  autoGrow = false,
  toolbarOnFocus = false,
  error,
  invalid = false,
  describedBy,
}: {
  label?: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  maxLength?: number;
  disabled?: boolean;
  compact?: boolean;
  /** Phase 7c S5 (opt-in, the quiz card's answers): keys pressed in the textarea. */
  onKeyDown?: React.KeyboardEventHandler<HTMLTextAreaElement>;
  /** Phase 7c S5: receives the textarea element (focus management of the quiz card's answers). */
  inputRef?: (el: HTMLTextAreaElement | null) => void;
  ariaLabel?: string;
  /** Phase 7c UX (opt-in, the quiz card): the preview only when the text holds math or markup (it would differ). */
  smartPreview?: boolean;
  /** Phase 7c UX (opt-in, the quiz card's answers): the textarea grows with its text instead of a fixed height. */
  autoGrow?: boolean;
  /** Phase 7c UX (opt-in, the quiz card's answers): the formatting toolbar shows only while the field has focus. */
  toolbarOnFocus?: boolean;
  /** Phase 7c UX (opt-in, the quiz card): an error shown under the field and linked with `aria-describedby`. */
  error?: string | null;
  /** Phase 7c UX (opt-in): marked invalid, described by a message rendered elsewhere (`describedBy` = its id). */
  invalid?: boolean;
  describedBy?: string;
}) {
  const { t } = useTranslation();
  const id = useId();
  const errId = `${id}-err`;
  const ref = useRef<HTMLTextAreaElement>(null);
  const [focused, setFocused] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!autoGrow || !el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + 2}px`;
  }, [autoGrow, value]);

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

  const showToolbar = !compact && (!toolbarOnFocus || focused);
  // Safari does not focus a clicked button: keep the focus in the textarea so the toolbar stays while it is used.
  const keep = toolbarOnFocus ? (e: React.MouseEvent) => e.preventDefault() : undefined;
  const showPreview = !!value.trim() && (!smartPreview || /[$<\\]/.test(value));

  return (
    <div
      onFocus={toolbarOnFocus ? () => setFocused(true) : undefined}
      onBlur={toolbarOnFocus ? (e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false); } : undefined}>
      {label && <label htmlFor={id} className={labelCls}>{label}</label>}
      {showToolbar && (
        // Phase 6b S5c: an even 2 x 2 grid of 44 px buttons at 375 px instead of ragged wrapped rows; one row from `sm`.
        <div role="toolbar" aria-label={t("teaching.formatToolbar")} className={toolbarOnFocus ? "mb-1.5 flex flex-wrap gap-1.5" : "mb-1.5 grid grid-cols-2 gap-1.5 sm:flex sm:flex-wrap"}>
          <button type="button" disabled={disabled} className={btnSmall} onMouseDown={keep} onClick={() => wrap("$", "$")}>{t("bank.rich.math")}</button>
          <button type="button" disabled={disabled} className={btnSmall} onMouseDown={keep} onClick={() => wrap("$$", "$$")}>{t("bank.rich.mathBlock")}</button>
          <button type="button" disabled={disabled} className={btnSmall} onMouseDown={keep} onClick={() => wrap("<u>", "</u>")}>{t("bank.rich.underline")}</button>
          <button type="button" disabled={disabled} className={btnSmall} onMouseDown={keep} onClick={() => wrap("<b>", "</b>")}>{t("bank.rich.bold")}</button>
        </div>
      )}
      <textarea id={id} ref={(el) => { ref.current = el; inputRef?.(el); }} rows={rows} value={value} maxLength={maxLength} disabled={disabled}
        onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} aria-label={ariaLabel}
        aria-invalid={error || invalid ? true : undefined} aria-describedby={error ? errId : describedBy}
        className={`${inputCls} font-mono${autoGrow ? " resize-none overflow-hidden" : ""}${error || invalid ? " border-red-500" : ""}`} />
      {error && <p id={errId} className="mt-1 text-sm text-red-700">{error}</p>}
      {showPreview && (
        <div className="mt-1.5 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-2">
          <p className="mb-0.5 text-xs font-medium uppercase tracking-wide text-slate-400">{t("bank.rich.preview")}</p>
          <MathRenderer content={value} />
        </div>
      )}
    </div>
  );
}
