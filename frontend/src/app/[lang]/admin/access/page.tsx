"use client";

// F6b Pro, platform admin (docs/phases/SUBSCRIPTION_DESIGN.md 7), the default tab of /admin/access: the summary
// (active / ending within 14 days / ended in the last 90), a status filter, a name or email search and the list of
// people with Pro (person page link, chain end, days left, plan, source) with "Продлить" (the grant dialog with the
// row's plan) and "Отменить Pro" (reason, danger). The header's "Выдать Pro" opens the same dialog with a person search.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtPassEnd, getProSummary, listPro, type ProRowOut, type ProStatus, type ProSummaryOut } from "@/lib/lms/access";
import { Button, EmptyState, ErrorState, PageHeader, SearchInput, Table, cn, focusRing, type PickedUser, type TableColumn } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { CancelProDialog, GrantProDialog, planLabel, sourceLabel } from "@/components/lms/access/ProAdminUi";

const STATUSES: ProStatus[] = ["active", "expiring", "expired"];

function Summary({ data }: { data: ProSummaryOut | null }) {
  const { t } = useTranslation();
  return (
    <dl className="mb-4 flex flex-wrap gap-2">
      {STATUSES.map((s) => (
        <div key={s} className="flex items-baseline gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
          <dt className="text-sm leading-5 text-slate-600">{t(`access.admin.pro.summary.${s}`)}</dt>
          <dd className="text-base font-semibold tabular-nums leading-6 text-slate-900">{data ? data[s] : "…"}</dd>
        </div>
      ))}
    </dl>
  );
}

function StatusFilter({ value, onChange }: { value: ProStatus; onChange: (s: ProStatus) => void }) {
  const { t } = useTranslation();
  return (
    <div role="group" aria-label={t("access.admin.pro.filter.label")} className="inline-flex rounded-control bg-slate-100 p-1">
      {STATUSES.map((s) => (
        <button key={s} type="button" aria-pressed={value === s} onClick={() => onChange(s)}
          className={cn("min-h-11 rounded-lg px-3 text-sm font-semibold sm:min-h-9", focusRing, "focus-visible:ring-offset-0",
            value === s ? "bg-white text-brand-800 shadow-sm" : "text-slate-700 hover:text-slate-900")}>
          {t(`access.admin.pro.filter.${s}`)}
        </button>
      ))}
    </div>
  );
}

export default function AdminProPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const errorText = useErrorText();
  const [summary, setSummary] = useState<ProSummaryOut | null>(null);
  const [status, setStatus] = useState<ProStatus>("active");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ProRowOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [granting, setGranting] = useState<{ person: PickedUser | null; row: ProRowOut | null } | null>(null);
  const [cancelling, setCancelling] = useState<ProRowOut | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => setQuery(q.trim()), 300);
    return () => window.clearTimeout(id);
  }, [q]);
  const loadSummary = useCallback(async () => {
    try { setSummary(await getProSummary()); } catch { setSummary(null); }
  }, []);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listPro({ status, q: query || undefined, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, [status, query]);
  useEffect(() => { void loadSummary(); }, [loadSummary]);
  useEffect(() => { void load(); }, [load]);
  const refresh = () => { void load(); void loadSummary(); };

  const name = (r: ProRowOut) => r.name || r.email || r.user_id;
  const columns: TableColumn<ProRowOut>[] = [
    { key: "person", header: t("access.admin.pro.columns.person"), primary: true, cell: (r) => (
      <span className="block min-w-0">
        <Link href={`/${lang}/admin/users/${r.user_id}`} className={cn("inline-flex min-h-11 items-center break-words font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>{name(r)}</Link>
        {r.email && r.name && <span className="block break-all text-sm text-slate-600">{r.email}</span>}
      </span>
    ) },
    { key: "ends", header: t("access.admin.pro.columns.ends"), nowrap: true, cell: (r) => fmtPassEnd(r.ends_at, lang, false) },
    { key: "left", header: t("access.admin.pro.columns.left"), nowrap: true, cell: (r) => r.active
      ? <span className="tabular-nums">{t("access.admin.batches.lengthDaysValue", { count: r.days_left })}</span>
      : <span className="text-slate-600">{t("access.admin.pro.ended")}</span> },
    { key: "plan", header: t("access.admin.pro.columns.plan"), cell: (r) => planLabel(r.plan, t) },
    { key: "source", header: t("access.admin.pro.columns.source"), cell: (r) => sourceLabel(r.source, t) },
    { key: "actions", header: "", actions: true, cell: (r) => (
      <span className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => setGranting({ person: { id: r.user_id, display_name: r.name, email: r.email ?? "" }, row: r })}>
          {t("access.admin.pro.renew")}<span className="sr-only">: {name(r)}</span>
        </Button>
        {r.active && (
          <Button variant="link" size="sm" className="text-danger-700" onClick={() => setCancelling(r)}>
            {t("access.admin.pro.cancel")}<span className="sr-only">: {name(r)}</span>
          </Button>
        )}
      </span>
    ) },
  ];

  return (
    <div>
      <PageHeader title={t("access.admin.pages.pro")} description={t("access.admin.description")}
        breadcrumbs={crumbs({ label: t("access.admin.pages.pro") })}
        primaryAction={<Button onClick={() => setGranting({ person: null, row: null })} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{t("access.admin.pro.grant")}</Button>} />
      <Summary data={summary} />
      <Table caption={t("access.admin.pro.caption")} columns={columns} rows={items} rowKey={(r) => r.user_id}
        search={
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <StatusFilter value={status} onChange={setStatus} />
            <SearchInput label={t("access.admin.pro.search")} value={q} onChange={setQ} containerClassName="min-w-0 flex-1 sm:max-w-sm" />
          </div>
        }
        loading={loading && items.length === 0}
        error={error && items.length === 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} /> : undefined}
        empty={<EmptyState variant="plain" title={t(query ? "access.admin.pro.empty.search" : `access.admin.pro.empty.${status}`)} />}
        pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }} />
      <GrantProDialog open={!!granting} person={granting?.person ?? null} renew={!!granting?.row}
        currentEnd={granting?.row?.active ? granting.row.ends_at : null} preset={granting?.row?.plan ?? null}
        onClose={() => setGranting(null)} onGranted={() => { setGranting(null); refresh(); }} />
      <CancelProDialog person={cancelling ? { id: cancelling.user_id, name: name(cancelling) } : null}
        onClose={() => setCancelling(null)} onCancelled={() => { setCancelling(null); refresh(); }} />
    </div>
  );
}
