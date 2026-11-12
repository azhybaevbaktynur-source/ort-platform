"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { formatBytes } from "@/lib/lms/storage";
import type { InfraMetric } from "@/lib/lms/infra";

export const BAR = { ok: "bg-brand-600", notice: "bg-warning-300", warning: "bg-warning-500", critical: "bg-danger-600" } as const;
export const TEXT = { ok: "text-slate-600", notice: "text-warning-800", warning: "text-warning-900", critical: "text-danger-700" } as const;

/** One usage line: label, "value of limit", percent and a bar coloured by the server's `level`. */
export function MetricBar({ metric }: { metric: InfraMetric }) {
  const { lang, t } = useTranslation();
  const num = (n: number) => new Intl.NumberFormat(lang, { maximumFractionDigits: 2 }).format(n);
  const units: [string, string, string, string] = [t("storage.units.b"), t("storage.units.kb"), t("storage.units.mb"), t("storage.units.gb")];
  const fmt = (n: number): string => {
    switch (metric.unit) {
      case "bytes": return formatBytes(n, lang, units);
      case "cu_hours": return t("infra.units.cuHours", { n: num(n) });
      case "seconds": return t("infra.units.hours", { n: num(n / 3600) });
      default: return num(n);
    }
  };
  const label = t(`infra.metric.${metric.key}`);
  const value = metric.value === null ? "-" : fmt(metric.value);
  const text = metric.limit === null ? value : t("infra.of", { value, limit: fmt(metric.limit) });
  const pct = metric.percent === null ? null : Math.min(100, Math.max(0, metric.percent));
  return (
    <div data-testid={`metric-${metric.key}${metric.source ? `-${metric.source}` : ""}`} data-level={metric.level}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-sm font-medium text-slate-800">
          {label}
          {metric.source ? <span className="ml-1.5 text-xs font-normal text-slate-600">· {t(`infra.source.${metric.source}`)}</span> : null}
        </span>
        <span className={`text-sm ${TEXT[metric.level]}`}>
          {text}
          {metric.percent !== null ? <span className="ml-1.5 font-semibold">{new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(metric.percent)}%</span> : null}
          {metric.level !== "ok" ? <span className="sr-only"> ({t(`infra.level.${metric.level}`)})</span> : null}
        </span>
      </div>
      {pct !== null ? (
        <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
          <div className={`h-2 rounded-full ${BAR[metric.level]}`} style={{ width: `${pct}%` }} />
        </div>
      ) : metric.limit === null && metric.value !== null ? (
        <p className="mt-0.5 text-xs text-slate-600">{t("infra.noLimit")}</p>
      ) : null}
    </div>
  );
}
