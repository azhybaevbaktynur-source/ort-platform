"use client";

import React, { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { BankOut } from "@/lib/lms/contentTypes";
import { shareBank, unshareBank, type BankSharingOut } from "@/lib/lms/organizations";
import { MenuButton, toast } from "@/components/ui";
import { apiErrorText } from "@/components/lms/org/OrgUi";

/** Whether the "⋯" menu has its share entry for this bank (callers render nothing otherwise). */
export function shareToggleVisible(bank: BankOut | null, sharing: BankSharingOut | null): boolean {
  if (!bank || !sharing || !bank.can_edit || bank.assessment || bank.deleted_at) return false;
  if (sharing.reason === "template_locked" || sharing.reason === "personal") return false;
  return bank.visibility === "organization" || sharing.enabled;
}

/**
 * Phase 9 UX: an org admin reading a course (no enrollment, `read_only`) on a private bank cannot share it (only the
 * course's teachers can; the server refuses anyway): the "More actions" menu shows the share entry disabled with
 * that hint.
 */
export function shareHintVisible(bank: BankOut | null, sharing: BankSharingOut | null, readOnlyViewer: boolean): boolean {
  if (!readOnlyViewer || !bank || !sharing || bank.can_edit || bank.assessment || bank.deleted_at) return false;
  if (sharing.reason === "template_locked" || sharing.reason === "personal") return false;
  return bank.visibility === "private";
}

export function ShareBankHint() {
  const { t } = useTranslation();
  return (
    <MenuButton variant="secondary" label={t("sharedBanks.menu")}
      leftIcon={<MoreHorizontal aria-hidden="true" className="h-4 w-4" />}
      items={[{ id: "share", label: t("sharedBanks.share"), description: t("sharedBanks.teachersOnly"), disabled: true }]}
      onSelect={() => undefined} />
  );
}

/**
 * Phase 9 S2 (PHASE_9_DESIGN 4.2, 8.1): "Share with organization" / "Stop sharing" in the bank page's "⋯" menu.
 * Rendered only when the caller may edit the bank (`bank.can_edit`), the bank is a live course bank (never a quiz
 * bank) and `GET /courses/{id}/bank-sharing` allows sharing; a bank that is already shared can always be unshared.
 * The server enforces every rule (ORT and personal organizations are refused there too).
 */
export function ShareBankToggle({ courseId, bank, sharing, onChanged }: {
  courseId: string;
  bank: BankOut;
  sharing: BankSharingOut | null;
  onChanged: (bank: BankOut) => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  if (!sharing || !shareToggleVisible(bank, sharing)) return null;
  const shared = bank.visibility === "organization";

  const run = async () => {
    setBusy(true);
    try {
      const out = shared ? await unshareBank(courseId, bank.id) : await shareBank(courseId, bank.id);
      toast.success(t(shared ? "sharedBanks.unsharedToast" : "sharedBanks.sharedToast"));
      onChanged(out);
    } catch (e) {
      toast.error(apiErrorText(t, e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <MenuButton variant="secondary" label={t("sharedBanks.menu")} disabled={busy}
      leftIcon={<MoreHorizontal aria-hidden="true" className="h-4 w-4" />}
      items={[shared
        ? { id: "unshare", label: t("sharedBanks.unshare"), description: t("sharedBanks.unshareHint") }
        : { id: "share", label: t("sharedBanks.share"), description: t("sharedBanks.shareHint", { org: sharing.root_name }) }]}
      onSelect={() => void run()} />
  );
}
