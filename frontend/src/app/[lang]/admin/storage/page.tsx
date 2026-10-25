"use client";

import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, TriangleAlert, XCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LmsApiError } from "@/lib/lms/client";
import {
  R2_FREE_CLASS_A, R2_FREE_CLASS_B, formatBytes, getStorageSummary, runStorageSmoke,
  type StorageSmokeOut, type StorageSummaryOut,
} from "@/lib/lms/storage";
import { StorageLevelBanner } from "@/components/lms/admin/StorageLevelBanner";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { LoadError, OrgError } from "@/components/lms/org/OrgUi";
import { Button, Card, LoadingState, PageHeader } from "@/components/ui";

function Check({ ok, label }: { ok: boolean; label: string }) {
  const { t } = useTranslation();
  return (
    <li className="flex items-center gap-2 text-sm">
      {ok ? <CheckCircle2 className="h-4 w-4 shrink-0 text-success-700" aria-hidden="true" /> : <XCircle className="h-4 w-4 shrink-0 text-danger-700" aria-hidden="true" />}
      <span className="text-slate-800">{label}</span>
      <span className="sr-only">{ok ? t("storage.smoke.passed") : t("storage.smoke.failed")}</span>
    </li>
  );
}

export default function AdminStoragePage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [summary, setSummary] = useState<StorageSummaryOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [running, setRunning] = useState(false);
  const [smoke, setSmoke] = useState<StorageSmokeOut | null>(null);
  const [smokeError, setSmokeError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSummary(await getStorageSummary());
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const units: [string, string, string, string] = [t("storage.units.b"), t("storage.units.kb"), t("storage.units.mb"), t("storage.units.gb")];
  const bytes = (n: number) => formatBytes(n, lang, units);
  const num = (n: number) => new Intl.NumberFormat(lang).format(n);

  const run = async () => {
    setRunning(true);
    setSmoke(null);
    setSmokeError(null);
    try {
      setSmoke(await runStorageSmoke());
      void load();
    } catch (e) {
      setSmokeError(e);
    } finally {
      setRunning(false);
    }
  };

  const smokeErrorText = (e: unknown): string | null => {
    if (!(e instanceof LmsApiError)) return null;
    if (e.code === "storage_driver_not_r2") return t("storage.smoke.notR2");
    if (e.code === "rate_limited") return t("storage.smoke.rateLimited");
    return null;
  };

  const dt = "text-sm font-medium leading-5 text-slate-600";
  const dd = "mt-1 text-lg font-semibold text-slate-900";
  const pct = summary ? Math.min(100, Math.round((summary.stored_bytes / summary.hard_bytes) * 100)) : 0;

  return (
    <div>
      <PageHeader title={t("storage.title")} description={t("storage.intro")} breadcrumbs={crumbs({ label: t("storage.nav") })} />
      {error && !summary ? <LoadError error={error} onRetry={() => void load()} /> : null}
      {error && summary ? <OrgError error={error} onRetry={() => void load()} className="mb-4" /> : null}
      {!summary && !error ? <LoadingState label={t("lms.common.loading")} /> : null}
      {summary ? (
        <div className="space-y-6">
          <StorageLevelBanner level={summary.level} />
          {summary.public_base_is_r2dev ? (
            <div className="flex gap-3 rounded-2xl border border-warning-200 bg-warning-50 p-4 text-sm leading-6 text-warning-900">
              <TriangleAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
              <p>{t("storage.r2devWarning")}</p>
            </div>
          ) : null}

          <Card title={t("storage.totals.title")}>
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div><dt className={dt}>{t("storage.totals.driver")}</dt><dd className={dd}>{summary.driver}</dd></div>
              <div><dt className={dt}>{t("storage.totals.stored")}</dt><dd className={dd}>{bytes(summary.stored_bytes)}</dd></div>
              <div><dt className={dt}>{t("storage.totals.objects")}</dt><dd className={dd}>{num(summary.object_count)}</dd></div>
              <div><dt className={dt}>{t("storage.totals.level")}</dt><dd className={dd}>{t(`storage.level.${summary.level}`)}</dd></div>
            </dl>
            <div className="mt-4" aria-hidden="true">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div className={`h-2 ${summary.level === "full" ? "bg-danger-600" : summary.level === "warn" ? "bg-warning-500" : "bg-success-600"}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
            <p className="mt-2 text-sm text-slate-600">
              {t("storage.totals.limits", { warn: bytes(summary.warn_bytes), hard: bytes(summary.hard_bytes) })}
            </p>
            <p className="mt-1 text-sm text-slate-600">{t("storage.totals.everWritten")}</p>
          </Card>

          <Card title={t("storage.month.title", { month: summary.month.month })}>
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div><dt className={dt}>{t("storage.month.objectsWritten")}</dt><dd className={dd}>{num(summary.month.objects_written)}</dd></div>
              <div><dt className={dt}>{t("storage.month.bytesWritten")}</dt><dd className={dd}>{bytes(summary.month.bytes_written)}</dd></div>
              <div><dt className={dt}>{t("storage.month.classA")}</dt><dd className={dd}>{t("storage.month.ofFree", { n: num(summary.month.class_a), free: num(R2_FREE_CLASS_A) })}</dd></div>
              <div><dt className={dt}>{t("storage.month.classBBackend")}</dt><dd className={dd}>{num(summary.month.class_b_backend)}</dd></div>
              <div><dt className={dt}>{t("storage.month.classBEstimated")}</dt><dd className={dd}>{t("storage.month.ofFree", { n: num(summary.month.class_b_estimated), free: num(R2_FREE_CLASS_B) })}</dd></div>
            </dl>
            <p className="mt-3 text-sm text-slate-600">{t("storage.month.estimateNote")}</p>
          </Card>

          <Card title={t("storage.smoke.title")} description={t("storage.smoke.hint")}>
            <Button variant="secondary" onClick={() => void run()} loading={running}>
              {running ? t("storage.smoke.running") : t("storage.smoke.run")}
            </Button>
            {smokeError ? (
              smokeErrorText(smokeError)
                ? <p role="alert" className="mt-4 rounded-xl border border-warning-200 bg-warning-50 px-3.5 py-3 text-sm text-warning-900">{smokeErrorText(smokeError)}</p>
                : <OrgError error={smokeError} className="mt-4" />
            ) : null}
            {smoke ? (
              <div className="mt-4" aria-live="polite">
                <p className={`mb-2 text-sm font-semibold ${smoke.put_ok && smoke.head_ok && smoke.public_read_ok && smoke.deleted ? "text-success-700" : "text-danger-700"}`}>
                  {smoke.put_ok && smoke.head_ok && smoke.public_read_ok && smoke.deleted ? t("storage.smoke.allOk") : t("storage.smoke.someFailed")}
                </p>
                <ul className="space-y-1">
                  <Check ok={smoke.put_ok} label={t("storage.smoke.put")} />
                  <Check ok={smoke.head_ok} label={t("storage.smoke.head")} />
                  <Check ok={smoke.public_read_ok} label={t("storage.smoke.publicRead")} />
                  <Check ok={smoke.deleted} label={t("storage.smoke.deleted")} />
                </ul>
                <dl className="mt-3 space-y-1 text-sm text-slate-700">
                  {smoke.public_url ? <div><dt className="inline font-medium">{t("storage.smoke.publicUrl")}: </dt><dd className="inline break-all">{smoke.public_url}</dd></div> : null}
                  {smoke.status_code !== null ? <div><dt className="inline font-medium">{t("storage.smoke.statusCode")}: </dt><dd className="inline">{smoke.status_code}</dd></div> : null}
                  <div><dt className="inline font-medium">{t("storage.smoke.latency")}: </dt><dd className="inline">{t("storage.smoke.ms", { n: num(smoke.latency_ms) })}</dd></div>
                  {smoke.error ? <div><dt className="inline font-medium">{t("storage.smoke.error")}: </dt><dd className="inline break-all font-mono">{smoke.error}</dd></div> : null}
                </dl>
              </div>
            ) : null}
          </Card>
        </div>
      ) : null}
    </div>
  );
}
