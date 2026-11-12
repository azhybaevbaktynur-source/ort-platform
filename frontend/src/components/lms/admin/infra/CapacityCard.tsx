"use client";

import React from "react";
import { Database, Info, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { formatBytes } from "@/lib/lms/storage";
import type { InfraCapacity } from "@/lib/lms/infra";
import { Badge, cn } from "@/components/ui";
import { BAR, TEXT } from "./MetricBar";
import { ago } from "./ServiceCard";

const BOX = {
  ok: "border-slate-200 bg-white", notice: "border-warning-200 bg-white", warning: "border-warning-300 bg-warning-50/40",
  critical: "border-danger-300 bg-danger-50/40",
} as const;

/** "How many full 6,000-student exams still fit in the database", with its inputs and the database levels
 *  (DB_STORAGE_REVIEW 7: notice 50 %, warning 70 %, critical 85 %, raised when no full exam fits; server-side). */
export function CapacityCard({ capacity }: { capacity: InfraCapacity }) {
  const { lang, t } = useTranslation();
  const units: [string, string, string, string] = [t("storage.units.b"), t("storage.units.kb"), t("storage.units.mb"), t("storage.units.gb")];
  const bytes = (n: number) => formatBytes(n, lang, units);
  const num = (n: number) => new Intl.NumberFormat(lang).format(n);
  const level = capacity.level ?? "ok";
  const percent = capacity.percent;
  const pct = percent === null ? null : Math.min(100, Math.max(0, percent));
  const price = capacity.upgrade_storage_usd_per_gb_month;
  const usd = price === null ? "" : new Intl.NumberFormat(lang, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(price);
  const urgent = level === "warning" || level === "critical";
  return (
    <section data-testid="infra-capacity" data-level={level} aria-labelledby="infra-capacity-title"
      className={cn("flex h-full flex-col gap-3 rounded-2xl border p-3 shadow-sm", BOX[level])}>
      <div className="flex items-start gap-2.5">
        <span aria-hidden="true" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700 [&>svg]:h-4 [&>svg]:w-4">
          <Database />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="infra-capacity-title" className="text-sm font-medium leading-5 text-slate-600">{t("infra.capacity.fits", { students: num(capacity.students) })}</h2>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xl font-bold leading-7 text-slate-900">
            <span data-testid="infra-capacity-fits">{num(capacity.fits)}</span>
            {capacity.estimated ? <Badge tone="neutral">{t("infra.capacity.estimated")}</Badge> : null}
            {level !== "ok" ? (
              <Badge tone={level === "critical" ? "danger" : "warning"} icon={<TriangleAlert aria-hidden="true" className="h-3.5 w-3.5" />}>
                {t(`infra.level.${level}`)}
              </Badge>
            ) : null}
          </p>
        </div>
      </div>

      <div data-testid="infra-capacity-used">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
          <span className="text-slate-800">
            {t("infra.capacity.used", { used: bytes(capacity.used_bytes), limit: bytes(capacity.limit_bytes) })}
            <span className="ml-1.5 text-xs text-slate-600">· {t(`infra.capacity.source.${capacity.used_source}`)}</span>
          </span>
          {percent !== null ? (
            <span className={cn("font-semibold", TEXT[level])}>{t("infra.capacity.percent", { percent: new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(percent) })}</span>
          ) : null}
        </div>
        {pct !== null ? (
          <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label={t("infra.metric.storage")}
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
            <div className={cn("h-2 rounded-full", BAR[level])} style={{ width: `${pct}%` }} />
          </div>
        ) : null}
      </div>

      {level === "notice" ? (
        <p data-testid="infra-capacity-advice" className="rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm leading-5 text-warning-900">
          {t("infra.capacity.notice")}
        </p>
      ) : null}
      {urgent ? (
        <p data-testid="infra-capacity-advice" role="alert"
          className={cn("flex gap-2 rounded-xl border px-3 py-2 text-sm font-medium leading-5",
            level === "critical" ? "border-danger-200 bg-danger-50 text-danger-800" : "border-warning-300 bg-warning-50 text-warning-900")}>
          <TriangleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{t("infra.capacity.upgradeHint", { price: usd })}</span>
        </p>
      ) : null}

      <ul className="space-y-0.5 text-sm leading-5 text-slate-600">
        <li>{t("infra.capacity.perExam", { size: bytes(capacity.exam_bytes) })}</li>
        {capacity.branches !== null && capacity.branches_limit !== null ? (
          <li data-testid="infra-capacity-branches">{t("infra.capacity.branches", { value: num(capacity.branches), limit: num(capacity.branches_limit) })}</li>
        ) : null}
        {capacity.history_seconds ? <li>{t("infra.capacity.history", { hours: num(Math.round(capacity.history_seconds / 3600)) })}</li> : null}
        {capacity.measured_at ? <li data-testid="infra-capacity-measured">{t("infra.capacity.measured", { when: ago(capacity.measured_at, lang, t("infra.never")) })}</li> : null}
        {level === "ok" ? <li>{t("infra.capacity.launch")}</li> : null}
      </ul>

      <p data-testid="infra-capacity-writes-stop" className="mt-auto flex gap-2 border-t border-slate-100 pt-3 text-xs leading-5 text-slate-600">
        <Info aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{t("infra.capacity.writesStop")}</span>
      </p>
    </section>
  );
}
