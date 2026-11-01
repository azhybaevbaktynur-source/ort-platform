"use client";

import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDateTimeShort } from "@/lib/format";
import { Button } from "@/components/ui";
import { createPairingCode, type PairingCode } from "./privacyApi";
import { PrivacyError } from "./privacyErrors";

/** `Get code`, then the code in large type. The code is shown once: another press replaces it. */
export function ParentCode() {
  const { lang, t } = useTranslation();
  const [code, setCode] = useState<PairingCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const get = async () => {
    setBusy(true);
    setError(null);
    try {
      setCode(await createPairingCode());
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      {code && (
        <div className="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-center">
          <p data-testid="pairing-code" className="break-all font-mono text-3xl font-bold tracking-widest text-slate-900 sm:text-4xl">{code.code}</p>
          <p className="mt-1 text-sm text-slate-600">{t("privacy.code.valid", { date: fmtApiDateTimeShort(code.expires_at, lang) })}</p>
        </div>
      )}
      <PrivacyError error={error} className="mb-3" />
      <Button variant={code ? "secondary" : "primary"} loading={busy} disabled={busy} onClick={() => void get()}>
        {code ? t("privacy.code.new") : t("privacy.code.get")}
      </Button>
    </div>
  );
}
