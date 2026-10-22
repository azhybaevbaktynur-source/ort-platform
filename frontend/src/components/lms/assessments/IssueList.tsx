"use client";

import React from "react";
import { AlertCircle, AlertTriangle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ISSUE_CODES, type Issue } from "@/lib/lms/assessmentTypes";

const KNOWN = new Set<string>(ISSUE_CODES);

/** Normalise the `details` of a publish_invalid error (array or {issues|errors: []}) into issues. */
export function issuesFromDetails(details: unknown): Issue[] {
  const raw = Array.isArray(details)
    ? details
    : details && typeof details === "object"
      ? ((details as { issues?: unknown; errors?: unknown }).issues ?? (details as { errors?: unknown }).errors)
      : null;
  if (!Array.isArray(raw)) return [];
  return raw.filter((x): x is Issue => !!x && typeof x === "object" && typeof (x as Issue).code === "string");
}

export function IssueList({ issues, kind }: { issues: Issue[]; kind: "error" | "warning" }) {
  const { t } = useTranslation();
  if (issues.length === 0) return null;
  const cls = kind === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-900";
  const Icon = kind === "error" ? AlertCircle : AlertTriangle;
  return (
    <ul className={`space-y-1 rounded-xl border px-3.5 py-3 text-sm ${cls}`}>
      {issues.map((i, idx) => (
        <li key={`${i.code}-${i.item_id ?? ""}-${idx}`} className="flex items-start gap-2">
          <Icon className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <span>
            {KNOWN.has(i.code) ? t(`assessments.issues.${i.code}`) : t("assessments.issues.unknown", { code: i.code })}
            {typeof i.section_pos === "number" && <span className="text-xs opacity-75"> · {t("assessments.issues.section", { n: i.section_pos })}</span>}
            {i.language && <span className="text-xs opacity-75"> · {String(i.language).toUpperCase()}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
