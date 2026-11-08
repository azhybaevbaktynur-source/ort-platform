"use client";

import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { LmsApiError } from "@/lib/lms/client";
import { getInfra, refreshInfra, type InfraOut } from "@/lib/lms/infra";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { ServiceCard, ago } from "@/components/lms/admin/infra/ServiceCard";
import { CapacityCard } from "@/components/lms/admin/infra/CapacityCard";
import { CostCard } from "@/components/lms/admin/infra/CostCard";
import { LoadError, OrgError } from "@/components/lms/org/OrgUi";
import { Button, LoadingState, PageHeader, STAFF_WIDTH } from "@/components/ui";

const POLL_MS = 3000;

export default function AdminServicesPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [data, setData] = useState<InfraOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [limited, setLimited] = useState(false);
  const [refreshError, setRefreshError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getInfra());
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  // another request is refreshing a provider: look again in a few seconds
  const anyRefreshing = !!data?.cards.some((c) => c.status === "refreshing");
  useEffect(() => {
    if (!anyRefreshing) return;
    const id = setTimeout(() => void load(), POLL_MS);
    return () => clearTimeout(id);
  }, [anyRefreshing, data, load]);

  const refresh = async () => {
    setBusy(true);
    setLimited(false);
    setRefreshError(null);
    try {
      setData(await refreshInfra());
    } catch (e) {
      if (e instanceof LmsApiError && (e.status === 429 || e.code === "rate_limited")) setLimited(true);
      else setRefreshError(e);
    } finally {
      setBusy(false);
    }
  };

  const working = busy || anyRefreshing;
  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader title={t("infra.title")} description={t("infra.subtitle")} breadcrumbs={crumbs({ label: t("infra.nav") })}
        secondaryActions={
          <Button variant="secondary" leftIcon={<RefreshCw aria-hidden="true" className="h-4 w-4" />} onClick={() => void refresh()} loading={busy} disabled={working}>
            {working ? t("infra.refreshing") : t("infra.refresh")}
          </Button>
        }>
        {data ? <p data-testid="infra-updated" className="mt-2 text-sm text-slate-600">{t("infra.updated", { when: ago(data.generated_at, lang, t("infra.never")) })}</p> : null}
      </PageHeader>
      {error && !data ? <LoadError error={error} onRetry={() => void load()} /> : null}
      {error && data ? <OrgError error={error} onRetry={() => void load()} className="mb-4" /> : null}
      {limited ? <p role="alert" data-testid="infra-rate-limited" className="mb-4 rounded-xl border border-warning-200 bg-warning-50 px-3.5 py-3 text-sm text-warning-900">{t("infra.rateLimited")}</p> : null}
      {refreshError ? <OrgError error={refreshError} className="mb-4" /> : null}
      {!data && !error ? <LoadingState label={t("lms.common.loading")} /> : null}
      {data ? (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <CapacityCard capacity={data.capacity} />
            <CostCard costs={data.costs} />
          </div>
          <div className="grid gap-4 md:grid-cols-2 min-[1700px]:grid-cols-3" data-testid="infra-cards">
            {data.cards.map((c) => <ServiceCard key={c.provider} card={c} />)}
          </div>
        </div>
      ) : null}
    </div>
  );
}
