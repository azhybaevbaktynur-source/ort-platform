"use client";

import React from "react";
import Link from "next/link";
import { ExternalLink, Loader2, PlugZap, TriangleAlert, XCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { INFRA_EMAIL_ENV, INFRA_ENV, cardTone, type InfraCard } from "@/lib/lms/infra";
import { Badge, Card } from "@/components/ui";
import { MetricBar } from "./MetricBar";

const BORDER = {
  ok: "", muted: "bg-slate-50", warning: "border-warning-300", critical: "border-danger-300", error: "border-danger-300",
} as const;

/** "5 minutes ago" in the page language. */
export function ago(iso: string | null, lang: string, never: string): string {
  if (!iso) return never;
  const min = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  if (Math.abs(min) < 60) return rtf.format(min, "minute");
  if (Math.abs(min) < 1440) return rtf.format(Math.round(min / 60), "hour");
  return rtf.format(Math.round(min / 1440), "day");
}

export function ServiceCard({ card }: { card: InfraCard }) {
  const { lang, t } = useTranslation();
  const tone = cardTone(card);
  const emailProvider = typeof card.details.provider === "string" ? card.details.provider : "";
  const envVars = card.provider === "email" ? INFRA_EMAIL_ENV[emailProvider] : INFRA_ENV[card.provider];
  const when = ago(card.fetched_at, lang, t("infra.never"));
  const reason = t(`infra.error.${card.error_code ?? "unknown"}`);
  const deployStatus = card.details.deploy_state ?? card.details.deploy_status;
  const commit = card.details.deploy_commit;
  const storagePage = card.provider === "r2" && typeof card.details.storage_page === "string" ? `/${lang}${card.details.storage_page}` : null;
  const hasData = card.metrics.length > 0 || card.flags.length > 0 || card.plan !== null;
  const showData = card.status !== "not_connected" && card.status !== "unavailable";

  return (
    <Card as="article" headingLevel={2} data-testid={`service-${card.provider}`} data-status={card.status} data-tone={tone}
      className={`flex flex-col ${BORDER[tone]}`}
      title={t(`infra.provider.${card.provider}.name`)} description={t(`infra.provider.${card.provider}.role`)}
      actions={card.plan ? <Badge tone="info">{t("infra.plan", { plan: card.plan })}</Badge> : undefined}>
      <div className="flex flex-1 flex-col gap-3">
        {card.status === "not_connected" ? (
          <p className="flex gap-2 text-sm leading-6 text-slate-700">
            <PlugZap aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
            <span>
              <span className="font-medium">{t("infra.status.not_connected")}</span>
              {envVars ? <>{": "}{t("infra.setOnServer")} <code className="break-words rounded bg-slate-100 px-1 py-0.5 text-xs">{envVars.join(", ")}</code></> : null}
            </span>
          </p>
        ) : null}
        {card.status === "unavailable" ? <p className="text-sm leading-6 text-slate-700">{t("infra.unavailable")}</p> : null}
        {card.status === "error" ? (
          <p role="alert" className="flex gap-2 rounded-xl border border-danger-200 bg-danger-50 px-3 py-2 text-sm leading-5 text-danger-800">
            <XCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              {t("infra.errorLine", { reason })}{card.error_status ? ` (${card.error_status})` : ""}
              {hasData && card.fetched_at ? <span className="block text-xs">{t("infra.previous", { when })}</span> : null}
            </span>
          </p>
        ) : null}
        {card.status === "refreshing" ? (
          <p role="status" className="flex items-center gap-2 text-sm text-slate-700">
            <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />{t("infra.status.refreshing")}
          </p>
        ) : null}

        {card.metrics.length > 0 ? (
          <div className="space-y-3">{card.metrics.map((m) => <MetricBar key={`${m.key}-${m.source ?? ""}`} metric={m} />)}</div>
        ) : null}
        {showData && card.flags.length > 0 ? (
          <ul className="flex flex-wrap gap-2" aria-label={t("infra.flags")}>
            {card.flags.map((f) => (
              <li key={f.key}>
                <Badge tone={f.level === "critical" ? "danger" : "warning"} icon={<TriangleAlert aria-hidden="true" className="h-3.5 w-3.5" />}>{t(`infra.flag.${f.key}`)}</Badge>
              </li>
            ))}
          </ul>
        ) : null}
        {showData && deployStatus ? (
          <p className="text-sm text-slate-700">{t("infra.deploy", { status: String(deployStatus), commit: commit ? String(commit) : "-" })}</p>
        ) : null}

        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 pt-3 text-sm text-slate-600">
          {card.fetched_at ? <span>{t("infra.fetchedAt", { when })}</span> : null}
          {card.dashboard_url ? (
            <a href={card.dashboard_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 font-medium text-brand-700 hover:underline sm:min-h-0">
              {t("infra.openDashboard")}<ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
            </a>
          ) : null}
          {storagePage ? <Link href={storagePage} className="inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0">{t("infra.openStorage")}</Link> : null}
        </div>
      </div>
    </Card>
  );
}
