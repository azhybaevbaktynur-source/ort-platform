"use client";

// S3 access on the platform admin's user page: the person's passes and the codes they used. F6b: "Выдать Pro" (plan,
// days or an end date, reason, at most 400 days) and "Отменить Pro" (every open pass, reason) with the Pro tab's
// dialogs; revoke one pass (reason). Moving a pass to another account = revoke here and give there (design 7.8).
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtPassEnd, fmtPassShort, getUserAccess, revokePass, type PassOut, type UserAccessOut } from "@/lib/lms/access";
import { Badge, Button, Card, ErrorState, ReasonDialog, Skeleton, toast, type BadgeTone } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { CancelProDialog, GrantProDialog, planLabel } from "@/components/lms/access/ProAdminUi";

function passState(p: PassOut, now: number): { key: string; tone: BadgeTone } {
  if (p.revoked_at) return { key: "statusRevoked", tone: "danger" };
  if (p.active) return { key: "statusActive", tone: "success" };
  return new Date(p.starts_at).getTime() > now ? { key: "statusFuture", tone: "info" } : { key: "statusEnded", tone: "neutral" };
}

export function UserAccessSection({ userId, name, readOnly = false }: { userId: string; name: string; readOnly?: boolean }) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [data, setData] = useState<UserAccessOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [granting, setGranting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [revoking, setRevoking] = useState<PassOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try { setData(await getUserAccess(userId)); } catch (e) { setError(e); }
  }, [userId]);
  useEffect(() => { void load(); }, [load]);

  const revoke = async (reason: string) => {
    if (!revoking) return;
    setBusy(true);
    setDialogError(null);
    try {
      setData(await revokePass(revoking.id, reason));
      setRevoking(null);
      toast.success(t("access.admin.user.revokedToast"));
    } catch (e) { setDialogError(errorText(e)); } finally { setBusy(false); }
  };

  const now = Date.now();
  const source = (p: PassOut) => p.source === "code" ? t("access.admin.user.source.code", { last4: p.code_last4 ?? "" })
    : p.source === "admin" ? t("access.admin.user.source.admin", { name: p.granted_by ?? "—" }) : t("access.admin.user.source.payment");
  return (
    <Card className="mb-6" title={t("access.admin.user.title")} padding="none"
      actions={!readOnly ? <>
        {data?.active && <Button variant="dangerOutline" size="sm" onClick={() => setCancelling(true)}>{t("access.admin.user.cancel")}</Button>}
        <Button variant="secondary" size="sm" onClick={() => setGranting(true)}>{t("access.admin.pro.grant")}</Button>
      </> : undefined}>
      <div className="px-4 pb-4 sm:px-6">
        {error && !data ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} /> : !data ? <Skeleton className="h-6 w-1/2" /> : (
          <>
            <p className="mb-3">
              {data.active
                ? <Badge tone="success">{t("access.admin.user.active", { date: fmtPassEnd(data.ends_at, lang) })}</Badge>
                : <span className="text-sm text-slate-600">{t("access.admin.user.none")}</span>}
            </p>
            <h3 className="mb-1 text-sm font-semibold text-slate-800">{t("access.admin.user.passes")}</h3>
            {data.passes.length === 0 ? <p className="text-sm text-slate-600">{t("access.admin.user.noPasses")}</p> : (
              <ul className="divide-y divide-slate-100 border-y border-slate-100">
                {data.passes.map((p) => {
                  const st = passState(p, now);
                  return (
                    <li key={p.id} className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 py-2.5 text-sm">
                      <span className="min-w-0">
                        <span className="block text-slate-900">{t("access.admin.user.period", { from: fmtPassShort(p.starts_at, lang), to: fmtPassShort(p.ends_at, lang, true) })}</span>
                        <span className="block break-words text-slate-600">{source(p)}{p.plan ? ` · ${planLabel(p.plan, t)}` : ""}{p.reason ? ` · ${p.reason}` : ""}</span>
                      </span>
                      <span className="flex items-center gap-2">
                        <Badge tone={st.tone}>{t(`access.admin.user.${st.key}`)}</Badge>
                        {!readOnly && !p.revoked_at && new Date(p.ends_at).getTime() > now && (
                          <Button variant="link" size="sm" className="text-danger-700" onClick={() => { setDialogError(null); setRevoking(p); }}>{t("access.admin.user.revoke")}</Button>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            {data.redemptions.length > 0 && (
              <>
                <h3 className="mb-1 mt-4 text-sm font-semibold text-slate-800">{t("access.admin.user.redemptions")}</h3>
                <ul className="space-y-1 text-sm text-slate-700">
                  {data.redemptions.map((r) => (
                    <li key={r.code_id}>{t("access.admin.user.redemption", { last4: r.last4, batch: r.batch_label })} · {fmtPassShort(r.redeemed_at, lang)}</li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </div>
      <GrantProDialog open={granting} person={{ id: userId, display_name: name, email: name }} currentEnd={data?.active ? data.ends_at : null}
        onClose={() => setGranting(false)} onGranted={(out) => { setData(out); setGranting(false); }} />
      <CancelProDialog person={cancelling ? { id: userId, name } : null} onClose={() => setCancelling(false)}
        onCancelled={(out) => { setData(out); setCancelling(false); }} />
      <ReasonDialog open={!!revoking} title={t("access.admin.user.revokeTitle")} object={name}
        effect={t("access.admin.user.revokeBody")} confirmLabel={t("access.admin.user.revoke")} tone="danger" busy={busy}
        error={dialogError ?? undefined} onConfirm={(r) => void revoke(r)} onCancel={() => setRevoking(null)} />
    </Card>
  );
}
