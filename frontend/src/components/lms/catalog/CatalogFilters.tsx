"use client";

// Phase 9 S4: catalog search (debounced). F7c: language chips next to it; the organization and enrollment-mode filters
// sit under a collapsed "More filters" on desktop and are not offered on phones.
import React, { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { CatalogFilters as Filters } from "@/lib/lms/catalog";
import type { EnrollmentMode, Lang } from "@/lib/lms/types";
import { Button, FilterBar, Select, cn, focusRing } from "@/components/ui";

const LANGS: Lang[] = ["ky", "ru", "en"];
/** Modes a student can act on; `closed` courses are still listed but not offered as a filter. */
export const CATALOG_MODE_FILTERS: EnrollmentMode[] = ["open", "form_review", "form_auto", "invite_code"];
const SEARCH_DEBOUNCE_MS = 300;
export const CATALOG_Q_MAX = 80;

export function CatalogFilters({ value, onChange, organizations }: {
  value: Filters;
  onChange: (f: Filters) => void;
  /** Organizations seen in the catalog so far (`id`, `name`). */
  organizations: { id: string; name: string }[];
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState(value.q ?? "");
  const [open, setOpen] = useState(false);

  // Debounce typing; the parent reloads the first page on every committed change.
  useEffect(() => {
    if ((value.q ?? "") === q.trim()) return;
    const id = setTimeout(() => onChange({ ...value, q: q.trim() }), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [q, value, onChange]);

  const secondary = [value.mode, value.organization_id].filter(Boolean).length;
  const canReset = !!(value.language || secondary || value.q);
  const chip = (lang: Lang | "", label: string) => {
    const on = (value.language ?? "") === lang;
    return (
      <button key={lang || "any"} type="button" aria-pressed={on} onClick={() => onChange({ ...value, language: lang })}
        className={cn("min-h-11 rounded-full border px-4 text-sm font-medium transition-colors", focusRing,
          on ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50")}>
        {label}
      </button>
    );
  };

  return (
    <div className="mb-6 space-y-3">
      <FilterBar
        search={{ id: "catalog-q", value: q, onChange: setQ, label: t("catalog.search.label"),
          placeholder: t("catalog.search.placeholder"), maxLength: CATALOG_Q_MAX }}
        canReset={canReset}
        onReset={() => { setQ(""); onChange({}); }}
      >
        <div role="group" aria-label={t("catalog.filters.language")} className="flex flex-wrap gap-2 !min-w-0">
          {chip("", t("catalog.filters.anyLanguage"))}
          {LANGS.map((l) => chip(l, t(`courses.languages.${l}`)))}
        </div>
      </FilterBar>
      <div className="hidden sm:block">
        <Button variant="link" aria-expanded={open} aria-controls="catalog-filters" onClick={() => setOpen((o) => !o)}
          rightIcon={<ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden="true" />}>
          {secondary ? t("catalog.filters.moreCount", { count: secondary }) : t("catalog.filters.more")}
        </Button>
        <div id="catalog-filters" className={cn("mt-2 flex-wrap items-end gap-3 [&>*]:min-w-[12rem]", open ? "flex" : "hidden")}>
          {organizations.length > 0 && (
            <Select id="catalog-org" label={t("catalog.filters.organization")} value={value.organization_id ?? ""}
              onChange={(e) => onChange({ ...value, organization_id: e.target.value })}
              options={[{ value: "", label: t("catalog.filters.anyOrganization") }, ...organizations.map((o) => ({ value: o.id, label: o.name }))]} />
          )}
          <Select id="catalog-mode" label={t("catalog.filters.mode")} value={value.mode ?? ""}
            onChange={(e) => onChange({ ...value, mode: e.target.value as EnrollmentMode | "" })}
            options={[{ value: "", label: t("catalog.filters.anyMode") }, ...CATALOG_MODE_FILTERS.map((m) => ({ value: m, label: t(`catalog.modes.${m}`) }))]} />
        </div>
      </div>
    </div>
  );
}
