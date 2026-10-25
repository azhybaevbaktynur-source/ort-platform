"use client";

import React, { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { CatalogSection } from "@/components/lms/CatalogSection";
import { cn, focusRing } from "@/components/ui";

/**
 * Phase 6b S5c (UX T13): for people who create courses the catalog comes after "My courses", collapsed behind a
 * visible labelled button. It opens by itself when the page is opened with `#catalog`.
 */
export function CollapsedCatalog({ onJoined }: { onJoined?: (courseId: string) => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    try { if (window.location.hash === "#catalog") setOpen(true); } catch { /* no window */ }
  }, []);
  return (
    <div className="mt-10 border-t border-slate-200 pt-6">
      <button type="button" aria-expanded={open} aria-controls="catalog-collapsed" onClick={() => setOpen((o) => !o)}
        className={cn("inline-flex min-h-11 items-center gap-2 rounded-xl px-1 text-base font-semibold text-slate-900 hover:text-brand-700", focusRing)}>
        <ChevronDown aria-hidden="true" className={cn("h-5 w-5 transition-transform", open && "rotate-180")} />
        {t("teaching.showCatalog")}
      </button>
      <div id="catalog-collapsed" hidden={!open} className="mt-4">
        {open && <CatalogSection onJoined={onJoined} />}
      </div>
    </div>
  );
}
