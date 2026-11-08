"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { API_BASE_URL } from "@/lib/apiBase";
import { buttonClasses } from "@/components/ui";

type Providers = { google: boolean; apple: boolean };

// once per tab (AUTH_SOCIAL_DESIGN 7.2)
let cached: Providers | null = null;
let pending: Promise<Providers> | null = null;

function loadProviders(): Promise<Providers> {
  if (cached) return Promise.resolve(cached);
  if (!pending) {
    pending = fetch(`${API_BASE_URL}/auth/providers`)
      .then((r) => (r.ok ? r.json() : { google: false, apple: false }))
      .then((d) => (cached = { google: d?.google === true, apple: d?.apple === true }))
      .catch(() => { pending = null; return { google: false, apple: false }; });
  }
  return pending;
}

/** Test hook: forget the answer of `GET /auth/providers`. */
export function resetProvidersCache() { cached = null; pending = null; }

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0">
      <path fill="#4285F4" d="M22.5 12.2c0-.8-.1-1.5-.2-2.2H12v4.2h5.9a5 5 0 0 1-2.2 3.3v2.7h3.5c2.1-1.9 3.3-4.7 3.3-8z" />
      <path fill="#34A853" d="M12 23c3 0 5.4-1 7.2-2.7l-3.5-2.7c-1 .7-2.2 1-3.7 1-2.8 0-5.2-1.9-6-4.5H2.4v2.8A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M6 14.1a6.6 6.6 0 0 1 0-4.2V7.1H2.4a11 11 0 0 0 0 9.8z" />
      <path fill="#EA4335" d="M12 5.4c1.6 0 3 .6 4.1 1.6l3.1-3.1A11 11 0 0 0 2.4 7.1L6 9.9c.8-2.6 3.2-4.5 6-4.5z" />
    </svg>
  );
}

function AppleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="currentColor">
      <path d="M16.4 12.6c0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.4-1.8-1.4-.1-2.8.9-3.5.9s-1.8-.8-3-.8c-1.5 0-3 .9-3.8 2.3-1.6 2.8-.4 7 1.2 9.3.8 1.1 1.7 2.4 2.9 2.3 1.2 0 1.6-.7 3-.7s1.8.7 3 .7c1.3 0 2.1-1.1 2.8-2.3.9-1.3 1.3-2.6 1.3-2.6s-2.5-1-2.5-3.8zM14.1 5.8c.6-.8 1.1-1.9.9-3-.9 0-2.1.6-2.7 1.4-.6.7-1.1 1.8-.9 2.9 1 .1 2.1-.5 2.7-1.3z" />
    </svg>
  );
}

/**
 * "Continue with Google / Apple" plus the "or" divider, each shown only if `GET /auth/providers` says it is on. Links, not
 * form posts: the frontend CSP has `form-action 'self'` (AUTH_SOCIAL_DESIGN 8.3). Renders nothing while no provider is on.
 */
export function useProviders(): Providers | null {
  const [providers, setProviders] = useState<Providers | null>(cached);
  useEffect(() => {
    let live = true;
    loadProviders().then((p) => { if (live) setProviders(p); });
    return () => { live = false; };
  }, []);
  return providers;
}

export function ProviderButtons({ redirect }: { redirect?: string | null }) {
  const { lang, t } = useTranslation();
  const providers = useProviders();
  if (!providers || (!providers.google && !providers.apple)) return null;
  const qs = `?lang=${lang}${redirect ? `&redirect=${encodeURIComponent(redirect)}` : ""}`;
  const cls = buttonClasses({ variant: "secondary", size: "lg", fullWidth: true });
  return (
    <div className="mb-5">
      <div className="space-y-3">
        {providers.google && (
          <a href={`${API_BASE_URL}/auth/google/start${qs}`} className={cls}>
            <GoogleMark />
            <span>{t("auth.continueWithGoogle")}</span>
          </a>
        )}
        {providers.apple && (
          <a href={`${API_BASE_URL}/auth/apple/start${qs}`} className={cls}>
            <AppleMark />
            <span>{t("auth.continueWithApple")}</span>
          </a>
        )}
      </div>
      <div className="mt-5 flex items-center gap-3 text-xs font-semibold uppercase text-slate-600" role="separator">
        <span className="h-px flex-1 bg-slate-200" />
        <span>{t("auth.orDivider")}</span>
        <span className="h-px flex-1 bg-slate-200" />
      </div>
    </div>
  );
}
