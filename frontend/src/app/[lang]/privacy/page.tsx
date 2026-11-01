"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { fmtApiDate, parseApiDate } from "@/lib/format";
import { Badge, Button, Card, ErrorState, LinkButton, LoadingState, PageHeader } from "@/components/ui";
import { AgeButtons } from "@/components/privacy/AgeButtons";
import { DataRequests } from "@/components/privacy/DataRequests";
import { ParentCode } from "@/components/privacy/ParentCode";
import { ParentsList } from "@/components/privacy/ParentsList";
import { PolicyAccept } from "@/components/privacy/PolicyAccept";
import { getMyPrivacy, getPolicies, giveConsents, ownPolicyIds, setMyAgeBand, type AgeBand, type PolicyKind, type PrivacyState } from "@/components/privacy/privacyApi";
import { PrivacyError, privacyErrorText } from "@/components/privacy/privacyErrors";

/** Existing account without a band: the three buttons, the policies from 14 up, `Confirm` (a set band cannot be changed). */
function ChooseAge({ onDone }: { onDone: (s: PrivacyState) => void }) {
  const { lang, t } = useTranslation();
  const [band, setBand] = useState<AgeBand | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = async () => {
    if (!band) return;
    setBusy(true);
    setError(null);
    try {
      const ids = band === "under_14" ? [] : ownPolicyIds(await getPolicies(lang));
      onDone(await setMyAgeBand(band, ids));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <AgeButtons value={band} onChoose={(b) => { setBand(b); setError(null); }} />
      {band && band !== "under_14" && <div className="mt-3"><PolicyAccept checked={accepted} onChange={setAccepted} /></div>}
      <PrivacyError error={error} className="mt-3" />
      <Button className="mt-3" fullWidth loading={busy} disabled={!band || busy || (band !== "under_14" && !accepted)} onClick={() => void submit()}>
        {t("privacy.confirm")}
      </Button>
    </Card>
  );
}

/** Under 14 and no parent's consent yet: the code at the top, nothing else needed. */
function NeedsParent({ state, onCheck }: { state: PrivacyState; onCheck: () => Promise<void> }) {
  const { lang, t } = useTranslation();
  const [checking, setChecking] = useState(false);
  const dueAt = parseApiDate(state.consent_due_at);
  const due = dueAt && dueAt > new Date() ? state.consent_due_at : null;
  return (
    <Card title={t("privacy.code.title")} description={due ? t("privacy.code.due", { date: fmtApiDate(due, lang) }) : undefined}>
      <ParentCode />
      <ParentsList compact />
      <Button className="mt-3" variant="secondary" loading={checking} disabled={checking}
        onClick={() => { setChecking(true); void onCheck().finally(() => setChecking(false)); }}>
        {t("privacy.code.check")}
      </Button>
    </Card>
  );
}

function Documents({ state, onDone }: { state: PrivacyState; onDone: (s: PrivacyState) => void }) {
  const { lang, t } = useTranslation();
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const kinds: PolicyKind[] = state.age_band === "under_14" ? ["guardian_consent"] : ["privacy", "terms"];
  const missing = (k: PolicyKind) => state.needs.some((n) => n.kind === k);
  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await giveConsents(state.needs.map((n) => n.policy_version_id)));
      setAccepted(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title={t("privacy.documents.title")}>
      <ul className="divide-y divide-slate-100">
        {kinds.map((k) => (
          <li key={k} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
            <Link href={`/${lang}/policies/${k}`} className="inline-flex min-h-11 min-w-0 items-center break-words font-medium text-brand-700 underline underline-offset-2 sm:min-h-0">{t(`privacy.policies.${k}`)}</Link>
            <Badge className="shrink-0" tone={missing(k) ? "warning" : "success"}>{t(missing(k) ? "privacy.documents.missing" : "privacy.documents.accepted")}</Badge>
          </li>
        ))}
      </ul>
      {state.needs.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <PolicyAccept checked={accepted} onChange={setAccepted} />
          <PrivacyError error={error} className="mt-2" />
          <Button className="mt-2" loading={busy} disabled={!accepted || busy} onClick={() => void accept()}>{t("privacy.documents.accept")}</Button>
        </div>
      )}
    </Card>
  );
}

export default function PrivacyPage() {
  const { lang, t } = useTranslation();
  const { reload: reloadMe, error: meError } = useLmsMe();
  const [state, setState] = useState<PrivacyState | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      setState(await getMyPrivacy());
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  // The gate lifted: the shell's profile, refused until now, loads again.
  const lifted = !!state && state.consent_state !== "pending_guardian" && meError?.code === "consent_required";
  useEffect(() => { if (lifted) void reloadMe(); }, [lifted, reloadMe]);

  const title = t("privacy.title");
  if (!state) {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title={title} />
        {error ? <ErrorState message={privacyErrorText(t, error)} onRetry={() => void load()} /> : <LoadingState label={t("lms.common.loading")} />}
      </div>
    );
  }

  if (state.consent_state === "pending_guardian") {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title={title} />
        <PrivacyError error={error} className="mb-3" />
        <NeedsParent state={state} onCheck={load} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={title} />
      <div className="space-y-4">
        {state.age_band === null ? <ChooseAge onDone={setState} /> : (
          <>
            <Card title={t("privacy.age.label")}>
              <p className="text-base font-medium text-slate-900">{t(`privacy.age.${state.age_band}`)}</p>
            </Card>
            <Documents state={state} onDone={setState} />
          </>
        )}
        <Card title={t("privacy.parents.title")}>
          <ParentsList />
          <div className="mt-4 border-t border-slate-100 pt-4"><ParentCode /></div>
        </Card>
        {state.age_band === "18_plus" && (
          <Card title={t("privacy.parentLink")}>
            <LinkButton href={`/${lang}/parent`} variant="secondary">{t("privacy.parentOpen")}</LinkButton>
          </Card>
        )}
        <Card title={t("privacy.data.title")}>
          <DataRequests state={state} onChanged={load} />
        </Card>
      </div>
    </div>
  );
}
