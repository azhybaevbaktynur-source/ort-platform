"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { FieldHint, FieldLabel } from "./Field";
import { cn, fieldBase, focusRing } from "./utils";

/*
 * Design-system copy of `components/lms/UserPicker.tsx` (Phase 6a), same props and types so
 * callers can switch their import later. The data source stays with the caller (`search`);
 * `platformUserSearch()` remains in the lms file because it calls the admin API.
 */

export interface PickedUser {
  id: string;
  display_name: string | null;
  email: string;
}

export type UserSearch = (q: string) => Promise<PickedUser[]>;

const MIN_CHARS = 2;

export interface UserPickerProps {
  id?: string;
  label: string;
  hint?: string;
  value: PickedUser | null;
  onChange: (u: PickedUser | null) => void;
  search: UserSearch;
  excludeIds?: string[];
  disabled?: boolean;
}

/**
 * Async user combobox: type a name or email (2+ characters), pick a person from the list.
 * Keyboard: arrows move, Enter picks, Escape closes. The chosen person is shown with a "Change" button.
 */
export function UserPicker({ id, label, hint, value, onChange, search, excludeIds = [], disabled = false }: UserPickerProps) {
  const { t } = useTranslation();
  const autoId = useId().replace(/:/g, "");
  const inputId = id ?? `${autoId}-input`;
  const listId = `${autoId}-list`;
  const hintId = hint ? `${autoId}-hint` : undefined;
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PickedUser[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(-1);
  const searchRef = useRef(search);
  searchRef.current = search;
  const excludeKey = excludeIds.join(",");

  useEffect(() => {
    const term = q.trim();
    if (term.length < MIN_CHARS) { setResults([]); setLoading(false); return; }
    let alive = true;
    setLoading(true);
    const h = setTimeout(() => {
      searchRef.current(term)
        .then((r) => {
          if (!alive) return;
          const ex = new Set(excludeKey ? excludeKey.split(",") : []);
          setResults(r.filter((u) => !ex.has(u.id)));
          setFailed(false);
          setActive(-1);
        })
        .catch(() => { if (alive) { setResults([]); setFailed(true); } })
        .finally(() => { if (alive) setLoading(false); });
    }, 300);
    return () => { alive = false; clearTimeout(h); };
  }, [q, excludeKey]);

  const pick = (u: PickedUser) => {
    onChange(u);
    setQ("");
    setResults([]);
    setOpen(false);
  };

  if (value) {
    return (
      <div>
        <FieldLabel>{label}</FieldLabel>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-300 bg-slate-50 py-1 pl-3 pr-1">
          <span className="min-w-0 py-1">
            <span className="block break-words text-sm font-medium leading-5 text-slate-900">{value.display_name || value.email}</span>
            <span className="block break-all text-sm leading-5 text-slate-600">{value.email}</span>
          </span>
          <button type="button" disabled={disabled} onClick={() => onChange(null)}
            className={cn("inline-flex min-h-11 items-center gap-1 rounded-lg px-3 text-sm font-semibold text-brand-700 hover:bg-white disabled:opacity-60", focusRing)}>
            <X className="h-4 w-4" aria-hidden="true" />{t("ui.picker.change")}
          </button>
        </div>
        <FieldHint id={hintId}>{hint}</FieldHint>
      </div>
    );
  }

  const term = q.trim();
  const showList = open && term.length >= MIN_CHARS;
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(results.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { if (showList && active >= 0 && results[active]) { e.preventDefault(); pick(results[active]); } }
    else if (e.key === "Escape") { if (open) { e.stopPropagation(); e.preventDefault(); setOpen(false); } }
  };

  return (
    <div className="relative">
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      <div className="relative mt-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
        <input
          id={inputId} type="text" role="combobox" autoComplete="off" disabled={disabled}
          aria-expanded={showList} aria-controls={listId} aria-autocomplete="list" aria-describedby={hintId}
          aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
          value={q} placeholder={t("ui.picker.placeholder")}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} onKeyDown={onKey}
          className={cn(fieldBase, "min-h-11 border-slate-300 py-2 pl-10")}
        />
      </div>
      <FieldHint id={hintId}>{hint}</FieldHint>
      {showList && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          <p role="status" className="sr-only">
            {loading ? t("ui.picker.searching") : t("ui.picker.count", { n: results.length })}
          </p>
          {loading && <p className="px-3 py-3 text-sm text-slate-600">{t("ui.picker.searching")}</p>}
          {!loading && failed && <p className="px-3 py-3 text-sm text-danger-700">{t("ui.picker.failed")}</p>}
          {!loading && !failed && results.length === 0 && <p className="px-3 py-3 text-sm text-slate-600">{t("ui.picker.empty")}</p>}
          <ul id={listId} role="listbox" aria-label={label} className="max-h-64 overflow-y-auto">
            {results.map((u, i) => (
              <li key={u.id} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); pick(u); }}
                className={cn("min-h-11 cursor-pointer px-3 py-2", i === active ? "bg-brand-50" : "hover:bg-slate-50")}>
                <span className="block truncate text-sm font-medium leading-5 text-slate-900">{u.display_name || u.email}</span>
                <span className="block truncate text-sm leading-5 text-slate-600">{u.email}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {open && term.length > 0 && term.length < MIN_CHARS && (
        <p className="mt-1 text-sm text-slate-600">{t("ui.picker.minChars", { n: MIN_CHARS })}</p>
      )}
    </div>
  );
}
