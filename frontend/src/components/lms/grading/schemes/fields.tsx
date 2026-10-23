"use client";

import React, { useEffect, useId, useState } from "react";
import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { inputCls, labelCls } from "@/components/lms/content/ui";
import { parseNum } from "./params";

/**
 * Number input that keeps what the user types ("0.", "1,5", "") and reports the parsed value
 * (null while empty/invalid). Re-syncs when the value changes from outside.
 */
export function NumInput({
  id, value, onChange, disabled, ariaLabel, placeholder, className = inputCls,
}: {
  id?: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  disabled?: boolean;
  ariaLabel?: string;
  placeholder?: string;
  className?: string;
}) {
  const [text, setText] = useState(value === null || value === undefined || Number.isNaN(value) ? "" : String(value));
  useEffect(() => {
    setText((cur) => {
      const parsed = parseNum(cur);
      const v = value === undefined || (typeof value === "number" && Number.isNaN(value)) ? null : value;
      return parsed === v ? cur : v === null ? "" : String(v);
    });
  }, [value]);
  return (
    <input id={id} type="text" inputMode="decimal" autoComplete="off" value={text} disabled={disabled} aria-label={ariaLabel}
      placeholder={placeholder} className={className}
      onChange={(e) => { setText(e.target.value); onChange(parseNum(e.target.value)); }} />
  );
}

/** Labelled number field. */
export function NumField({
  label, value, onChange, hint, disabled, placeholder,
}: {
  label: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  hint?: string;
  disabled?: boolean;
  placeholder?: string;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className={labelCls}>{label}</label>
      <NumInput id={id} value={value} onChange={onChange} disabled={disabled} placeholder={placeholder} />
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

/** Up / down / remove buttons for one row of a list editor. */
export function RowActions({
  index, count, onMove, onRemove, disabled, minRows = 1,
}: {
  index: number;
  count: number;
  onMove?: (from: number, to: number) => void;
  onRemove: (index: number) => void;
  disabled?: boolean;
  minRows?: number;
}) {
  const { t } = useTranslation();
  const btn = "rounded-lg border border-slate-300 bg-white p-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-40";
  return (
    <div className="flex items-center gap-1">
      {onMove && (
        <>
          <button type="button" className={btn} disabled={disabled || index === 0} onClick={() => onMove(index, index - 1)}
            aria-label={t("schemes.editor.moveUp", { n: index + 1 })}>
            <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button type="button" className={btn} disabled={disabled || index === count - 1} onClick={() => onMove(index, index + 1)}
            aria-label={t("schemes.editor.moveDown", { n: index + 1 })}>
            <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </>
      )}
      <button type="button" className={`${btn} text-red-700`} disabled={disabled || count <= minRows} onClick={() => onRemove(index)}
        aria-label={t("schemes.editor.removeRow", { n: index + 1 })}>
        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

/** Small uppercase caption above a group of inputs. */
export function GroupTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold text-slate-900">{children}</h3>;
}
