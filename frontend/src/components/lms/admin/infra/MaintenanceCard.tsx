"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Eraser, ScanSearch, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LmsApiError } from "@/lib/lms/client";
import { getMaintenance, runMaintenance, type MaintenanceRun, type MaintenanceState } from "@/lib/lms/maintenance";
import { OrgError } from "@/components/lms/org/OrgUi";
import { Badge, Button, ConfirmDialog, cn } from "@/components/ui";
import { ago } from "./ServiceCard";

/** Daily database cleanup (DB_STORAGE_REVIEW 5, slice D2): the last run with its per-task counts, a dry run ("check")
 *  and an applied run behind a confirmation. Students' results, grades and the audit log are never touched. */
export function MaintenanceCard() {
  const { lang, t } = useTranslation();
  const [state, setState] = useState<MaintenanceState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"check" | "apply" | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [limited, setLimited] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setState(await getMaintenance());
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const run = async (apply: boolean) => {
    setBusy(apply ? "apply" : "check");
    setLimited(false);
    setError(null);
    try {
      const out: MaintenanceRun = await runMaintenance(apply);
      setState((s) => ({ tasks: s?.tasks ?? Object.keys(out.counts), last_run: out }));
      setConfirm(false);
    } catch (e) {
      if (e instanceof LmsApiError && (e.status === 429 || e.code === "rate_limited")) {
        setLimited(true);
        setConfirm(false);
      } else setError(e);
    } finally {
      setBusy(null);
    }
  };

  const num = (n: number) => new Intl.NumberFormat(lang).format(n);
  const last = state?.last_run ?? null;
  const tasks = state?.tasks ?? [];
  const total = last ? Object.entries(last.counts).reduce((sum, [k, c]) => sum + (k === "measure_storage" ? 0 : last.dry_run ? c.examined : c.changed), 0) : 0;
  return (
    <section data-testid="infra-maintenance" aria-labelledby="infra-maintenance-title"
      className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-1 basis-72 items-start gap-2.5">
          <span aria-hidden="true" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700 [&>svg]:h-4 [&>svg]:w-4">
            <Eraser />
          </span>
          <div className="min-w-0">
            <h2 id="infra-maintenance-title" className="text-base font-semibold leading-6 text-slate-900">{t("infra.maintenance.title")}</h2>
            <p className="mt-0.5 text-sm leading-5 text-slate-600">{t("infra.maintenance.subtitle")}</p>
          </div>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <Button variant="secondary" className="w-full sm:w-auto" leftIcon={<ScanSearch aria-hidden="true" className="h-4 w-4" />}
            loading={busy === "check"} disabled={busy !== null || !state} onClick={() => void run(false)} data-testid="maintenance-check">
            {t("infra.maintenance.check")}
          </Button>
          <Button variant="dangerOutline" className="w-full sm:w-auto" leftIcon={<Eraser aria-hidden="true" className="h-4 w-4" />}
            disabled={busy !== null || !state} onClick={() => setConfirm(true)} data-testid="maintenance-apply">
            {t("infra.maintenance.apply")}
          </Button>
        </div>
      </div>

      {limited ? <p role="alert" data-testid="maintenance-rate-limited" className="mt-3 rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm text-warning-900">{t("infra.maintenance.rateLimited")}</p> : null}
      {error && !confirm ? <OrgError error={error} onRetry={state ? undefined : () => void load()} className="mt-3" /> : null}

      {state ? (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <p data-testid="maintenance-last-run" className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
            {last ? (
              <>
                <span>{t("infra.maintenance.lastRun", { when: ago(last.ran_at, lang, t("infra.never")) })}</span>
                <Badge tone={last.dry_run ? "neutral" : "info"}>{t(last.dry_run ? "infra.maintenance.mode.dryRun" : "infra.maintenance.mode.applied")}</Badge>
                <span className="text-slate-600">· {t(`infra.maintenance.trigger.${["token", "admin", "fallback"].includes(last.trigger) ? last.trigger : "token"}`)}</span>
                <span className="text-slate-600">· {t(last.dry_run ? "infra.maintenance.totalFound" : "infra.maintenance.totalDone", { n: num(total) })}</span>
              </>
            ) : <span>{t("infra.maintenance.neverRun")}</span>}
          </p>
          {last && last.errors.length > 0 ? (
            <p role="alert" data-testid="maintenance-errors" className="mt-2 flex gap-2 rounded-xl border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-800">
              <TriangleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{t("infra.maintenance.failed", { tasks: last.errors.map((k) => t(`infra.maintenance.task.${k}`)).join(", ") })}</span>
            </p>
          ) : null}
          {last ? (
            <dl data-testid="maintenance-counts" className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 xl:grid-cols-3">
              {tasks.map((key) => {
                const c = last.counts[key];
                const n = c ? (last.dry_run ? c.examined : c.changed) : null;
                return (
                  <div key={key} data-task={key} className="flex items-baseline justify-between gap-3 border-b border-slate-50 py-0.5">
                    <dt className="min-w-0 text-slate-600">{t(`infra.maintenance.task.${key}`)}</dt>
                    <dd className={cn("shrink-0 tabular-nums", n && key !== "measure_storage" ? "font-semibold text-slate-900" : "text-slate-500")}>
                      {key === "measure_storage" ? (c ? t("infra.maintenance.measured") : "—") : n === null ? "—" : num(n)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog open={confirm} title={t("infra.maintenance.confirmTitle")} effect={t("infra.maintenance.confirmEffect")}
        confirmLabel={t("infra.maintenance.apply")} tone="danger" busy={busy === "apply"}
        error={error && confirm ? <OrgError error={error} /> : undefined}
        onConfirm={() => void run(true)} onCancel={() => { setConfirm(false); setError(null); }} />
    </section>
  );
}
