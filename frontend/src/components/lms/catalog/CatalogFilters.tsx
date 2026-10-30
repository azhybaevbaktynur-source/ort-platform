"use client";

// Phase 9 S4: catalog search and filters (PHASE_9_DESIGN 4.6, 8.1, 8.4): a search box (debounced) plus language,
// organization and enrollment-mode filters. On phones the filters fold under a "Filters" button (the sheet).
import React, { useEffect, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { CatalogFilters as Filters } from "@/lib/lms/catalog";
import type { EnrollmentMode, Lang } from "@/lib/lms/types";
import { Button, FilterBar, Select } from "@/components/ui";

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

  const active = [value.language, value.mode, value.organization_id].filter(Boolean).length;
  const canReset = active > 0 || !!(value.q ?? "");

  return (
    <div className="mb-6 space-y-3">
      <FilterBar
        search={{ id: "catalog-q", value: q, onChange: setQ, label: t("catalog.search.label"),
          placeholder: t("catalog.search.placeholder"), maxLength: CATALOG_Q_MAX }}
        canReset={canReset}
        onReset={() => { setQ(""); onChange({}); }}
      >
        <Button variant="secondary" className="sm:hidden" aria-expanded={open} aria-controls="catalog-filters"
          leftIcon={<SlidersHorizontal className="h-4 w-4" aria-hidden="true" />} onClick={() => setOpen((o) => !o)}>
          {active ? t("catalog.filters.toggleCount", { count: active }) : t("catalog.filters.toggle")}
        </Button>
        <div id="catalog-filters" className={`${open ? "flex" : "hidden"} flex-col gap-3 sm:flex sm:flex-row sm:flex-wrap sm:items-end sm:[&>*]:min-w-[12rem]`}>
          <Select id="catalog-language" label={t("catalog.filters.language")} value={value.language ?? ""}
            onChange={(e) => onChange({ ...value, language: e.target.value as Lang | "" })}
            options={[{ value: "", label: t("catalog.filters.anyLanguage") }, ...LANGS.map((l) => ({ value: l, label: t(`courses.languages.${l}`) }))]} />
          {organizations.length > 0 && (
            <Select id="catalog-org" label={t("catalog.filters.organization")} value={value.organization_id ?? ""}
              onChange={(e) => onChange({ ...value, organization_id: e.target.value })}
              options={[{ value: "", label: t("catalog.filters.anyOrganization") }, ...organizations.map((o) => ({ value: o.id, label: o.name }))]} />
          )}
          <Select id="catalog-mode" label={t("catalog.filters.mode")} value={value.mode ?? ""}
            onChange={(e) => onChange({ ...value, mode: e.target.value as EnrollmentMode | "" })}
            options={[{ value: "", label: t("catalog.filters.anyMode") }, ...CATALOG_MODE_FILTERS.map((m) => ({ value: m, label: t(`catalog.modes.${m}`) }))]} />
        </div>
      </FilterBar>
    </div>
  );
}
