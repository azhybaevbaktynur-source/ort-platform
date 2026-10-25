"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listUsers } from "@/lib/lms/admin";
import { isSystemAccount } from "@/lib/lms/organizations";

export interface PickedUser {
  id: string;
  display_name: string | null;
  email: string;
}

export type UserSearch = (q: string) => Promise<PickedUser[]>;

/** Search over the platform users list (admin only): enabled accounts, no system accounts. */
export function platformUserSearch(): UserSearch {
  return async (q) => {
    const page = await listUsers({ q, limit: 10 });
    return page.items
      .filter((u) => !u.disabled_at && !isSystemAccount(u))
      .map((u) => ({ id: u.id, display_name: u.display_name, email: u.email }));
  };
}

const MIN_CHARS = 2;

/**
 * Async user combobox (admin B1): type a name or email, pick a person from the list.
 * Keyboard: arrows move, Enter picks, Escape closes. The chosen person is shown with a "Change" button.
 */
export function UserPicker({
  id, label, hint, value, onChange, search, excludeIds = [], disabled = false,
}: {
  id?: string;
  label: string;
  hint?: string;
  value: PickedUser | null;
  onChange: (u: PickedUser | null) => void;
  search: UserSearch;
  excludeIds?: string[];
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const autoId = useId();
  const inputId = id ?? `${autoId}-input`;
  const listId = `${autoId}-list`;
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
        <p className="mb-1 block text-sm font-medium text-slate-700">{label}</p>
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-300 bg-slate-50 px-3 py-2">
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium text-slate-900">{value.display_name || value.email}</span>
            <span className="block truncate text-xs text-slate-500">{value.email}</span>
          </span>
          <button type="button" disabled={disabled} onClick={() => onChange(null)}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-lg px-3 text-sm font-medium text-brand-700 hover:bg-white disabled:opacity-50">
            <X className="h-4 w-4" aria-hidden="true" />{t("organizations.picker.change")}
          </button>
        </div>
      </div>
    );
  }

  const term = q.trim();
  const showList = open && term.length >= MIN_CHARS;
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(results.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { if (showList && active >= 0 && results[active]) { e.preventDefault(); pick(results[active]); } }
    else if (e.key === "Escape") { if (open) { e.stopPropagation(); setOpen(false); } }
  };

  return (
    <div className="relative">
      <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-slate-700">{label}</label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" aria-hidden="true" />
        <input
          id={inputId} type="text" role="combobox" autoComplete="off" disabled={disabled}
          aria-expanded={showList} aria-controls={listId} aria-autocomplete="list"
          aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
          value={q} placeholder={t("organizations.picker.placeholder")}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} onKeyDown={onKey}
          className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:bg-slate-50"
        />
      </div>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {showList && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          <p role="status" className="sr-only">
            {loading ? t("organizations.picker.searching") : t("organizations.picker.count", { n: results.length })}
          </p>
          {loading && <p className="px-3 py-3 text-sm text-slate-500">{t("organizations.picker.searching")}</p>}
          {!loading && failed && <p className="px-3 py-3 text-sm text-red-700">{t("organizations.picker.failed")}</p>}
          {!loading && !failed && results.length === 0 && <p className="px-3 py-3 text-sm text-slate-500">{t("organizations.picker.empty")}</p>}
          <ul id={listId} role="listbox" aria-label={label} className="max-h-64 overflow-y-auto">
            {results.map((u, i) => (
              <li key={u.id} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); pick(u); }}
                className={`cursor-pointer px-3 py-2.5 ${i === active ? "bg-brand-50" : "hover:bg-slate-50"}`}>
                <span className="block truncate text-sm font-medium text-slate-900">{u.display_name || u.email}</span>
                <span className="block truncate text-xs text-slate-500">{u.email}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {open && term.length > 0 && term.length < MIN_CHARS && (
        <p className="mt-1 text-xs text-slate-500">{t("organizations.picker.minChars", { n: MIN_CHARS })}</p>
      )}
    </div>
  );
}
