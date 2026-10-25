"use client";

import React from "react";
import Link from "next/link";
import { Spinner } from "./Spinner";
import { cn, focusRing } from "./utils";

export type ButtonVariant = "primary" | "secondary" | "danger" | "dangerOutline" | "link";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800",
  secondary: "border border-slate-300 bg-white text-slate-800 shadow-sm hover:bg-slate-50 active:bg-slate-100",
  danger: "bg-danger-600 text-white shadow-sm hover:bg-danger-700 active:bg-danger-800",
  // Phase 6b S11b: a destructive action that opens a confirmation (page headers); the filled `danger` is for the confirm button.
  dangerOutline: "border border-danger-300 bg-white text-danger-700 shadow-sm hover:bg-danger-50 active:bg-danger-100",
  link: "text-brand-700 underline-offset-4 hover:text-brand-800 hover:underline",
};

// Every size keeps a 44 px touch target on phones; `sm` shrinks only from the `sm` breakpoint up.
const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-11 px-3 text-sm sm:min-h-9",
  md: "min-h-11 px-4 text-base sm:text-sm",
  lg: "min-h-12 px-5 text-base",
};

export interface ButtonStyleOptions {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  className?: string;
}

/** Class names of a button; use with `next/link` or `<a>` when navigation looks like a button. */
export function buttonClasses({ variant = "primary", size = "md", fullWidth = false, className }: ButtonStyleOptions = {}): string {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-xl text-center font-semibold leading-5 transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-60 aria-disabled:cursor-not-allowed aria-disabled:opacity-60",
    focusRing,
    SIZES[size],
    variant === "link" && "min-h-11 px-1 sm:min-h-0 sm:px-0",
    VARIANTS[variant],
    fullWidth && "w-full",
    className,
  );
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, Omit<ButtonStyleOptions, "className"> {
  /** Shows a spinner, sets `aria-busy` and blocks clicks; the label stays visible. */
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", fullWidth, loading = false, leftIcon, rightIcon, className, disabled, type = "button", children, onClick, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      onClick={loading ? undefined : onClick}
      className={buttonClasses({ variant, size, fullWidth, className })}
      {...rest}
    >
      {loading ? <Spinner /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  );
});

export interface LinkButtonProps extends Omit<React.ComponentProps<typeof Link>, "className">, Omit<ButtonStyleOptions, "className"> {
  className?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

/** A `next/link` that looks like a Button (navigation, not an action). */
export function LinkButton({ variant = "primary", size = "md", fullWidth, className, leftIcon, rightIcon, children, ...rest }: LinkButtonProps) {
  return (
    <Link className={buttonClasses({ variant, size, fullWidth, className })} {...rest}>
      {leftIcon}
      {children}
      {rightIcon}
    </Link>
  );
}
