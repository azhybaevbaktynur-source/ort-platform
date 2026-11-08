"use client";

// FB8-5 S4 (STAFF_UX_AUDIT §6): the system health in one line on the overview; the full card is on /admin/health.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { getPlatformHealth, type PlatformHealth } from "@/lib/lms/security";
import { Skeleton, cn, focusRing } from "@/components/ui";

/** Failed checks of a health answer (database, migrations, email, storage). */
export const failedHealthChecks = (h: PlatformHealth) =>
  [h.database.ok, h.migrations.ok, h.email.ok, h.storage.ok].filter((ok) => !ok).length;

/** One `GET /platform/health` for the overview (the line and the attention list share it). */
export function usePlatformHealth(enabled = true) {
  const [health, setHealth] = useState<PlatformHealth | null>(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(async () => {
    setFailed(false);
    try { setHealth(await getPlatformHealth()); } catch { setHealth(null); setFailed(true); }
  }, []);
  useEffect(() => { if (enabled) void load(); }, [enabled, load]);
  return { health, failed };
}

export function HealthLine({ health, failed }: { health: PlatformHealth | null; failed: boolean }) {
  const { lang, t } = useTranslation();
  const n = health ? failedHealthChecks(health) : 0;
  const ok = !!health && health.ok && n === 0;
  const status = failed ? t("adminHealth.unavailable") : ok ? t("adminHealth.line.ok") : t("adminHealth.line.problems", { count: n });
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700"
      data-testid="health-line">
      <span className="font-semibold text-slate-900">{t("adminHealth.title")}</span>
      {!health && !failed ? <Skeleton className="h-4 w-40" /> : (
        <span className="inline-flex items-center gap-2">
          <span aria-hidden="true" className={cn("h-2.5 w-2.5 rounded-full", ok ? "bg-success-600" : failed ? "bg-slate-400" : "bg-danger-600")} />
          {status}
        </span>
      )}
      {health?.commit && <span className="text-slate-600">{t("adminHealth.line.commit", { commit: health.commit.slice(0, 7) })}</span>}
      <Link href={`/${lang}/admin/health`} className={cn("ml-auto inline-flex min-h-11 items-center font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
        {t("adminHealth.line.details")}
      </Link>
    </p>
  );
}
