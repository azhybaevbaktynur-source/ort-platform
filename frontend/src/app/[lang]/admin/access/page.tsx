"use client";

// S3 access, platform admin: code batches (create, list; each batch's page has its codes, export and revoke) and the
// attention block (recently published exams with their tier, the reveal alert).
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDateTimeShort } from "@/lib/format";
import { createBatch, listBatches, type BatchOut } from "@/lib/lms/access";
import { Badge, Button, Dialog, EmptyState, ErrorState, Input, PageHeader, Table, Textarea, cn, focusRing, toast, type TableColumn } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { AccessTabs, RecentExamsCard, RevealAlert, batchLength, useAccessOverview } from "@/components/lms/access/AdminAccessUi";

function CreateBatchDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (b: BatchOut) => void }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const [label, setLabel] = useState("");
  const [count, setCount] = useState("50");
  const [mode, setMode] = useState<"days" | "date">("days");
  const [days, setDays] = useState("30");
  const [endsOn, setEndsOn] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) { setLabel(""); setCount("50"); setMode("days"); setDays("30"); setEndsOn(""); setNote(""); setError(null); }
  }, [open]);
  const n = Number(count);
  const d = Number(days);
  const valid = label.trim() !== "" && Number.isInteger(n) && n >= 1 && n <= 500
    && (mode === "days" ? Number.isInteger(d) && d >= 1 && d <= 400 : endsOn !== "");

  const submit = async () => {
    if (!valid) { setError(t("lms.errors.batch_length_required")); return; }
    setBusy(true);
    setError(null);
    try {
      const b = await createBatch({ label: label.trim(), count: n, note: note.trim() || undefined,
        ...(mode === "days" ? { duration_days: d } : { ends_on: endsOn }) });
      toast.success(t("access.admin.batches.created", { count: b.count }));
      onCreated(b);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const radio = "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 text-sm font-medium sm:min-h-9";
  return (
    <Dialog open={open} onClose={onClose} busy={busy} title={t("access.admin.batches.createTitle")}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={busy}>{t("common.cancel")}</Button>
        <Button onClick={() => void submit()} loading={busy}>{t("access.admin.batches.submit")}</Button>
      </>}>
      <div className="space-y-4">
        <Input id="batch-label" label={t("access.admin.batches.label")} hint={t("access.admin.batches.labelHint")} maxLength={120}
          value={label} onChange={(e) => setLabel(e.target.value)} />
        <Input id="batch-count" label={t("access.admin.batches.count")} hint={t("access.admin.batches.countHint")} inputMode="numeric"
          value={count} onChange={(e) => setCount(e.target.value.replace(/[^0-9]/g, "").slice(0, 3))} containerClassName="max-w-xs" />
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-slate-800">{t("access.admin.batches.length")}</legend>
          <div className="flex flex-wrap gap-2">
            {(["days", "date"] as const).map((m) => (
              <label key={m} className={cn(radio, mode === m ? "border-brand-600 bg-brand-50 text-brand-800" : "border-slate-300 bg-white text-slate-700")}>
                <input type="radio" name="batch-mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="h-4 w-4" />
                {t(m === "days" ? "access.admin.batches.lengthDays" : "access.admin.batches.lengthDate")}
              </label>
            ))}
          </div>
        </fieldset>
        {mode === "days" ? (
          <Input id="batch-days" label={t("access.admin.batches.days")} hint={t("access.admin.batches.daysHint")} inputMode="numeric"
            value={days} onChange={(e) => setDays(e.target.value.replace(/[^0-9]/g, "").slice(0, 3))} containerClassName="max-w-xs" />
        ) : (
          <Input id="batch-ends" type="date" label={t("access.admin.batches.endsOn")} hint={t("access.admin.batches.endsOnHint")}
            value={endsOn} onChange={(e) => setEndsOn(e.target.value)} containerClassName="max-w-xs" />
        )}
        <Textarea id="batch-note" label={t("access.admin.batches.note")} hint={t("access.admin.batches.noteHint")} rows={2} maxLength={500}
          value={note} onChange={(e) => setNote(e.target.value)} optional />
        {error && <p role="alert" className="text-sm font-medium text-danger-700">{error}</p>}
      </div>
    </Dialog>
  );
}

export default function AdminAccessPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const errorText = useErrorText();
  const { data: overview } = useAccessOverview();
  const [items, setItems] = useState<BatchOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listBatches(next);
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const base = `/${lang}/admin/access`;
  const columns: TableColumn<BatchOut>[] = [
    { key: "name", header: t("access.admin.batches.columns.name"), primary: true, cell: (b) => (
      <span className="flex flex-wrap items-center gap-2">
        <Link href={`${base}/batches/${b.id}`} className={cn("inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>{b.label}</Link>
        {b.revoked_at && <Badge tone="danger">{t("access.admin.batches.revoked")}</Badge>}
      </span>
    ) },
    { key: "length", header: t("access.admin.batches.columns.length"), cell: (b) => batchLength(b, t, lang), nowrap: true },
    { key: "codes", header: t("access.admin.batches.columns.codes"), cell: (b) => (
      <span className="text-sm text-slate-700">{t("access.admin.batches.counts", { unused: b.unused, given: b.given, redeemed: b.redeemed })}</span>
    ) },
    { key: "created", header: t("access.admin.batches.columns.created"), cell: (b) => (
      <span className="text-sm text-slate-600">{fmtApiDateTimeShort(b.created_at, lang)}{b.created_by ? ` · ${b.created_by}` : ""}</span>
    ) },
  ];

  return (
    <div>
      <PageHeader title={t("access.admin.title")} description={t("access.admin.description")}
        breadcrumbs={crumbs({ label: t("access.admin.nav") })}
        primaryAction={<Button onClick={() => setCreating(true)} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{t("access.admin.batches.create")}</Button>} />
      <AccessTabs />
      {overview?.reveal_alert && <RevealAlert count={overview.reveals_last_hour} className="mb-6" />}
      <Table caption={t("access.admin.tabs.batches")} columns={columns} rows={items} rowKey={(b) => b.id}
        loading={loading && items.length === 0}
        error={error && items.length === 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} /> : undefined}
        empty={<EmptyState variant="plain" title={t("access.admin.batches.empty")} />}
        pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }} />
      <RecentExamsCard data={overview} className="mt-8" compact />
      <CreateBatchDialog open={creating} onClose={() => setCreating(false)}
        onCreated={(b) => { setCreating(false); setItems((prev) => [b, ...prev]); }} />
    </div>
  );
}
