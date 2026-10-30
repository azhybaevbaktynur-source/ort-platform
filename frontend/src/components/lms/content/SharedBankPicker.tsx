"use client";

import React, { useCallback, useMemo, useState } from "react";
import { Copy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { BankOut } from "@/lib/lms/contentTypes";
import { copySharedBank, listSharedBanks, type BankSharingOut } from "@/lib/lms/organizations";
import { Button, EmptyState, toast } from "@/components/ui";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { SharedBankList } from "@/components/lms/org/SharedBankList";
import { OrgError } from "@/components/lms/org/OrgUi";

/**
 * Phase 9 S2 (PHASE_9_DESIGN 4.2, 8.1): the "From my organization" section of a course's Question banks page:
 * banks shared in the course's organization tree, each with "Copy into this course". Rendered only when
 * `GET /courses/{id}/bank-sharing` says `can_copy` (course staff with content.manage, never ORT). The course's own
 * shared banks are left out (they are already listed above).
 */
export function SharedBankPicker({ courseId, sharing, onCopied }: {
  courseId: string;
  sharing: BankSharingOut;
  onCopied: (bank: BankOut) => void;
}) {
  const { t } = useTranslation();
  const fetchPage = useCallback((cursor: string | null) => listSharedBanks(sharing.root_id, { cursor }), [sharing.root_id]);
  const list = useCursorList(fetchPage);
  const items = useMemo(() => list.items.filter((b) => b.course_id !== courseId), [list.items, courseId]);
  const [copying, setCopying] = useState<string | null>(null);
  const [copyError, setCopyError] = useState<unknown>(null);

  const copy = async (bankId: string) => {
    setCopying(bankId);
    setCopyError(null);
    try {
      const out = await copySharedBank(courseId, bankId);
      toast.success(t("sharedBanks.copied", { title: out.title }));
      onCopied(out);
    } catch (e) {
      setCopyError(e);
    } finally {
      setCopying(null);
    }
  };

  return (
    <section aria-labelledby="bank-group-org" className="space-y-2 pt-2">
      <h2 id="bank-group-org" className="text-sm font-semibold text-slate-700">{t("sharedBanks.pickerTitle")}</h2>
      <p className="text-sm text-slate-600">{t("sharedBanks.pickerIntro", { org: sharing.root_name })}</p>
      <OrgError error={copyError} />
      {list.error ? <OrgError error={list.error} onRetry={list.reload} /> : (
        <>
          {!list.loading && items.length === 0 && !list.cursor && (
            <EmptyState variant="plain" className="py-4" title={t("sharedBanks.pickerEmpty")} />
          )}
          <SharedBankList items={items} loading={list.loading} hasMore={!!list.cursor} onMore={list.loadMore}
            action={(b) => (
              <Button variant="secondary" size="sm" loading={copying === b.id} disabled={copying !== null && copying !== b.id}
                aria-label={t("sharedBanks.copyLabel", { title: b.title })}
                leftIcon={<Copy aria-hidden="true" className="h-4 w-4" />} onClick={() => void copy(b.id)}>
                {t("sharedBanks.copy")}
              </Button>
            )} />
        </>
      )}
    </section>
  );
}
