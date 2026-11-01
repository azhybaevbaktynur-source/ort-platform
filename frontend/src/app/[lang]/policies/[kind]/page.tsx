"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { UiLanguageSwitcher } from "@/components/auth/AuthHeader";
import { Brand } from "@/components/ui/AppHeader";
import { Badge, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { PolicyBody } from "@/components/privacy/PolicyBody";
import { getPolicies, POLICY_KINDS, type PolicyKind, type PolicyOut } from "@/components/privacy/privacyApi";
import { privacyErrorText } from "@/components/privacy/privacyErrors";

/** A policy's current text, public (linked from the sign-up form). */
export default function PolicyPage() {
  const { lang, t } = useTranslation();
  const { kind } = useParams<{ kind: string }>();
  const known = POLICY_KINDS.includes(kind as PolicyKind);
  const [policy, setPolicy] = useState<PolicyOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPolicy((await getPolicies(lang)).find((p) => p.kind === kind) ?? null);
    } catch (e) {
      setError(e);
    }
  }, [lang, kind]);
  useEffect(() => { if (known) void load(); }, [known, load]);

  return (
    <div className="min-h-screen bg-slate-50 py-6 sm:py-8">
      <main className="mx-auto w-full max-w-2xl px-4">
        <div className="mb-6 flex items-center justify-between gap-3">
          <Brand href={`/${lang}`} tagline />
          <UiLanguageSwitcher />
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          {!known ? <EmptyState variant="plain" title={t("privacy.policies.notFound")} />
            : error ? <ErrorState message={privacyErrorText(t, error)} onRetry={() => void load()} />
            : !policy ? <LoadingState label={t("lms.common.loading")} />
            : (
              <>
                {policy.status === "draft_legal_review" && <Badge tone="warning" className="mb-3 whitespace-normal">{t("privacy.draftBadge")}</Badge>}
                <PolicyBody body={policy.body} />
              </>
            )}
        </div>
      </main>
    </div>
  );
}
