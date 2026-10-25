"use client";

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { CircleAlert, CircleCheck, Info, LoaderCircle, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cn, focusRing } from "./utils";

/*
 * Toasts: short, non-blocking messages in a polite live region.
 * API kept from Phase 1 (callers use `toast.success(...)` or `useToast()`); Phase 6b S5a
 * restyled it (contrast, 44 px close button with a label, phone layout).
 */

export type ToastType = "success" | "error" | "info" | "loading";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType, title?: string, duration?: number) => string;
  dismissToast: (id: string) => void;
  toast: {
    success: (message: string, title?: string) => string;
    error: (message: string, title?: string) => string;
    info: (message: string, title?: string) => string;
    loading: (message: string, title?: string) => string;
    dismiss: (id: string) => void;
  };
}

const ToastContext = createContext<ToastContextValue | null>(null);

// Global fallback emitter so toast can be called anywhere if needed
let globalToastHandler: ((msg: string, type: ToastType, title?: string, duration?: number) => string) | null = null;
let globalDismissHandler: ((id: string) => void) | null = null;

export const toast = {
  success: (message: string, title?: string) => {
    if (globalToastHandler) return globalToastHandler(message, "success", title, 4000);
    return "";
  },
  error: (message: string, title?: string) => {
    if (globalToastHandler) return globalToastHandler(message, "error", title, 6000);
    return "";
  },
  info: (message: string, title?: string) => {
    if (globalToastHandler) return globalToastHandler(message, "info", title, 4000);
    return "";
  },
  loading: (message: string, title?: string) => {
    if (globalToastHandler) return globalToastHandler(message, "loading", title, 0);
    return "";
  },
  dismiss: (id: string) => {
    if (globalDismissHandler) globalDismissHandler(id);
  },
};

const STYLES: Record<ToastType, { box: string; icon: React.ReactNode }> = {
  success: { box: "border-success-200", icon: <CircleCheck className="h-5 w-5 text-success-700" aria-hidden="true" /> },
  error: { box: "border-danger-200", icon: <CircleAlert className="h-5 w-5 text-danger-700" aria-hidden="true" /> },
  info: { box: "border-brand-200", icon: <Info className="h-5 w-5 text-brand-700" aria-hidden="true" /> },
  loading: { box: "border-brand-200", icon: <LoaderCircle className="h-5 w-5 animate-spin text-brand-700" aria-hidden="true" /> },
};

function ToastItem({ item, onDismiss }: { item: ToastMessage; onDismiss: (id: string) => void }) {
  const { t } = useTranslation();
  const s = STYLES[item.type];
  return (
    <div className={cn("pointer-events-auto flex items-start gap-3 rounded-2xl border bg-white py-2 pl-4 pr-1 text-slate-900 shadow-lg", s.box)}>
      <div className="shrink-0 pt-2.5">{s.icon}</div>
      <div className="min-w-0 flex-1 py-2">
        {item.title && <p className="text-sm font-semibold leading-5 text-slate-900">{item.title}</p>}
        <p className="break-words text-sm leading-5 text-slate-700">{item.message}</p>
      </div>
      <button
        type="button"
        onClick={() => onDismiss(item.id)}
        aria-label={t("ui.close")}
        title={t("ui.close")}
        className={cn("inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-600 hover:bg-slate-100 hover:text-slate-900", focusRing)}
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = "info", title?: string, duration = 4000): string => {
      const id = `${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      const newToast: ToastMessage = { id, type, title, message, duration };

      setToasts((prev) => [...prev, newToast]);

      if (duration > 0) {
        setTimeout(() => {
          dismissToast(id);
        }, duration);
      }

      return id;
    },
    [dismissToast]
  );

  useEffect(() => {
    globalToastHandler = (msg, type, title, duration) => showToast(msg, type, title, duration);
    globalDismissHandler = (id) => dismissToast(id);
    return () => {
      globalToastHandler = null;
      globalDismissHandler = null;
    };
  }, [showToast, dismissToast]);

  const value = {
    showToast,
    dismissToast,
    toast: {
      success: (msg: string, title?: string) => showToast(msg, "success", title, 4000),
      error: (msg: string, title?: string) => showToast(msg, "error", title, 6000),
      info: (msg: string, title?: string) => showToast(msg, "info", title, 4000),
      loading: (msg: string, title?: string) => showToast(msg, "loading", title, 0),
      dismiss: dismissToast,
    },
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* Polite live region: bottom of the screen on phones, bottom right on desktop. */}
      <div
        aria-live="polite"
        aria-relevant="additions text"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col gap-2 sm:inset-x-auto sm:bottom-5 sm:right-5 sm:w-full sm:max-w-sm"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} item={t} onDismiss={dismissToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    // Return the global fallback
    return {
      showToast: (msg: string, type?: ToastType, title?: string, duration?: number) => {
        if (globalToastHandler) return globalToastHandler(msg, type || "info", title, duration);
        return "";
      },
      dismissToast: (id: string) => {
        if (globalDismissHandler) globalDismissHandler(id);
      },
      toast,
    };
  }
  return context;
};
