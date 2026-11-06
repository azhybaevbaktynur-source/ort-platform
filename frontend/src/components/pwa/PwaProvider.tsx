"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { RefreshCw, Share, SquarePlus, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { IconButton } from "@/components/ui/IconButton";

/*
 * S5 installable app (docs/ROADMAP_EXAM_PREP.md):
 * - registers the service worker (/service-worker.js -> public/sw.js) in production builds only, after the page loaded;
 * - a waiting new version shows a small "New version: update" toast; tapping it activates the worker and reloads this
 *   tab only. Never shown on exam routes (lobby, player, result, practice), so nothing reloads during an exam;
 * - "Install the app" for the account menu: Chrome's saved `beforeinstallprompt` (app/layout.tsx), or on iOS a sheet
 *   with the Share -> Add to Home Screen steps. Hidden in the installed app and for 14 days after a dismissal.
 */

type InstallKind = "prompt" | "ios" | null;

interface PwaContextValue {
  /** What "Install the app" does here, or null when the entry is hidden. */
  installKind: InstallKind;
  install: () => void;
  /** Student UI U8: this device runs the installed app, or installed it from this browser (remembered). */
  installed: boolean;
}

const PwaContext = createContext<PwaContextValue>({ installKind: null, install: () => undefined, installed: false });
export const usePwa = () => useContext(PwaContext);

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}
declare global {
  interface Window { __pwaInstallPrompt?: InstallPromptEvent | null }
}

const SW_URL = "/service-worker.js";
const DISMISS_KEY = "pwa_install_dismissed_at";
const DISMISS_MS = 14 * 24 * 60 * 60 * 1000;
const INSTALLED_KEY = "pwa_installed"; // Student UI U8: the getting-started checklist
const UPDATE_CHECK_MS = 30 * 60 * 1000;

/** Exam routes: the assessment lobby, the player, attempt results and practice. No update toast there. */
const EXAM_ROUTE = /^\/[^/]+\/courses\/[^/]+\/(?:attempts|assessments|practice)(?:\/|$)/;
export const isExamRoute = (pathname: string | null) => !!pathname && EXAM_ROUTE.test(pathname);

function recentlyDismissed(): boolean {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY) || 0);
    return at > 0 && Date.now() - at < DISMISS_MS;
  } catch {
    return false;
  }
}

function rememberDismissal() {
  try {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
  } catch {
    /* private mode: the entry simply comes back */
  }
}

function isStandalone(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

function isIos(): boolean {
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export function PwaProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [installKind, setInstallKind] = useState<InstallKind>(null);
  const [installed, setInstalled] = useState(false);
  const [iosOpen, setIosOpen] = useState(false);
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);
  const [updateHidden, setUpdateHidden] = useState(false);
  const reloading = useRef(false);

  // ---- service worker: register, watch for a waiting new version
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    const sw = navigator.serviceWorker;
    let reg: ServiceWorkerRegistration | null = null;
    let lastCheck = Date.now();
    const offer = (w: ServiceWorker | null) => { if (w && sw.controller) setWaiting(w); };
    const track = (w: ServiceWorker | null) => {
      w?.addEventListener("statechange", () => {
        if (w.state === "installed") offer(w);
        else if (w.state === "redundant") setWaiting(reg?.waiting && sw.controller ? reg.waiting : null); // replaced by a newer one
      });
    };
    const onControllerChange = () => {
      // Only the tab where the person tapped "Update" reloads; other tabs (maybe in an exam) keep running.
      if (reloading.current) window.location.reload();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible" && reg && Date.now() - lastCheck > UPDATE_CHECK_MS) {
        lastCheck = Date.now();
        reg.update().catch(() => undefined);
      }
    };
    const start = () => {
      sw.register(SW_URL, { scope: "/", updateViaCache: "none" }).then((r) => {
        reg = r;
        offer(r.waiting);
        track(r.installing);
        r.addEventListener("updatefound", () => track(r.installing));
      }).catch(() => undefined);
    };
    sw.addEventListener("controllerchange", onControllerChange);
    document.addEventListener("visibilitychange", onVisible);
    if (document.readyState === "complete") start();
    else window.addEventListener("load", start, { once: true });
    return () => {
      sw.removeEventListener("controllerchange", onControllerChange);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("load", start);
    };
  }, []);

  // ---- install entry
  useEffect(() => {
    const remember = () => {
      try { localStorage.setItem(INSTALLED_KEY, "1"); } catch { /* private mode: only this session knows */ }
      setInstalled(true);
    };
    const refresh = () => {
      if (isStandalone()) remember();
      else {
        try { if (localStorage.getItem(INSTALLED_KEY) === "1") setInstalled(true); } catch { /* storage blocked */ }
      }
      if (isStandalone() || recentlyDismissed()) setInstallKind(null);
      else if (window.__pwaInstallPrompt) setInstallKind("prompt");
      else setInstallKind(isIos() ? "ios" : null);
    };
    const onInstalled = () => { window.__pwaInstallPrompt = null; remember(); refresh(); };
    refresh();
    window.addEventListener("pwa-install-available", refresh);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("pwa-install-available", refresh);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const install = useCallback(() => {
    const prompt = window.__pwaInstallPrompt;
    if (prompt) {
      window.__pwaInstallPrompt = null; // one use only
      setInstallKind(null);
      prompt.prompt().then(() => prompt.userChoice).then((choice) => {
        if (choice.outcome === "dismissed") rememberDismissal();
      }).catch(() => undefined);
    } else if (installKind === "ios") {
      setIosOpen(true);
    }
  }, [installKind]);

  const closeIos = () => {
    setIosOpen(false);
    rememberDismissal();
    setInstallKind(null);
  };

  const update = () => {
    if (!waiting) return;
    reloading.current = true;
    waiting.postMessage({ type: "SKIP_WAITING" });
  };

  return (
    <PwaContext.Provider value={{ installKind, install, installed }}>
      {children}
      {waiting && !updateHidden && !isExamRoute(pathname) && (
        <UpdateToast onUpdate={update} onHide={() => setUpdateHidden(true)} />
      )}
      {installKind === "ios" && <IosInstallSheet open={iosOpen} onClose={closeIos} />}
    </PwaContext.Provider>
  );
}

function UpdateToast({ onUpdate, onHide }: { onUpdate: () => void; onHide: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="status" data-testid="pwa-update"
      className="fixed inset-x-4 bottom-4 z-[60] flex items-center gap-2 rounded-2xl border border-slate-200 bg-white py-2 pl-4 pr-2 shadow-lg sm:inset-x-auto sm:bottom-5 sm:left-5 sm:max-w-sm">
      <RefreshCw aria-hidden="true" className="h-5 w-5 shrink-0 text-brand-700" />
      <p className="min-w-0 flex-1 text-sm font-medium leading-5 text-slate-900">{t("pwa.update.message")}</p>
      <Button size="sm" onClick={onUpdate}>{t("pwa.update.action")}</Button>
      <IconButton aria-label={t("pwa.update.dismiss")} icon={<X className="h-5 w-5" />} onClick={onHide} />
    </div>
  );
}

function IosInstallSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const steps: { icon?: React.ReactNode; key: string }[] = [
    { key: "pwa.install.iosStep1", icon: <Share className="h-5 w-5" /> },
    { key: "pwa.install.iosStep2", icon: <SquarePlus className="h-5 w-5" /> },
    { key: "pwa.install.iosStep3" },
  ];
  return (
    <Dialog open={open} onClose={onClose} size="sm" title={t("pwa.install.iosTitle")} description={t("pwa.install.iosIntro")}
      footer={<Button onClick={onClose}>{t("pwa.install.iosDone")}</Button>}>
      <ol className="space-y-3">
        {steps.map((s, i) => (
          <li key={s.key} className="flex items-start gap-3">
            <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-50 text-sm font-semibold text-brand-800">{i + 1}</span>
            <span className="min-w-0 flex-1 pt-0.5 text-slate-800">{t(s.key)}</span>
            {s.icon && <span aria-hidden="true" className="shrink-0 pt-0.5 text-brand-700">{s.icon}</span>}
          </li>
        ))}
      </ol>
    </Dialog>
  );
}
