"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { Badge, Button, Card, EmptyState, Input, LinkButton, LoadingState } from "@/components/ui";
import { GuardianError } from "./GuardianError";
import { listLinks, redeemCode, type GuardianLink } from "./api";

/** `/[lang]/parent`: enter a code, and the students already linked (PHASE_11_DESIGN 11). */
export function ParentHome() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { reload: reloadMe } = useLmsMe();
  const [links, setLinks] = useState<GuardianLink[] | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setLinks(await listLinks());
    } catch (e) {
      setLoadError(e);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const link = await redeemCode(code);
      void reloadMe(); // UX rework 2: the header's Parent area comes from MeOut
      router.push(`/${lang}/parent/${link.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  if ((loadError as { code?: string } | null)?.code === "guardian_must_be_adult") {
    return (
      <div className="max-w-2xl">
        <h1 className="mb-4 text-2xl font-bold text-slate-900">{t("guardian.title")}</h1>
        <EmptyState icon={<Users />} title={t("guardian.adultOnly.title")} description={t("guardian.adultOnly.body")}
          action={<LinkButton href={`/${lang}/privacy`} prefetch={false}>{t("guardian.adultOnly.action")}</LinkButton>} />
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <h1 className="mb-4 text-2xl font-bold text-slate-900">{t("guardian.title")}</h1>

      <Card className="mb-6">
        <form onSubmit={submit} className="space-y-3">
          <Input label={t("guardian.code.label")} hint={t("guardian.code.hint")} value={code} autoComplete="off"
            autoCapitalize="characters" spellCheck={false} maxLength={32} onChange={(ev) => setCode(ev.target.value)}
            className="font-mono uppercase tracking-widest" />
          <GuardianError error={error} />
          <Button type="submit" loading={busy} disabled={!code.trim()} className="w-full sm:w-auto">{t("guardian.code.submit")}</Button>
        </form>
      </Card>

      <h2 className="mb-2 text-lg font-semibold text-slate-900">{t("guardian.students")}</h2>
      {loadError ? (
        <GuardianError error={loadError} onRetry={() => void load()} />
      ) : links === null ? (
        <LoadingState rows={2} />
      ) : links.length === 0 ? (
        <EmptyState icon={<Users />} title={t("guardian.noStudents")} />
      ) : (
        <ul className="space-y-2">
          {links.map((link) => (
            <li key={link.id}>
              <Link href={`/${lang}/parent/${link.id}`}
                className="flex min-h-11 items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 hover:bg-slate-50">
                <span className="min-w-0 flex-1 break-words font-medium text-slate-900">{link.student_name}</span>
                {link.needs_consent && <Badge tone="warning">{t("guardian.needsConsent")}</Badge>}
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
