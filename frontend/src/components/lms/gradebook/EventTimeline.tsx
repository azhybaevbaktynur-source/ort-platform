"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { GradeEventOut } from "@/lib/lms/gradingTypes";
import { fmtDateTime } from "@/components/lms/assessments/format";
import { eventChanges } from "./gradebookModel";

const FIELDS = new Set([
  "override_points", "released_at", "excused", "state", "display_value", "effective_points", "raw_points",
  "kept_attempt_id", "scheme_version_id", "status", "label", "late_deduction",
]);

/** Grade-event history of one submission (newest first as sent by the server). */
export function EventTimeline({ events }: { events: GradeEventOut[] }) {
  const { t } = useTranslation();
  if (events.length === 0) return <p className="text-sm text-slate-500">{t("gradebook.events.empty")}</p>;
  const fieldName = (k: string) => (FIELDS.has(k) ? t(`gradebook.fields.${k}`) : k);
  const value = (k: string, v: string) => {
    if (v === "true") return t("gradebook.fields.yes");
    if (v === "false") return t("gradebook.fields.no");
    if (k.endsWith("_at") && v !== "—") return fmtDateTime(v) || v;
    return v;
  };
  return (
    <ol className="space-y-3 border-l-2 border-slate-200 pl-4">
      {events.map((e) => {
        const changes = eventChanges(e);
        return (
          <li key={e.id} className="relative text-sm">
            <span className="absolute -left-[1.4rem] top-1.5 h-2.5 w-2.5 rounded-full bg-slate-400" aria-hidden="true" />
            <p className="font-semibold text-slate-900">{t(`gradebook.events.types.${e.event}`)}</p>
            <p className="text-xs text-slate-500">
              {e.actor_name || t("gradebook.events.system")} · {fmtDateTime(e.created_at)}
            </p>
            {changes.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-slate-700">
                {changes.map((c) => (
                  <li key={c.key} className="break-words">
                    <span className="text-slate-500">{fieldName(c.key)}:</span> {value(c.key, c.from)} → {value(c.key, c.to)}
                  </li>
                ))}
              </ul>
            )}
            {e.reason && <p className="mt-1 whitespace-pre-wrap break-words text-xs text-slate-700"><span className="text-slate-500">{t("gradebook.events.reason")}:</span> {e.reason}</p>}
          </li>
        );
      })}
    </ol>
  );
}
