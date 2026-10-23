"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listSchemes } from "@/lib/lms/grading";
import type { SchemeSummaryOut } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { Pager } from "@/components/lms/Pager";
import { btnPrimary } from "@/components/lms/content/ui";
import { ScaleText, SchemeBadges } from "./SchemeBadges";
import { SchemeError } from "./SchemeError";
import { sortSchemes } from "./params";

/** Scheme library: built-in schemes first, then the teacher's own. Creating is offered to approved teachers only (the server decides). */
export function SchemeLibrary() {
  const { lang, t } = useTranslation();
  const { me } = useLmsMe();
  const [items, setItems] = useState<SchemeSummaryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listSchemes({ cursor: next, include_system: true });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const sorted = sortSchemes(items);
  const system = sorted.filter((s) => s.is_system);
  const mine = sorted.filter((s) => !s.is_system);
  const base = `/${lang}/grading-schemes`;

  const card = (s: SchemeSummaryOut) => (
    <li key={s.id}>
      <Link href={`${base}/${s.id}`}
        className="flex h-full flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm hover:border-brand-300 hover:shadow">
        <span className="font-semibold text-slate-900">{pickLocalized(s.title, lang as Lang) || t("schemes.library.untitled")}</span>
        <SchemeBadges scheme={s} />
        <span className="mt-auto flex flex-wrap gap-x-3 text-xs text-slate-500">
          {s.current_version
            ? <span>{t("schemes.library.version", { n: s.current_version.version_no })}</span>
            : <span>{t("schemes.library.noVersion")}</span>}
          {s.current_version && <ScaleText min={s.current_version.scale_min} max={s.current_version.scale_max} />}
        </span>
      </Link>
    </li>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold text-slate-900">{t("schemes.library.title")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t("schemes.library.intro")}</p>
        </div>
        {me?.can_create_courses && (
          <Link href={`${base}/new`} className={`${btnPrimary} inline-flex items-center gap-1.5`}>
            <Plus className="h-4 w-4" aria-hidden="true" />{t("schemes.library.new")}
          </Link>
        )}
      </div>

      {error ? <SchemeError error={error} onRetry={() => load()} /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}

      {system.length > 0 && (
        <section aria-labelledby="schemes-system">
          <h2 id="schemes-system" className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{t("schemes.library.systemTitle")}</h2>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{system.map(card)}</ul>
        </section>
      )}
      {!loading || items.length > 0 ? (
        <section aria-labelledby="schemes-mine">
          <h2 id="schemes-mine" className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{t("schemes.library.mineTitle")}</h2>
          {mine.length > 0 ? (
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{mine.map(card)}</ul>
          ) : (
            !loading && !error && (
              <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">{t("schemes.library.emptyMine")}</p>
            )
          )}
        </section>
      ) : null}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}
