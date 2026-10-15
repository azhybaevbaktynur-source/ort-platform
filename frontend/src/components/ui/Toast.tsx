"use client";

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { CheckCircle2, AlertCircle, Info, X, Loader2 } from "lucide-react";

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
    if (globalToastHandler) return globalToastHandler(message, "error", title, 5000);
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
      error: (msg: string, title?: string) => showToast(msg, "error", title, 5000),
      info: (msg: string, title?: string) => showToast(msg, "info", title, 4000),
      loading: (msg: string, title?: string) => showToast(msg, "loading", title, 0),
      dismiss: dismissToast,
    },
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* Toast Render Portal */}
      <div
        aria-live="polite"
        className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 p-4 rounded-2xl border shadow-lg backdrop-blur-md transition-all duration-300 transform translate-y-0 opacity-100 ${
              t.type === "success"
                ? "bg-white/95 border-emerald-200 text-slate-800 shadow-emerald-500/10"
                : t.type === "error"
                ? "bg-white/95 border-rose-200 text-slate-800 shadow-rose-500/10"
                : t.type === "loading"
                ? "bg-white/95 border-indigo-200 text-slate-800 shadow-indigo-500/10"
                : "bg-white/95 border-slate-200 text-slate-800 shadow-slate-500/10"
            }`}
          >
            <div className="shrink-0 pt-0.5">
              {t.type === "success" && <CheckCircle2 className="w-5 h-5 text-emerald-600" />}
              {t.type === "error" && <AlertCircle className="w-5 h-5 text-rose-600" />}
              {t.type === "loading" && <Loader2 className="w-5 h-5 text-indigo-600 animate-spin" />}
              {t.type === "info" && <Info className="w-5 h-5 text-indigo-600" />}
            </div>

            <div className="flex-1 min-w-0">
              {t.title && <div className="text-xs font-bold text-slate-900 mb-0.5">{t.title}</div>}
              <div className="text-xs text-slate-600 leading-relaxed font-medium">{t.message}</div>
            </div>

            <button
              type="button"
              onClick={() => dismissToast(t.id)}
              className="shrink-0 p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
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

