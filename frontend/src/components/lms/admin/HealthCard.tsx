"use client";

import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getPlatformHealth, type PlatformHealth } from "@/lib/lms/security";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { OrgError } from "@/components/lms/org/OrgUi";

function Row({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  const { t } = useTranslation();
  return (
    <li className="flex items-start gap-3 py-3">
      {ok
        ? <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-success-700" />
        : <XCircle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-danger-700" />}
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-slate-900">
          {label} <span className="sr-only">{ok ? t("adminHealth.ok") : t("adminHealth.problem")}</span>
        </span>
        <span className="block break-words text-sm text-slate-600">{detail}</span>
      </span>
    </li>
  );
}

/** S1: the real health check (database, migrations, email, storage); FB8-5 S4: on its own page, /admin/health. */
export function HealthCard({ className, heading = true }: { className?: string; heading?: boolean }) {
  const { t } = useTranslation();
  const [health, setHealth] = useState<PlatformHealth | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHealth(await getPlatformHealth());
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const yesNo = (v: boolean) => (v ? t("platformAdmin.yes") : t("platformAdmin.no"));
  return (
    <Card className={className} title={heading ? t("adminHealth.title") : undefined}
      description={heading ? t("adminHealth.description") : undefined}
      actions={
        <span className="flex items-center gap-2">
          {health && <Badge tone={health.ok ? "success" : "warning"}>{health.ok ? t("adminHealth.allOk") : t("adminHealth.needsAttention")}</Badge>}
          <Button variant="secondary" size="sm" loading={loading} onClick={() => void load()}
            leftIcon={<RefreshCw aria-hidden="true" className="h-4 w-4" />}>{t("adminHealth.check")}</Button>
        </span>
      }>
      {error ? <OrgError error={error} onRetry={load} /> : !health ? <Skeleton className="h-40 w-full" /> : (
        <ul className="divide-y divide-slate-100 border-t border-slate-100" data-testid="health-checks">
          <Row ok={health.database.ok} label={t("adminHealth.database")}
            detail={health.database.ok
              ? t("adminHealth.databaseOk", { ms: health.database.latency_ms ?? 0, dialect: health.database.dialect })
              : t("adminHealth.databaseDown")} />
          <Row ok={health.migrations.ok} label={t("adminHealth.migrations")}
            detail={health.migrations.current.length
              ? t("adminHealth.migrationsDetail", {
                current: health.migrations.current.join(", "), expected: health.migrations.expected.join(", "),
              })
              : t("adminHealth.migrationsUntracked", { expected: health.migrations.expected.join(", ") })} />
          <Row ok={health.email.ok} label={t("adminHealth.email")}
            detail={t("adminHealth.emailDetail", { provider: health.email.provider, configured: yesNo(health.email.configured) })} />
          <Row ok={health.storage.ok} label={t("adminHealth.storage")}
            detail={t("adminHealth.storageDetail", { driver: health.storage.driver, r2: yesNo(health.storage.r2_configured) })} />
        </ul>
      )}
      {health?.commit && <p className="mt-3 text-sm text-slate-600">{t("adminHealth.commit", { commit: health.commit })}</p>}
    </Card>
  );
}
