"use client";

import React from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button } from "./Button";
import { cn } from "./utils";

export interface ErrorStateProps {
  /** What happened. Defaults to `ui.error.title`. */
  title?: React.ReactNode;
  /** What to do. Defaults to `ui.error.body`. */
  message?: React.ReactNode;
  /** Shows a Retry button when retrying can help. */
  onRetry?: () => void;
  /** Retry in progress (spinner on the button). */
  retrying?: boolean;
  /** Extra action next to Retry (for example a link back). */
  action?: React.ReactNode;
  /** `inline` is a compact banner for a part of a page; `page` is a centered block. */
  variant?: "page" | "inline";
  className?: string;
}

export function ErrorState({ title, message, onRetry, retrying = false, action, variant = "page", className }: ErrorStateProps) {
  const { t } = useTranslation();
  const heading = title ?? t("ui.error.title");
  const body = message ?? t("ui.error.body");
  const retry = onRetry && (
    <Button variant="secondary" size={variant === "inline" ? "sm" : "md"} loading={retrying} onClick={onRetry} leftIcon={<RefreshCw aria-hidden="true" className="h-4 w-4" />}>
      {t("ui.retry")}
    </Button>
  );
  if (variant === "inline") {
    return (
      <div role="alert" className={cn("flex gap-3 rounded-xl border border-danger-200 bg-danger-50 p-4", className)}>
        <TriangleAlert aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-danger-700" />
        <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold leading-6 text-danger-800">{heading}</p>
            <p className="text-sm leading-6 text-danger-800">{body}</p>
          </div>
          {(retry || action) && <div className="flex flex-wrap gap-2">{retry}{action}</div>}
        </div>
      </div>
    );
  }
  return (
    <div role="alert" className={cn("flex flex-col items-center rounded-2xl border border-slate-200 bg-white px-4 py-10 text-center", className)}>
      <span aria-hidden="true" className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-danger-50 text-danger-700">
        <TriangleAlert className="h-6 w-6" />
      </span>
      <p className="max-w-md text-base font-semibold leading-6 text-slate-900">{heading}</p>
      <p className="mt-1 max-w-md text-sm leading-6 text-slate-600">{body}</p>
      {(retry || action) && <div className="mt-4 flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">{retry}{action}</div>}
    </div>
  );
}
