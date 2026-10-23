"use client";

import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LmsApiError } from "@/lib/lms/client";
import {
  R2_FREE_CLASS_A, R2_FREE_CLASS_B, formatBytes, getStorageSummary, runStorageSmoke,
  type StorageSmokeOut, type StorageSummaryOut,
} from "@/lib/lms/storage";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { StorageLevelBanner } from "@/components/lms/admin/StorageLevelBanner";

function Check({ ok, label }: { ok: boolean; label: string }) {
  const { t } = useTranslation();
  return (
    <li className="flex items-center gap-2 text-sm">
      {ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" /> : <XCircle className="h-4 w-4 text-red-600" aria-hidden="true" />}
      <span className="text-slate-800">{label}</span>
      <span className="sr-only">{ok ? t("storage.smoke.passed") : t("storage.smoke.failed")}</span>
    </li>
  );
}

export default function AdminStoragePage() {
  const { lang, t } = useTranslation();
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

  const card = "rounded-2xl border border-slate-200 bg-white p-5";
  const dt = "text-xs font-medium uppercase tracking-wide text-slate-500";
  const dd = "mt-1 text-lg font-semibold text-slate-900";
  const pct = summary ? Math.min(100, Math.round((summary.stored_bytes / summary.hard_bytes) * 100)) : 0;

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold text-slate-900">{t("storage.title")}</h1>
      <p className="mb-6 text-sm text-slate-600">{t("storage.intro")}</p>
      {error ? <ErrorMessage error={error} onRetry={() => load()} className="mb-4" /> : null}
      {!summary && !error ? <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p> : null}
      {summary ? (
        <div className="space-y-6">
          <StorageLevelBanner level={summary.level} />
          {summary.public_base_is_r2dev ? (
            <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">{t("storage.r2devWarning")}</div>
          ) : null}

          <section className={card} aria-labelledby="st-total">
            <h2 id="st-total" className="mb-4 font-semibold text-slate-900">{t("storage.totals.title")}</h2>
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div><dt className={dt}>{t("storage.totals.driver")}</dt><dd className={dd}>{summary.driver}</dd></div>
              <div><dt className={dt}>{t("storage.totals.stored")}</dt><dd className={dd}>{bytes(summary.stored_bytes)}</dd></div>
              <div><dt className={dt}>{t("storage.totals.objects")}</dt><dd className={dd}>{num(summary.object_count)}</dd></div>
              <div><dt className={dt}>{t("storage.totals.level")}</dt><dd className={dd}>{t(`storage.level.${summary.level}`)}</dd></div>
            </dl>
            <div className="mt-4" aria-hidden="true">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div className={`h-2 ${summary.level === "full" ? "bg-red-500" : summary.level === "warn" ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {t("storage.totals.limits", { warn: bytes(summary.warn_bytes), hard: bytes(summary.hard_bytes) })}
            </p>
            <p className="mt-1 text-xs text-slate-500">{t("storage.totals.everWritten")}</p>
          </section>

          <section className={card} aria-labelledby="st-month">
            <h2 id="st-month" className="mb-4 font-semibold text-slate-900">{t("storage.month.title", { month: summary.month.month })}</h2>
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div><dt className={dt}>{t("storage.month.objectsWritten")}</dt><dd className={dd}>{num(summary.month.objects_written)}</dd></div>
              <div><dt className={dt}>{t("storage.month.bytesWritten")}</dt><dd className={dd}>{bytes(summary.month.bytes_written)}</dd></div>
              <div><dt className={dt}>{t("storage.month.classA")}</dt><dd className={dd}>{t("storage.month.ofFree", { n: num(summary.month.class_a), free: num(R2_FREE_CLASS_A) })}</dd></div>
              <div><dt className={dt}>{t("storage.month.classBBackend")}</dt><dd className={dd}>{num(summary.month.class_b_backend)}</dd></div>
              <div><dt className={dt}>{t("storage.month.classBEstimated")}</dt><dd className={dd}>{t("storage.month.ofFree", { n: num(summary.month.class_b_estimated), free: num(R2_FREE_CLASS_B) })}</dd></div>
            </dl>
            <p className="mt-3 text-xs text-slate-500">{t("storage.month.estimateNote")}</p>
          </section>

          <section className={card} aria-labelledby="st-smoke">
            <h2 id="st-smoke" className="mb-1 font-semibold text-slate-900">{t("storage.smoke.title")}</h2>
            <p className="mb-4 text-sm text-slate-600">{t("storage.smoke.hint")}</p>
            <button type="button" onClick={run} disabled={running}
              className="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
              {running ? t("storage.smoke.running") : t("storage.smoke.run")}
            </button>
            {smokeError ? (
              smokeErrorText(smokeError)
                ? <p role="alert" className="mt-4 rounded-xl border border-amber-300 bg-amber-50 px-3.5 py-3 text-sm text-amber-900">{smokeErrorText(smokeError)}</p>
                : <ErrorMessage error={smokeError} className="mt-4" />
            ) : null}
            {smoke ? (
              <div className="mt-4" aria-live="polite">
                <p className={`mb-2 text-sm font-semibold ${smoke.put_ok && smoke.head_ok && smoke.public_read_ok && smoke.deleted ? "text-emerald-700" : "text-red-700"}`}>
                  {smoke.put_ok && smoke.head_ok && smoke.public_read_ok && smoke.deleted ? t("storage.smoke.allOk") : t("storage.smoke.someFailed")}
                </p>
                <ul className="space-y-1">
                  <Check ok={smoke.put_ok} label={t("storage.smoke.put")} />
                  <Check ok={smoke.head_ok} label={t("storage.smoke.head")} />
                  <Check ok={smoke.public_read_ok} label={t("storage.smoke.publicRead")} />
                  <Check ok={smoke.deleted} label={t("storage.smoke.deleted")} />
                </ul>
                <dl className="mt-3 space-y-1 text-xs text-slate-600">
                  {smoke.public_url ? <div><dt className="inline font-medium">{t("storage.smoke.publicUrl")}: </dt><dd className="inline break-all">{smoke.public_url}</dd></div> : null}
                  {smoke.status_code !== null ? <div><dt className="inline font-medium">{t("storage.smoke.statusCode")}: </dt><dd className="inline">{smoke.status_code}</dd></div> : null}
                  <div><dt className="inline font-medium">{t("storage.smoke.latency")}: </dt><dd className="inline">{t("storage.smoke.ms", { n: num(smoke.latency_ms) })}</dd></div>
                  {smoke.error ? <div><dt className="inline font-medium">{t("storage.smoke.error")}: </dt><dd className="inline break-all font-mono">{smoke.error}</dd></div> : null}
                </dl>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
