"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { fmtApiDate } from "@/lib/format";
import { getMyPrivacy, type PrivacyState } from "./privacyApi";

function bannerText(state: PrivacyState, t: (k: string, p?: Record<string, string | number>) => string, lang: string): string | null {
  if (state.consent_state === "exempt") return null;
  if (state.age_band === null) return t("privacy.banner.age");
  if (state.consent_state === "pending_guardian") return t("privacy.banner.parent", { date: fmtApiDate(state.consent_due_at, lang) });
  return state.needs.length > 0 ? t("privacy.banner.accept") : null;
}

/** The home page's one small line (PHASE_11_DESIGN 3.3): nothing is restricted. Navigation only: fails silently. */
export function PrivacyBanner() {
  const { lang, t } = useTranslation();
  const [state, setState] = useState<PrivacyState | null>(null);
  useEffect(() => {
    let alive = true;
    getMyPrivacy().then((s) => { if (alive) setState(s); }).catch(() => { if (alive) setState(null); });
    return () => { alive = false; };
  }, []);
  const text = state && bannerText(state, t, lang);
  if (!text) return null;
  return (
    <Link href={`/${lang}/privacy`} className="mb-6 flex min-h-11 items-center gap-3 rounded-2xl border border-warning-200 bg-warning-50 px-4 py-2 text-sm font-semibold text-warning-900 hover:bg-warning-100">
      <ShieldCheck className="h-5 w-5 shrink-0" aria-hidden="true" />
      <span className="min-w-0 break-words">{text}</span>
    </Link>
  );
}
