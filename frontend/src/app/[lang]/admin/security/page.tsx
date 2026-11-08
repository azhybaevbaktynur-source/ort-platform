"use client";

// S1 admin security: the platform admin's own two-step login (set up, new recovery codes) and "end all my sessions".
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { LogOut, ShieldCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { fmtApiDateTimeShort } from "@/lib/format";
import {
  confirmMfa, getMfaStatus, logoutEverywhere, regenerateRecoveryCodes, startMfaSetup, type MfaSetup, type MfaStatus,
} from "@/lib/lms/security";
import { Badge, Button, Card, ConfirmDialog, Input, LoadingState, PageHeader, STAFF_WIDTH } from "@/components/ui";
import { useAdminCrumbs, useAdminSummary } from "@/components/lms/admin/AdminShell";
import { RecoveryCodes } from "@/components/lms/admin/RecoveryCodes";
import { LoadError, OrgError } from "@/components/lms/org/OrgUi";

const onlyDigits = (v: string) => v.replace(/\D/g, "").slice(0, 6);
const grouped = (secret: string) => secret.replace(/(.{4})/g, "$1 ").trim();

export default function AdminSecurityPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const crumbs = useAdminCrumbs();
  const { refresh: refreshSummary } = useAdminSummary();
  const { signOut } = useAuth();
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  // The current password: asked before the setup starts and sent again with the code (security review)
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [regenCode, setRegenCode] = useState("");
  const [endAll, setEndAll] = useState(false);
  const [endError, setEndError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setStatus(await getMfaStatus());
    } catch (e) {
      setLoadError(e);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!setup) { setQr(null); return; }
    let live = true;
    QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 224, errorCorrectionLevel: "M" })
      .then((url) => { if (live) setQr(url); })
      .catch(() => { if (live) setQr(null); }); // the secret below still works
    return () => { live = false; };
  }, [setup]);

  const begin = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setSetup(await startMfaSetup(password));
      setCode("");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await confirmMfa(code, password);
      // Turning it on ended every session, this one too: continue with the new token
      localStorage.setItem("ort_token", res.access_token);
      setCodes(res.recovery_codes);
      setSetup(null);
      setCode("");
      setPassword("");
      await load();
      refreshSummary();
    } catch (err) {
      setError(err);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCodes((await regenerateRecoveryCodes(regenCode)).recovery_codes);
      setRegenCode("");
      await load();
    } catch (err) {
      setError(err);
      setRegenCode("");
    } finally {
      setBusy(false);
    }
  };

  const endAllSessions = async () => {
    setBusy(true);
    setEndError(null);
    try {
      await logoutEverywhere();
      await signOut();
      router.push(`/${lang}/login`);
    } catch (e) {
      setEndError(e);
      setBusy(false);
    }
  };

  const title = t("adminSecurity.title");
  if (loadError && !status) {
    return (
      <div>
        <PageHeader title={title} breadcrumbs={crumbs({ label: title })} />
        <LoadError error={loadError} onRetry={load} />
      </div>
    );
  }
  if (!status) return <LoadingState label={t("lms.common.loading")} />;

  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader title={title} description={t("adminSecurity.description")} breadcrumbs={crumbs({ label: title })}
        badge={status.enabled
          ? <Badge tone="success">{t("adminSecurity.badgeOn")}</Badge>
          : <Badge tone="warning">{t("adminSecurity.badgeOff")}</Badge>} />

      {codes && <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />}

      {!status.enabled && (
        <Card title={t("adminSecurity.setup.title")} className="mb-6"
          description={status.required ? t("adminSecurity.setup.required") : t("adminSecurity.setup.optional")}>
          {!setup ? (
            <>
              <p className="mb-4 text-sm leading-6 text-slate-700">{t("adminSecurity.setup.apps")}</p>
              <form onSubmit={begin} className="space-y-3">
                <Input label={t("adminSecurity.setup.passwordLabel")} hint={t("adminSecurity.setup.passwordHint")}
                  type="password" autoComplete="current-password" required value={password}
                  onChange={(e) => setPassword(e.target.value)} containerClassName="max-w-sm" />
                {error ? <OrgError error={error} /> : null}
                <Button type="submit" loading={busy} disabled={!password}
                  leftIcon={<ShieldCheck aria-hidden="true" className="h-4 w-4" />}>
                  {t("adminSecurity.setup.start")}
                </Button>
              </form>
            </>
          ) : (
            <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
              <div className="flex flex-col items-center">
                {qr
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={qr} alt={t("adminSecurity.setup.qrAlt")} width={224} height={224} className="rounded-xl border border-slate-200" />
                  : <div className="h-56 w-56 rounded-xl border border-slate-200 bg-slate-50" aria-hidden="true" />}
              </div>
              <div className="min-w-0">
                <ol className="mb-4 list-decimal space-y-2 pl-5 text-sm leading-6 text-slate-700">
                  <li>{t("adminSecurity.setup.step1")}</li>
                  <li>{t("adminSecurity.setup.step2")}</li>
                </ol>
                <p className="text-sm font-medium text-slate-800">{t("adminSecurity.setup.secretLabel")}</p>
                <p data-testid="mfa-secret" className="mb-4 mt-1 break-all rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-base tracking-wider text-slate-900">
                  {grouped(setup.secret)}
                </p>
                <form onSubmit={confirm} className="space-y-3">
                  <Input label={t("adminSecurity.setup.codeLabel")} inputMode="numeric" autoComplete="one-time-code"
                    value={code} onChange={(e) => setCode(onlyDigits(e.target.value))} placeholder="000000" maxLength={6}
                    className="max-w-[12rem] font-mono text-lg tracking-[0.3em]" />
                  {error ? <OrgError error={error} /> : null}
                  <Button type="submit" loading={busy} disabled={code.length !== 6}>{t("adminSecurity.setup.confirm")}</Button>
                </form>
              </div>
            </div>
          )}
        </Card>
      )}

      {status.enabled && (
        <Card title={t("adminSecurity.enabled.title")} className="mb-6"
          description={t("adminSecurity.enabled.since", { date: fmtApiDateTimeShort(status.enabled_at, lang) })}>
          <p className="mb-4 text-sm leading-6 text-slate-700">
            {t("adminSecurity.enabled.codesLeft", { n: status.recovery_codes_left })}
          </p>
          <form onSubmit={regenerate} className="space-y-3">
            <Input label={t("adminSecurity.enabled.regenLabel")} hint={t("adminSecurity.enabled.regenHint")}
              inputMode="numeric" autoComplete="one-time-code" value={regenCode} maxLength={6} placeholder="000000"
              onChange={(e) => setRegenCode(onlyDigits(e.target.value))} className="max-w-[12rem] font-mono text-lg tracking-[0.3em]" />
            {error ? <OrgError error={error} /> : null}
            <Button type="submit" variant="secondary" loading={busy} disabled={regenCode.length !== 6}>{t("adminSecurity.enabled.regen")}</Button>
          </form>
        </Card>
      )}

      <Card title={t("adminSecurity.sessions.title")} description={t("adminSecurity.sessions.body")}>
        <Button variant="danger" leftIcon={<LogOut aria-hidden="true" className="h-4 w-4" />}
          onClick={() => { setEndError(null); setEndAll(true); }}>{t("adminSecurity.sessions.button")}</Button>
      </Card>

      <ConfirmDialog open={endAll} title={t("adminSecurity.sessions.confirmTitle")} effect={t("adminSecurity.sessions.confirmBody")}
        confirmLabel={t("adminSecurity.sessions.button")} tone="danger" busy={busy}
        error={endError ? <OrgError error={endError} /> : undefined}
        onConfirm={() => void endAllSessions()} onCancel={() => setEndAll(false)} />
    </div>
  );
}
