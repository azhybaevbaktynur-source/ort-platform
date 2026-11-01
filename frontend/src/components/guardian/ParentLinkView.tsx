"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { Badge, Button, Card, ConfirmDialog, EmptyState, LinkButton, LoadingState } from "@/components/ui";
import { fmtApiDate } from "@/lib/format";
import { GuardianError, useGuardianErrorText } from "./GuardianError";
import { ParentTabs } from "./ParentTabs";
import {
  currentPolicies, giveConsent, listLinks, removeLink, requestDelete, withdrawConsent, type GuardianLink, type PolicyOut,
} from "./api";

type Confirming = "remove" | "withdraw" | "delete" | null;

/** Consent text, its draft badge and the button. The whole screen while a child's consent is pending. */
function ConsentCard({ link, onDone }: { link: GuardianLink; onDone: () => Promise<void> }) {
  const { lang, t } = useTranslation();
  const [policy, setPolicy] = useState<PolicyOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    currentPolicies(lang)
      .then((rows) => { if (alive) setPolicy(rows.find((p) => p.kind === "guardian_consent") ?? null); })
      .catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [lang]);

  const consent = async () => {
    if (!policy) return;
    setBusy(true);
    setError(null);
    try {
      await giveConsent(link.id, policy.id);
      await onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <h2 className="text-lg font-semibold text-slate-900">{t("guardian.consent.title")}</h2>
      <p className="mt-1 text-base leading-6 text-slate-700 sm:text-sm">{t("guardian.consent.body", { name: link.student_name })}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Link href={`/${lang}/policies/guardian_consent`} prefetch={false} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 underline sm:min-h-0">
          {t("guardian.consent.read")}
        </Link>
        {policy?.status === "draft_legal_review" && <Badge tone="warning">{t("guardian.consent.draft")}</Badge>}
      </div>
      <GuardianError error={error} className="mt-3" />
      <Button className="mt-4 w-full sm:w-auto" loading={busy} disabled={!policy} onClick={() => void consent()}>
        {t("guardian.consent.confirm")}
      </Button>
    </Card>
  );
}

/** `/[lang]/parent/[linkId]`: grades, due dates and announcements, or the consent screen (PHASE_11_DESIGN 11). */
export function ParentLinkView({ linkId }: { linkId: string }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useGuardianErrorText();
  const [link, setLink] = useState<GuardianLink | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [confirming, setConfirming] = useState<Confirming>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [deleteDue, setDeleteDue] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const rows = await listLinks();
      setLink(rows.find((row) => row.id === linkId) ?? null);
    } catch (e) {
      setLoadError(e);
    }
  }, [linkId]);

  useEffect(() => { void load(); }, [load]);

  const back = (
    <Link href={`/${lang}/parent`} className="inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0">
      {t("guardian.back")}
    </Link>
  );

  if (loadError) {
    return <div className="max-w-3xl">{back}<GuardianError error={loadError} onRetry={() => void load()} className="mt-2" /></div>;
  }
  if (link === undefined) return <LoadingState rows={3} />;
  if (link === null) {
    return (
      <div className="max-w-3xl">
        {back}
        <EmptyState className="mt-2" title={t("guardian.errors.guardian_link_not_found")}
          action={<LinkButton href={`/${lang}/parent`}>{t("guardian.back")}</LinkButton>} />
      </div>
    );
  }

  const name = link.student_name;
  const close = () => { setConfirming(null); setActionError(null); };
  const run = async () => {
    setBusy(true);
    setActionError(null);
    try {
      if (confirming === "remove") {
        await removeLink(link.id);
        router.push(`/${lang}/parent`);
        return;
      }
      if (confirming === "withdraw") await withdrawConsent(link.id);
      if (confirming === "delete") setDeleteDue((await requestDelete(link.id)).due_at);
      close();
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  const dialog = confirming && {
    remove: { title: t("guardian.remove.title"), effect: t("guardian.remove.effect", { name }), confirm: t("guardian.remove.action") },
    withdraw: { title: t("guardian.withdraw.title"), effect: t("guardian.withdraw.effect", { name }), confirm: t("guardian.withdraw.action") },
    delete: { title: t("guardian.delete.title"), effect: t("guardian.delete.effect", { name }), confirm: t("guardian.delete.action") },
  }[confirming];

  return (
    <div className="max-w-3xl">
      {back}
      <div className="mb-4 mt-2 flex flex-wrap items-center justify-between gap-2">
        <h1 className="min-w-0 break-words text-2xl font-bold text-slate-900">{name}</h1>
        <Button variant="secondary" size="sm" onClick={() => setConfirming("remove")}>{t("guardian.remove.action")}</Button>
      </div>

      {link.needs_consent ? (
        <ConsentCard link={link} onDone={load} />
      ) : (
        <ParentTabs linkId={link.id} onConsentNeeded={load} />
      )}

      {link.under_14 && !link.needs_consent && (
        link.holds_consent ? (
          <Card className="mt-6">
            <h2 className="text-lg font-semibold text-slate-900">{t("guardian.consent.title")}</h2>
            <p className="mt-1 text-sm text-slate-700">{t("guardian.consent.held")}</p>
            {deleteDue && <p role="status" className="mt-2 text-sm text-slate-700">{t("guardian.delete.sent", { date: fmtApiDate(deleteDue, lang) })}</p>}
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <Button variant="secondary" onClick={() => setConfirming("withdraw")}>{t("guardian.withdraw.action")}</Button>
              {!deleteDue && <Button variant="secondary" onClick={() => setConfirming("delete")}>{t("guardian.delete.action")}</Button>}
            </div>
          </Card>
        ) : (
          <div className="mt-6"><ConsentCard link={link} onDone={load} /></div>
        )
      )}

      {dialog && (
        <ConfirmDialog open title={dialog.title} object={name} effect={dialog.effect} confirmLabel={dialog.confirm} tone="danger"
          busy={busy} error={actionError ? (errorText(actionError) ?? <GuardianError error={actionError} />) : undefined}
          onConfirm={() => void run()} onCancel={close} />
      )}
    </div>
  );
}
