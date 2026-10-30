"use client";

import React, { useCallback, useState } from "react";
import { Library } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listSharedBanks } from "@/lib/lms/organizations";
import { EmptyState, LinkButton, PageHeader, SearchInput } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { SharedBankList } from "@/components/lms/org/SharedBankList";
import { LoadError } from "@/components/lms/org/OrgUi";
import { useCursorList, useDebounced } from "@/components/lms/admin/useCursorList";

/**
 * Phase 9 S2 (PHASE_9_DESIGN 4.2, 8.1): every bank shared in the organization's whole tree. An org admin opens a
 * bank in its home course (they may edit shared banks, `can_edit_bank`); teachers copy banks from their course.
 */
export default function OrgSharedBanksPage() {
  const { lang, t } = useTranslation();
  const { org, crumbs } = useOrg();
  const [input, setInput] = useState("");
  const q = useDebounced(input);
  const fetchPage = useCallback((cursor: string | null) => listSharedBanks(org.id, { cursor, q: q || undefined }), [org.id, q]);
  const list = useCursorList(fetchPage);
  const status = (list.error as { status?: number } | null)?.status;

  return (
    <div>
      <PageHeader title={t("sharedBanks.title")} description={t("sharedBanks.intro")} breadcrumbs={crumbs({ label: t("sharedBanks.nav") })} />
      {status === 404 ? (
        <EmptyState icon={<Library />} title={t("sharedBanks.noAccess")} />
      ) : (
        <div className="space-y-4">
          <SearchInput value={input} onChange={setInput} label={t("sharedBanks.search")} placeholder={t("sharedBanks.search")} containerClassName="sm:max-w-sm" />
          {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : (
            <>
              {!list.loading && list.items.length === 0 && (
                <EmptyState icon={<Library />} title={q ? t("sharedBanks.emptySearch") : t("sharedBanks.empty")}
                  description={q ? undefined : t("sharedBanks.emptyHint")} />
              )}
              <SharedBankList items={list.items} loading={list.loading} hasMore={!!list.cursor} onMore={list.loadMore}
                action={(b) => (
                  <LinkButton variant="secondary" size="sm" href={`/${lang}/courses/${b.course_id}/bank/${b.id}`}>{t("sharedBanks.open")}</LinkButton>
                )} />
            </>
          )}
        </div>
      )}
    </div>
  );
}
