"use client";

import React from "react";
import { FileUp } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { EmptyState } from "@/components/ui";

/**
 * Phase 9 S2: the slot of the org area's Roster import page. The wizard (`RosterImportWizard`) is slice S3's file;
 * at integration (S5) this body becomes `<RosterImportWizard orgId={orgId} readOnly={readOnly} />`.
 */
export function RosterImportSlot({ orgId, readOnly }: { orgId: string; readOnly: boolean }) {
  const { t } = useTranslation();
  void orgId;
  void readOnly;
  return <EmptyState icon={<FileUp />} title={t("organizations.org.rosterImportSoon")} />;
}
