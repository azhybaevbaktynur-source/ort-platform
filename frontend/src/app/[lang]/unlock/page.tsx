"use client";

// S3 access (docs/phases/S3_ACCESS_DESIGN.md 5): what a pass includes, how to pay (`access.howToPay`, text the owner
// fills), the code field and the current status. Reached from a locked test, the student menu and the exam-prep page.
import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, KeyRound } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtPassEnd, getMyAccess, redeemCode, type MyAccessOut } from "@/lib/lms/access";
import { Badge, Button, Card, ErrorState, Input, LinkButton, PageHeader, Skeleton, toast } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";

function Included({ practice }: { practice: boolean }) {
  const { t } = useTranslation();
  const rows = [t("access.unlock.includedExams"), ...(practice ? [t("access.unlock.includedPractice")] : []),
    t("access.unlock.includedResults")];
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r} className="flex items-start gap-2.5 text-base leading-6 text-slate-800">
          <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-success-700" />
          <span>{r}</span>
        </li>
      ))}
    </ul>
  );
}

export default function UnlockPage() {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [access, setAccess] = useState<MyAccessOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try { setAccess(await getMyAccess()); } catch (e) { setLoadError(e); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!code.trim()) { setError(t("lms.errors.code_invalid")); return; }
    setBusy(true);
    setError(null);
    try {
      const out = await redeemCode(code);
      setAccess(out);
      setCode("");
      const msg = t("access.unlock.success", { date: fmtPassEnd(out.ends_at ?? out.pass_ends_at, lang) });
      setDone(msg);
      toast.success(msg);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[60rem]">
      <PageHeader title={t("access.unlock.title")} description={t("access.unlock.intro")} />
      {loadError && !access ? <ErrorState message={errorText(loadError)} onRetry={() => void load()} className="mb-6" /> : null}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start">
        <div className="space-y-6">
          <Card title={t("access.unlock.statusTitle")}>
            {!access && !loadError ? <Skeleton className="h-6 w-48" /> : access?.active ? (
              <p className="flex flex-wrap items-center gap-2 text-base leading-6 text-slate-900">
                <Badge tone="success" icon={<CheckCircle2 aria-hidden="true" />}>{t("access.unlock.statusActive", { date: fmtPassEnd(access.ends_at, lang) })}</Badge>
              </p>
            ) : (
              <p className="text-base leading-6 text-slate-700">{t("access.unlock.statusNone")}</p>
            )}
          </Card>
          <Card title={t("access.unlock.codeTitle")}>
            <form onSubmit={submit} noValidate className="space-y-3">
              <Input id="unlock-code" label={t("access.unlock.codeLabel")} hint={t("access.unlock.codeHint")}
                autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={40} value={code}
                error={error ?? undefined} className="font-mono uppercase tracking-wider"
                onChange={(e) => { setCode(e.target.value); if (error) setError(null); if (done) setDone(null); }} />
              <Button type="submit" loading={busy} leftIcon={<KeyRound aria-hidden="true" className="h-4 w-4" />} className="w-full sm:w-auto">
                {t("access.unlock.redeem")}
              </Button>
              {done && <p role="status" className="text-sm font-medium leading-5 text-success-800">{done}</p>}
            </form>
          </Card>
        </div>
        <div className="space-y-6">
          <Card title={t("access.unlock.includedTitle")}>
            <Included practice={!(access?.practice_free ?? false)} />
          </Card>
          <Card title={t("access.unlock.payTitle")}>
            <p className="whitespace-pre-line text-base leading-6 text-slate-700">{t("access.howToPay")}</p>
          </Card>
        </div>
      </div>
      <div className="mt-6">
        <LinkButton variant="link" href={`/${lang}/courses`}>{t("access.unlock.back")}</LinkButton>
      </div>
    </div>
  );
}
