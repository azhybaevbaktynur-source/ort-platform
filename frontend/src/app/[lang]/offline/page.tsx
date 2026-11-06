"use client";

import React from "react";
import { WifiOff } from "lucide-react";
import { Button, Mascot } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";

/**
 * S5 installable app: what the service worker (public/sw.js) shows instead of a page when there is no network.
 * Static, no data, no links that need the network; "Try again" reloads the address the person asked for.
 */
export default function OfflinePage() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto flex min-h-[80vh] max-w-md flex-col items-center justify-center px-4 py-10 text-center">
      <Mascot pose="thinking" size={112} eager className="mb-3" />
      <h1 className="flex items-center gap-2 text-xl font-bold text-slate-900">
        <WifiOff aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-600" />
        {t("pwa.offline.title")}
      </h1>
      <p className="mt-2 text-sm leading-6 text-slate-600">{t("pwa.offline.body")}</p>
      <Button className="mt-6 w-full sm:w-auto" onClick={() => window.location.reload()}>{t("pwa.offline.retry")}</Button>
    </main>
  );
}
