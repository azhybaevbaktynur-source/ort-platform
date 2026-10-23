"use client";

import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { joinByCode, normalizeJoinCode } from "@/lib/lms/courses";
import type { JoinOut } from "@/lib/lms/types";
import { JoinCodeInput } from "./JoinCodeInput";

/**
 * Join form. Every failure except rate limiting and network problems shows the same message
 * (P1-5: no code-validity oracle).
 */
export function JoinCodeForm({ initialCode = "", onJoined }: { initialCode?: string; onJoined: (r: JoinOut) => void }) {
  const { t } = useTranslation();
  const [code, setCode] = useState(normalizeJoinCode(initialCode).slice(0, 8));
  const [busy, setBusy] = useState(false);
  const [errKey, setErrKey] = useState<string | null>(null);
  const [retry, setRetry] = useState<number | null>(null);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setBusy(true);
    setErrKey(null);
    setRetry(null);
    try {
      onJoined(await joinByCode(normalizeJoinCode(code)));
    } catch (e) {
      const err = e as { code?: string; status?: number; details?: Record<string, unknown> };
      if (err.code === "rate_limited") {
        setErrKey("lms.errors.rate_limited");
        const r = err.details?.retry_after_seconds;
        setRetry(typeof r === "number" ? r : null);
      } else if (err.code === "network") {
        setErrKey("lms.errors.network");
      } else {
        setErrKey("lms.errors.join_code_invalid");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <p id="join-hint" className="text-sm text-slate-600">{t("courses.join.hint")}</p>
      <JoinCodeInput value={code} onChange={setCode} disabled={busy} invalid={!!errKey} describedBy={errKey ? "join-error" : "join-hint"} />
      {errKey && (
        <p id="join-error" role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">
          {t(errKey)}
          {retry !== null && <span className="block text-xs">{t("lms.common.retryAfter", { seconds: retry })}</span>}
        </p>
      )}
      <button type="submit" disabled={busy || code.length < 8}
        className="w-full rounded-xl bg-brand-600 px-4 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
        {busy ? t("lms.common.loading") : t("courses.join.submit")}
      </button>
    </form>
  );
}
