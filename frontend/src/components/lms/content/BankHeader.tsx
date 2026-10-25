"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { BankOut } from "@/lib/lms/contentTypes";
import { PageHeader, TabsNav } from "@/components/ui";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";

/**
 * Bank title with a questions/passages tab switch.
 * Phase 6b S5c: design-system `PageHeader` (breadcrumbs, one primary action) and `TabsNav`.
 */
export function BankHeader({
  courseId, bank, active, primaryAction, secondaryActions,
}: {
  courseId: string;
  bank: BankOut | null;
  active: "questions" | "passages";
  primaryAction?: React.ReactNode;
  secondaryActions?: React.ReactNode;
}) {
  const { lang, t } = useTranslation();
  const base = `/${lang}/courses/${courseId}/bank`;
  const crumbs = useTabCrumbs("bank", [{ label: bank?.title || "…" }], courseId);
  return (
    <div className="mb-4">
      <PageHeader breadcrumbs={crumbs} title={bank?.title || "…"} primaryAction={primaryAction} secondaryActions={secondaryActions} className="mb-3" />
      {bank && (
        <TabsNav label={bank.title} items={[
          { href: `${base}/${bank.id}`, label: t("bank.questions.tab", { n: bank.question_count }), active: active === "questions" },
          { href: `${base}/${bank.id}/passages`, label: t("bank.passages.tab", { n: bank.passage_count }), active: active === "passages" },
        ]} />
      )}
    </div>
  );
}
