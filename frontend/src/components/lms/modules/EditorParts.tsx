"use client";

// F5c (COURSE_LESSONS_DESIGN §6, §7.3): small pieces of the teacher's module editor: the minutes chip of a lesson row
// (click -> an inline minutes field; Enter saves, Esc cancels, empty clears), the module's Pro switch (platform courses
// only; gold when on), the ↑ ↓ buttons of a row and the duration text ("6 мин", "1 ч 20 мин").
import React, { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Clock, Plus, Star } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { DURATION_S_MAX, DURATION_S_MIN } from "@/lib/lms/modulesTypes";
import { cn, focusRing, toast } from "@/components/ui";

/** Minutes typed by the teacher -> seconds; "" -> null (clears); undefined when not a whole number of 1..600 minutes. */
export function parseMinutes(raw: string): number | null | undefined {
  const v = raw.trim();
  if (v === "") return null;
  if (!/^\d+$/.test(v)) return undefined;
  const s = Number(v) * 60;
  return s >= DURATION_S_MIN && s <= DURATION_S_MAX ? s : undefined;
}

/** "6 мин", "1 ч", "1 ч 20 мин" (rounded to whole minutes). */
export function useDurationText() {
  const { t } = useTranslation();
  return useCallback((seconds: number) => {
    const total = Math.max(1, Math.round(seconds / 60));
    const h = Math.floor(total / 60);
    const m = total % 60;
    if (h === 0) return t("modules.editor.minutes", { n: m });
    return m === 0 ? t("modules.editor.hours", { h }) : t("modules.editor.hoursMinutes", { h, m });
  }, [t]);
}

/** The minutes chip of a page / file / link row. `onSave` resolves true when the server took it (the outline reloads). */
export function DurationChip({ seconds, name, disabled, onSave }: {
  seconds: number | null | undefined;
  name: string;
  disabled?: boolean;
  onSave: (seconds: number | null) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const fmt = useDurationText();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [busy, setBusy] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const settled = useRef(false);

  useEffect(() => {
    if (!editing) return;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [editing]);

  const start = () => {
    setValue(seconds ? String(Math.round(seconds / 60)) : "");
    setInvalid(false);
    settled.current = false;
    setEditing(true);
  };
  const stop = (focus: boolean) => {
    settled.current = true;
    setEditing(false);
    if (focus) window.requestAnimationFrame(() => buttonRef.current?.focus());
  };
  const commit = async (fromBlur: boolean) => {
    if (settled.current || busy) return;
    const s = parseMinutes(value);
    if (s === undefined) {
      // a blur with a bad value gives up quietly; Enter says why and keeps the field
      if (fromBlur) { stop(false); return; }
      setInvalid(true);
      toast.error(t("modules.editor.durationInvalid"));
      return;
    }
    if (s === (seconds ?? null)) { stop(!fromBlur); return; }
    settled.current = true;
    setBusy(true);
    const ok = await onSave(s);
    setBusy(false);
    if (ok) stop(!fromBlur);
    else settled.current = false;
  };

  const label = seconds ? t("modules.editor.durationEdit", { title: name, value: fmt(seconds) }) : t("modules.editor.durationSet", { title: name });

  if (editing) {
    return (
      <span className="inline-flex h-11 shrink-0 items-center gap-1">
        <input ref={inputRef} type="number" inputMode="numeric" min={1} max={600} step={1} value={value} disabled={busy}
          aria-label={t("modules.editor.durationField", { title: name })} aria-invalid={invalid || undefined}
          title={invalid ? t("modules.editor.durationInvalid") : undefined}
          onChange={(e) => { setValue(e.target.value); setInvalid(false); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); void commit(false); }
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); stop(true); }
          }}
          onBlur={() => void commit(true)}
          className={cn("h-9 w-20 rounded-lg border bg-white px-2 text-sm text-slate-900", invalid ? "border-danger-600" : "border-slate-300", focusRing)} />
        <span aria-hidden="true" className="text-sm text-slate-600">{t("modules.editor.durationUnset")}</span>
      </span>
    );
  }
  return (
    <button ref={buttonRef} type="button" disabled={disabled} onClick={start} aria-label={label} title={label}
      className={cn("group/chip inline-flex h-11 shrink-0 items-center rounded-xl px-0.5 disabled:cursor-not-allowed", focusRing)}>
      <span className={cn("inline-flex h-7 items-center gap-1 whitespace-nowrap rounded-full border px-2 text-xs font-medium leading-4 transition-colors",
        seconds
          ? "border-slate-200 bg-slate-50 text-slate-700 group-hover/chip:border-slate-300 group-hover/chip:bg-white"
          : "border-dashed border-slate-300 text-slate-500 group-hover/chip:border-slate-400 group-hover/chip:text-slate-700")}>
        {seconds ? <Clock aria-hidden="true" className="h-3.5 w-3.5" /> : <Plus aria-hidden="true" className="h-3.5 w-3.5" />}
        {seconds ? fmt(seconds) : t("modules.editor.durationUnset")}
      </span>
    </button>
  );
}

/** The module's Pro switch (shown only on platform courses; the server refuses `paid` elsewhere). Gold when on. */
export function ProSwitch({ on, name, busy, disabled, onToggle }: {
  on: boolean; name: string; busy: boolean; disabled?: boolean; onToggle: () => void;
}) {
  const { t } = useTranslation();
  const hint = on ? t("modules.editor.proHintOn") : t("modules.editor.proHintOff");
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={t("modules.editor.proSwitch", { title: name })} title={hint}
      aria-busy={busy || undefined} disabled={disabled || busy} onClick={onToggle}
      className={cn("group/pro inline-flex h-11 shrink-0 items-center rounded-xl px-0.5 disabled:cursor-not-allowed disabled:opacity-60", focusRing)}>
      <span className={cn("inline-flex h-7 items-center gap-1.5 rounded-full border pl-2 pr-1 text-xs font-semibold leading-4 transition-colors",
        on
          ? "border-gold-300 bg-gradient-to-r from-gold-100 to-gold-200 text-gold-900"
          : "border-slate-300 bg-white text-slate-600 group-hover/pro:border-slate-400")}>
        <Star aria-hidden="true" className={cn("h-3.5 w-3.5", on ? "fill-current text-gold-700" : "text-slate-400")} />
        {t("modules.editor.pro")}
        <span aria-hidden="true" className={cn("relative inline-flex h-4 w-7 shrink-0 rounded-full transition-colors", on ? "bg-gold-600" : "bg-slate-300")}>
          <span className={cn("absolute top-0.5 h-3 w-3 rounded-full bg-white shadow-sm transition-all", on ? "left-3.5" : "left-0.5")} />
        </span>
      </span>
    </button>
  );
}

/** ↑ ↓ of a row: always rendered from `sm` (visible on hover / focus at `lg`), reachable by keyboard. An end of the list
 * is `aria-disabled` (not `disabled`), so focus stays on the button after a move to the top or the bottom. */
export function MoveButtons({ name, first, last, onMove }: {
  name: string; first: boolean; last: boolean; onMove: (dir: -1 | 1) => void;
}) {
  const { t } = useTranslation();
  const btn = (dir: -1 | 1, off: boolean, label: string, Icon: typeof ArrowUp) => (
    <button type="button" data-move={dir < 0 ? "up" : "down"} aria-label={label} title={label} aria-disabled={off || undefined}
      onClick={() => { if (!off) onMove(dir); }}
      className={cn("inline-flex h-11 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900",
        "aria-disabled:cursor-not-allowed aria-disabled:opacity-40 aria-disabled:hover:bg-transparent", focusRing)}>
      <Icon aria-hidden="true" className="h-4 w-4" />
    </button>
  );
  return (
    <span className="hidden shrink-0 items-center sm:inline-flex lg:opacity-0 lg:transition-opacity lg:focus-within:opacity-100 lg:group-hover/row:opacity-100">
      {btn(-1, first, t("modules.editor.moveItemUp", { title: name }), ArrowUp)}
      {btn(1, last, t("modules.editor.moveItemDown", { title: name }), ArrowDown)}
    </span>
  );
}
