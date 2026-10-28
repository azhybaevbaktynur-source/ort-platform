"use client";

// Phase 8b S4: the server's `spec_invalid` details (and the client pre-check) as one list with "Go to" links that
// switch to the right tab, open the section and focus the field (PHASE_8B_DESIGN 9.1).
import React from "react";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { SpecIssue } from "@/lib/lms/examTemplateTypes";
import { Button } from "@/components/ui";
import { useSpecIssueText } from "./ui";

export function IssuesBar({ issues, sectionName, onGoTo }: {
  issues: SpecIssue[];
  sectionName: (i: number) => string;
  onGoTo: (loc: (string | number)[]) => void;
}) {
  const { t } = useTranslation();
  const text = useSpecIssueText(sectionName);
  if (!issues.length) return null;
  return (
    <div role="alert" className="rounded-xl border border-danger-200 bg-danger-50 px-3.5 py-3 text-sm text-danger-800">
      <p className="flex items-center gap-2 font-semibold">
        <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />{t("examTemplates.constructor.issuesBar.title", { n: issues.length })}
      </p>
      <p className="mt-1 text-danger-900">{t("examTemplates.constructor.issuesBar.body")}</p>
      <ul className="mt-2 space-y-1">
        {issues.map((i, idx) => (
          <li key={idx} className="flex flex-wrap items-center gap-x-2">
            <span className="min-w-0 break-words"><span className="font-medium">{text.where(i.loc)}</span>: {text.what(i)}</span>
            <Button variant="link" size="sm" className="px-1" onClick={() => onGoTo(i.loc)}
              aria-label={t("examTemplates.constructor.issuesBar.goToField", { field: text.where(i.loc) })}>
              {t("examTemplates.constructor.issuesBar.goTo")}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
