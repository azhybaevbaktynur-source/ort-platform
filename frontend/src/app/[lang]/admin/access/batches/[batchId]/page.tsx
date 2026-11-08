"use client";

// S3 access, platform admin: one batch's codes. A code shows as its last four characters; "Show" reveals the full code
// (audited, one at a time), "Copy" copies it, "Mark as sold" keeps who bought it (personal data, never in the audit).
// Export downloads the unused codes as CSV (audited); Revoke stops every code nobody has redeemed. F6b: both under «Ещё».
import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Copy, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDateTimeShort } from "@/lib/format";
import {
  exportBatch, getBatch, listCodes, markGiven, revealCode, revokeBatch, type BatchOut, type CodeOut, type CodeStatus,
} from "@/lib/lms/access";
import {
  Badge, Button, Card, DescriptionList, Dialog, EmptyState, ErrorState, IconButton, Input, LoadingState, MenuButton, PageHeader,
  ReasonDialog, Select, Table, toast, type BadgeTone, type TableColumn,
} from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { batchLength } from "@/components/lms/access/AdminAccessUi";

const STATUS_TONE: Record<CodeStatus, BadgeTone> = { unused: "neutral", given: "info", redeemed: "success", revoked: "danger" };
const STATUSES: CodeStatus[] = ["unused", "given", "redeemed", "revoked"];

export default function AdminBatchPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const errorText = useErrorText();
  const [batch, setBatch] = useState<BatchOut | null>(null);
  const [items, setItems] = useState<CodeOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [status, setStatus] = useState<CodeStatus | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [shown, setShown] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [giving, setGiving] = useState<CodeOut | null>(null);
  const [note, setNote] = useState("");
  const [revoking, setRevoking] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const loadBatch = useCallback(async () => {
    try { setBatch(await getBatch(batchId)); } catch (e) { setError(e); }
  }, [batchId]);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listCodes(batchId, { status, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, [batchId, status]);
  useEffect(() => { void loadBatch(); }, [loadBatch]);
  useEffect(() => { void load(); }, [load]);

  const replace = (c: CodeOut) => setItems((prev) => prev.map((x) => (x.id === c.id ? c : x)));
  const toggleShow = async (c: CodeOut) => {
    if (shown[c.id]) { setShown(({ [c.id]: _, ...rest }) => rest); return; }
    setBusyId(c.id);
    try {
      const out = await revealCode(c.id);
      setShown((s) => ({ ...s, [c.id]: out.code }));
    } catch (e) { toast.error(errorText(e)); } finally { setBusyId(null); }
  };
  const copy = async (code: string) => {
    try { await navigator.clipboard.writeText(code); toast.success(t("access.admin.codes.copied")); } catch { /* the code stays visible */ }
  };
  const saveGiven = async () => {
    if (!giving) return;
    setBusyId(giving.id);
    setDialogError(null);
    try {
      replace(await markGiven(giving.id, note.trim()));
      setGiving(null);
      toast.success(t("access.admin.codes.givenToast"));
      void loadBatch();
    } catch (e) { setDialogError(errorText(e)); } finally { setBusyId(null); }
  };
  const runExport = async () => {
    setExporting(true);
    try {
      const { name, blob } = await exportBatch(batchId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(t("access.admin.batches.exported"));
    } catch (e) { toast.error(errorText(e)); } finally { setExporting(false); }
  };
  const runRevoke = async (reason: string) => {
    setBusyId("batch");
    setDialogError(null);
    try {
      setBatch(await revokeBatch(batchId, reason));
      setRevoking(false);
      setShown({});
      toast.success(t("access.admin.batches.revokedToast"));
      void load();
    } catch (e) { setDialogError(errorText(e)); } finally { setBusyId(null); }
  };

  const accessCrumb = { label: t("access.admin.pages.pro"), href: `/${lang}/admin/access` };
  const vouchersCrumb = { label: t("access.admin.pages.vouchers"), href: `/${lang}/admin/access/vouchers` };
  if (error && !batch) {
    return (
      <div>
        <PageHeader title={t("access.admin.codes.title")} breadcrumbs={crumbs(accessCrumb, vouchersCrumb, { label: "…" })} />
        <ErrorState message={errorText(error)} onRetry={() => { void loadBatch(); void load(); }} />
      </div>
    );
  }
  if (!batch) return <LoadingState label={t("lms.common.loading")} />;

  const open = (c: CodeOut) => c.status === "unused" || c.status === "given";
  const columns: TableColumn<CodeOut>[] = [
    { key: "number", header: t("access.admin.codes.columns.number"), cell: (c) => <span className="tabular-nums text-slate-600">{c.position}</span>, nowrap: true },
    { key: "code", header: t("access.admin.codes.columns.code"), primary: true, cell: (c) => (
      <span className="font-mono text-sm tracking-wider text-slate-900">{shown[c.id] ?? `••••-••••-${c.last4}`}</span>
    ), nowrap: true },
    { key: "status", header: t("access.admin.codes.columns.status"), cell: (c) => <Badge tone={STATUS_TONE[c.status]}>{t(`access.admin.codes.status.${c.status}`)}</Badge> },
    { key: "buyer", header: t("access.admin.codes.columns.buyer"), hideInCard: (c) => !c.given_note,
      cell: (c) => <span className="break-words text-sm text-slate-700">{c.given_note || "—"}</span> },
    { key: "used", header: t("access.admin.codes.columns.used"), hideInCard: (c) => !c.redeemed_by_id, cell: (c) => c.redeemed_by_id ? (
      <span className="text-sm text-slate-700">{c.redeemed_by_name || c.redeemed_by_email}<span className="block text-slate-500">{fmtApiDateTimeShort(c.redeemed_at, lang)}</span></span>
    ) : "—" },
    { key: "actions", header: "", actions: true, cell: (c) => open(c) ? (
      <span className="flex flex-wrap items-center gap-1">
        <Button variant="secondary" size="sm" loading={busyId === c.id && !giving} onClick={() => void toggleShow(c)}
          leftIcon={shown[c.id] ? <EyeOff aria-hidden="true" className="h-4 w-4" /> : <Eye aria-hidden="true" className="h-4 w-4" />}>
          {t(shown[c.id] ? "access.admin.codes.hide" : "access.admin.codes.show")}<span className="sr-only"> {c.position}</span>
        </Button>
        {shown[c.id] && (
          <IconButton variant="ghost" aria-label={t("access.admin.codes.copy")} icon={<Copy aria-hidden="true" className="h-4 w-4" />} onClick={() => void copy(shown[c.id])} />
        )}
        <Button variant="link" size="sm" onClick={() => { setGiving(c); setNote(c.given_note ?? ""); setDialogError(null); }}>
          {t(c.status === "given" ? "access.admin.codes.editGiven" : "access.admin.codes.markGiven")}
        </Button>
      </span>
    ) : null },
  ];

  return (
    <div>
      <PageHeader title={batch.label} breadcrumbs={crumbs(accessCrumb, vouchersCrumb, { label: batch.label })}
        badge={batch.revoked_at ? <Badge tone="danger">{t("access.admin.batches.revoked")}</Badge> : undefined}
        secondaryActions={
          <MenuButton label={t("access.admin.more")} variant="secondary" disabled={exporting}
            items={[
              { id: "export", label: t("access.admin.batches.export") },
              ...(!batch.revoked_at ? [{ id: "revoke", label: <span className="text-danger-700">{t("access.admin.batches.revoke")}</span> }] : []),
            ]}
            onSelect={(id) => {
              if (id === "export") void runExport();
              else { setDialogError(null); setRevoking(true); }
            }} />
        } />
      <Card className="mb-6">
        <DescriptionList twoColumns items={[
          { key: "length", term: t("access.admin.batches.columns.length"), description: batchLength(batch, t, lang) },
          { key: "codes", term: t("access.admin.batches.columns.codes"), description: t("access.admin.batches.counts", { unused: batch.unused, given: batch.given, redeemed: batch.redeemed }) },
          { key: "created", term: t("access.admin.batches.columns.created"), description: `${fmtApiDateTimeShort(batch.created_at, lang)}${batch.created_by ? ` · ${batch.created_by}` : ""}` },
          ...(batch.note ? [{ key: "note", term: t("access.admin.batches.note"), description: <span className="whitespace-pre-line break-words">{batch.note}</span> }] : []),
        ]} />
      </Card>
      <p className="mb-3 text-sm text-slate-600">{t("access.admin.codes.showHint")}</p>
      <Table caption={t("access.admin.codes.title")} columns={columns} rows={items} rowKey={(c) => c.id}
        search={<Select id="code-status" label={t("access.admin.codes.filter")} value={status} containerClassName="max-w-xs"
          onChange={(e) => setStatus(e.target.value as CodeStatus | "")}
          options={[{ value: "", label: t("access.admin.codes.all") }, ...STATUSES.map((s) => ({ value: s, label: t(`access.admin.codes.status.${s}`) }))]} />}
        loading={loading && items.length === 0}
        error={error && items.length === 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} /> : undefined}
        empty={<EmptyState variant="plain" title={t("access.admin.codes.empty")} />}
        pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }} />

      <Dialog open={!!giving} onClose={() => setGiving(null)} busy={busyId === giving?.id} title={t("access.admin.codes.givenTitle")}
        description={giving ? `${giving.position} · ••••-••••-${giving.last4}` : undefined}
        footer={<>
          <Button variant="secondary" onClick={() => setGiving(null)} disabled={busyId === giving?.id}>{t("common.cancel")}</Button>
          <Button onClick={() => void saveGiven()} loading={busyId === giving?.id}>{t("access.admin.codes.givenSave")}</Button>
        </>}>
        <Input id="given-note" label={t("access.admin.codes.givenNote")} hint={t("access.admin.codes.givenNoteHint")} maxLength={200}
          value={note} onChange={(e) => setNote(e.target.value)} optional error={dialogError ?? undefined} />
      </Dialog>
      <ReasonDialog open={revoking} title={t("access.admin.batches.revokeTitle")} object={batch.label}
        effect={t("access.admin.batches.revokeBody")} confirmLabel={t("access.admin.batches.revoke")} tone="danger"
        busy={busyId === "batch"} error={dialogError ?? undefined}
        onConfirm={(r) => void runRevoke(r)} onCancel={() => setRevoking(false)} />
    </div>
  );
}
