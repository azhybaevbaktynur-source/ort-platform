"use client";

// S4 email change (A9) on the account page: the current address; a change needs the current password and is confirmed
// from a link sent to the new address. Nothing changes until that link is opened.
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { EMAIL_RE, cancelEmailChange, getMyEmail, requestEmailChange, type MyEmail } from "@/lib/lms/emailChange";
import { Button, Card, Input, Skeleton, toast } from "@/components/ui";
import { OrgError } from "@/components/lms/org/OrgUi";
import { useAuth } from "@/lib/auth-context";

export function EmailCard() {
  const { lang, t } = useTranslation();
  const [data, setData] = useState<MyEmail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState(""); // platform admins only: the current two-step login code
  const isAdmin = !!useAuth().userProfile?.is_platform_admin;
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setData(await getMyEmail()); setError(null); } catch (e) { setError(e); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = email.trim();
    if (!EMAIL_RE.test(clean)) { setProblem(t("privacy.email.invalid")); return; }
    setProblem(null);
    setBusy(true);
    setError(null);
    try {
      setData(await requestEmailChange(clean, password, lang, isAdmin ? code.trim() : undefined));
      setEditing(false);
      setEmail("");
      setPassword("");
      setCode("");
      toast.success(t("privacy.email.requested", { email: clean.toLowerCase() }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    setBusy(true);
    setError(null);
    try {
      await cancelEmailChange();
      toast.success(t("privacy.email.cancelled"));
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={t("privacy.email.title")}>
      {!data ? (error ? <OrgError error={error} onRetry={() => void load()} /> : <Skeleton className="h-6 w-1/2" />) : (
        <div className="space-y-3" data-testid="email-card">
          <p className="text-sm text-slate-600">{t("privacy.email.current")}</p>
          <p className="break-all text-base font-medium text-slate-900">{data.email}</p>
          {data.pending && (
            <div className="rounded-xl border border-brand-200 bg-brand-50 px-3.5 py-3 text-sm text-brand-900">
              <p className="break-words">{t(data.pending.by_admin ? "privacy.email.sentByAdmin" : "privacy.email.sent", { email: data.pending.new_email })}</p>
              <p className="mt-1 text-brand-800">{t("privacy.email.after")}</p>
              <Button className="mt-2" variant="secondary" size="sm" disabled={busy} onClick={() => void cancel()}>{t("privacy.email.cancelPending")}</Button>
            </div>
          )}
          {editing ? (
            <form onSubmit={(e) => void submit(e)} className="space-y-3 border-t border-slate-100 pt-3" noValidate>
              <Input id="my-new-email" type="email" inputMode="email" autoComplete="email" label={t("privacy.email.newEmail")}
                value={email} onChange={(e) => setEmail(e.target.value)} required />
              <Input id="my-email-password" type="password" autoComplete="current-password" label={t("privacy.email.password")}
                hint={t("privacy.email.passwordHint")} value={password} onChange={(e) => setPassword(e.target.value)} required />
              {isAdmin && (
                <Input id="my-email-code" inputMode="numeric" autoComplete="one-time-code" label={t("adminSecurity.confirmCode.label")}
                  hint={t("privacy.email.codeHint")} value={code} onChange={(e) => setCode(e.target.value)} required containerClassName="max-w-xs" />
              )}
              <p className="text-sm text-slate-600">{t("privacy.email.after")}</p>
              {problem && <p role="alert" className="text-sm font-medium text-danger-700">{problem}</p>}
              {error ? <OrgError error={error} /> : null}
              <div className="flex flex-wrap gap-2">
                <Button type="submit" loading={busy} disabled={busy || !email.trim() || !password || (isAdmin && !code.trim())}>{t("privacy.email.submit")}</Button>
                <Button type="button" variant="secondary" disabled={busy} onClick={() => { setEditing(false); setProblem(null); setError(null); }}>{t("privacy.email.cancel")}</Button>
              </div>
            </form>
          ) : (
            <>
              {error ? <OrgError error={error} /> : null}
              <Button variant="secondary" onClick={() => { setEditing(true); setError(null); }}>{t("privacy.email.change")}</Button>
            </>
          )}
        </div>
      )}
    </Card>
  );
}
