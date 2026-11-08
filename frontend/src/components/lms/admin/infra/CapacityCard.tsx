"use client";

import React from "react";
import { Database } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { formatBytes } from "@/lib/lms/storage";
import type { InfraCapacity } from "@/lib/lms/infra";
import { Badge, StatTile } from "@/components/ui";

/** "How many full 6,000-student exams still fit in the database." */
export function CapacityCard({ capacity }: { capacity: InfraCapacity }) {
  const { lang, t } = useTranslation();
  const units: [string, string, string, string] = [t("storage.units.b"), t("storage.units.kb"), t("storage.units.mb"), t("storage.units.gb")];
  const bytes = (n: number) => formatBytes(n, lang, units);
  const num = (n: number) => new Intl.NumberFormat(lang).format(n);
  return (
    <div data-testid="infra-capacity">
      <StatTile size="sm" className="h-full" icon={<Database />}
        label={t("infra.capacity.fits", { students: num(capacity.students) })}
        value={<>{num(capacity.fits)}{capacity.estimated ? <Badge tone="neutral" className="ml-2 align-middle">{t("infra.capacity.estimated")}</Badge> : null}</>}
        hint={
          <>
            <span className="block">{t("infra.capacity.perExam", { size: bytes(capacity.exam_bytes) })}</span>
            <span className="block">{t("infra.capacity.used", { used: bytes(capacity.used_bytes), limit: bytes(capacity.limit_bytes) })} ({t(`infra.capacity.source.${capacity.used_source}`)})</span>
            {capacity.history_seconds ? <span className="block">{t("infra.capacity.history", { hours: num(Math.round(capacity.history_seconds / 3600)) })}</span> : null}
            <span className="block">{t("infra.capacity.launch")}</span>
          </>
        } />
    </div>
  );
}
