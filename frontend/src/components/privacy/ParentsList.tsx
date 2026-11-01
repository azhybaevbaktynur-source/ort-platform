"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Badge, Button, ConfirmDialog, LoadingState } from "@/components/ui";
import { listMyGuardians, removeMyGuardian, type GuardianRow } from "./privacyApi";
import { PrivacyError } from "./privacyErrors";

/**
 * The parents linked to this account, each removable (the server refuses an under-14's only consent holder).
 * `compact` (the under-14 code screen): names only, and nothing at all until there is a parent.
 */
export function ParentsList({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<GuardianRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [removing, setRemoving] = useState<GuardianRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [removeError, setRemoveError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    listMyGuardians().then(setRows).catch(setError);
  }, []);
  useEffect(load, [load]);

  const confirm = async () => {
    if (!removing) return;
    setBusy(true);
    setRemoveError(null);
    try {
      await removeMyGuardian(removing.id);
      setRemoving(null);
      load();
    } catch (e) {
      setRemoveError(e);
    } finally {
      setBusy(false);
    }
  };

  if (compact && (error || !rows || rows.length === 0)) return null;
  if (error) {
    return (
      <div className="space-y-2">
        <PrivacyError error={error} />
        <Button variant="secondary" size="sm" onClick={load}>{t("lms.common.retry")}</Button>
      </div>
    );
  }
  if (!rows) return <LoadingState label={t("lms.common.loading")} />;
  if (rows.length === 0) return <p className="text-sm text-slate-600">{t("privacy.parents.none")}</p>;
  return (
    <>
      <ul className={compact ? "mt-4 divide-y divide-slate-100 border-t border-slate-100 pt-2" : "divide-y divide-slate-100"}>
        {rows.map((g) => (
          <li key={g.id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
            <span className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="min-w-0 break-words font-medium text-slate-900">{g.guardian_name}</span>
              {g.holds_consent && <Badge tone="success">{t("privacy.parents.holdsConsent")}</Badge>}
            </span>
            {!compact && (
              <Button variant="secondary" size="sm" onClick={() => { setRemoveError(null); setRemoving(g); }}>{t("privacy.parents.remove")}</Button>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog open={!!removing} tone="danger" busy={busy}
        title={t("privacy.parents.removeTitle")} object={removing?.guardian_name}
        effect={t("privacy.parents.removeEffect")} confirmLabel={t("privacy.parents.remove")}
        error={removeError ? <PrivacyError error={removeError} /> : undefined}
        onConfirm={() => void confirm()} onCancel={() => setRemoving(null)} />
    </>
  );
}
