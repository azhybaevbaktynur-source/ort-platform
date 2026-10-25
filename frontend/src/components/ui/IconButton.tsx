"use client";

import React from "react";
import { Spinner } from "./Spinner";
import { cn, focusRing } from "./utils";

export type IconButtonVariant = "ghost" | "secondary" | "danger";

const VARIANTS: Record<IconButtonVariant, string> = {
  ghost: "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
  secondary: "border border-slate-300 bg-white text-slate-700 shadow-sm hover:bg-slate-50",
  danger: "text-danger-700 hover:bg-danger-50",
};

export interface IconButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "aria-label" | "children"> {
  /** Required: an icon-only button needs a text name for screen readers. */
  "aria-label": string;
  icon: React.ReactNode;
  variant?: IconButtonVariant;
  loading?: boolean;
}

/** Square 44 px icon-only button. */
export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon, variant = "ghost", loading = false, className, disabled, type = "button", onClick, title, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      title={title ?? rest["aria-label"]}
      onClick={loading ? undefined : onClick}
      className={cn(
        "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        focusRing,
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="h-5 w-5" /> : <span aria-hidden="true" className="inline-flex [&>svg]:h-5 [&>svg]:w-5">{icon}</span>}
    </button>
  );
});
