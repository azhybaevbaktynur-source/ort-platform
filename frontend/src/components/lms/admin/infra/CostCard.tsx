"use client";

import React from "react";
import { Wallet } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { InfraCosts } from "@/lib/lms/infra";
import { StatTile } from "@/components/ui";

/** Monthly cost estimate (static rows mirroring docs/COSTS.md). */
export function CostCard({ costs }: { costs: InfraCosts }) {
  const { lang, t } = useTranslation();
  const usd = (n: number) => new Intl.NumberFormat(lang, { style: "currency", currency: "USD" }).format(n);
  return (
    <div data-testid="infra-costs">
      <StatTile size="sm" className="h-full" icon={<Wallet />} label={t("infra.costs.title")} value={usd(costs.total_usd)}
        hint={
          <>
            {!costs.complete ? <span className="block">{t("infra.costs.incomplete")}</span> : null}
            <span className="block">{t("infra.costs.source", { source: costs.source, date: costs.as_of })}</span>
            <span className="mt-1 block space-y-0.5">
              {costs.rows.map((r) => (
                <span key={r.key} className="block">
                  {r.service} · {r.plan}: {r.usd_per_month === null ? t("infra.costs.unknown") : usd(r.usd_per_month)}
                  {r.next_plan ? ` (${t("infra.costs.next", { plan: r.next_plan })}${r.next_usd_per_month !== null ? ` ${usd(r.next_usd_per_month)}` : ""}${r.verified ? "" : `, ${t("infra.costs.unverified")}`})` : ""}
                </span>
              ))}
            </span>
          </>
        } />
    </div>
  );
}
