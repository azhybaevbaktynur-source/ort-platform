"use client";

import React, { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { IconButton } from "./IconButton";
import { cn } from "./utils";

export type DialogSize = "sm" | "md" | "lg";

const SIZES: Record<DialogSize, string> = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-md",
  lg: "sm:max-w-2xl",
};

export interface DialogProps {
  open: boolean;
  /** Called on Esc, the close button and (if allowed) a backdrop click. Not called while `busy`. */
  onClose: () => void;
  title: React.ReactNode;
  /** Short text under the title, linked with `aria-describedby`. */
  description?: React.ReactNode;
  children?: React.ReactNode;
  /** Buttons. Laid out `flex-col-reverse` on phones (put the primary LAST: it shows on top) and right-aligned in a row from `sm`. */
  footer?: React.ReactNode;
  size?: DialogSize;
  /** While true the dialog cannot be closed (a request is running). */
  busy?: boolean;
  /** Close on a click outside the panel (default true). */
  closeOnBackdrop?: boolean;
  /** Hide the X button (the footer must then offer a way out). */
  hideCloseButton?: boolean;
  /** Element focused when the dialog opens; default: the first focusable element in the body, else the panel. */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  /** `alertdialog` for confirmations of dangerous or important actions. */
  role?: "dialog" | "alertdialog";
  className?: string;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.getClientRects().length > 0);
}

/**
 * Modal dialog on the native `<dialog>` element (`showModal`): the page behind is inert,
 * Tab is trapped inside, Esc closes, and focus returns to the element that opened it.
 */
export function Dialog({
  open, onClose, title, description, children, footer, size = "md", busy = false, closeOnBackdrop = true,
  hideCloseButton = false, initialFocusRef, role = "dialog", className,
}: DialogProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descId = useId();
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      returnTo.current = document.activeElement as HTMLElement | null;
      el.showModal();
      document.documentElement.style.overflow = "hidden";
      const target = initialFocusRef?.current ?? (bodyRef.current ? focusables(bodyRef.current)[0] : undefined);
      (target ?? el).focus();
    } else if (!open && el.open) {
      el.close();
    }
  }, [open, initialFocusRef]);

  // Restore scroll and focus whenever the dialog closes (or unmounts while open).
  useEffect(() => {
    if (!open) return;
    return () => {
      document.documentElement.style.overflow = "";
      const back = returnTo.current;
      returnTo.current = null;
      if (back && document.contains(back)) setTimeout(() => back.focus(), 0);
    };
  }, [open]);

  const requestClose = () => {
    if (!busyRef.current) onCloseRef.current();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDialogElement>) => {
    if (e.key !== "Tab" || !ref.current) return;
    const items = focusables(ref.current);
    if (items.length === 0) { e.preventDefault(); return; }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === ref.current)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
  };

  return (
    <dialog
      ref={ref}
      role={role === "alertdialog" ? "alertdialog" : undefined}
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      aria-busy={busy || undefined}
      tabIndex={-1}
      onCancel={(e) => { e.preventDefault(); requestClose(); }}
      onKeyDown={onKeyDown}
      onClick={(e) => { if (closeOnBackdrop && e.target === ref.current) requestClose(); }}
      className={cn(
        "m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] overflow-hidden rounded-2xl bg-white p-0 text-slate-900 shadow-xl",
        "backdrop:bg-slate-900/50 focus:outline-none open:flex open:flex-col",
        SIZES[size],
        className,
      )}
    >
      {open && (
        <>
          <div className="flex items-start gap-3 px-5 pt-5 sm:px-6">
            <div className="min-w-0 flex-1 pt-2">
              <h2 id={titleId} className="text-lg font-semibold leading-7 text-slate-900">{title}</h2>
              {description && <div id={descId} className="mt-1 text-sm leading-6 text-slate-600">{description}</div>}
            </div>
            {!hideCloseButton && (
              <IconButton aria-label={t("ui.close")} icon={<X />} onClick={requestClose} disabled={busy} className="-mr-2" />
            )}
          </div>
          <div ref={bodyRef} className="min-h-0 flex-1 overflow-y-auto px-5 pb-5 pt-3 text-base leading-6 sm:px-6 sm:text-sm sm:leading-6">
            {children}
          </div>
          {footer && (
            <div className="flex flex-col-reverse gap-2 border-t border-slate-100 bg-slate-50 px-5 py-4 sm:flex-row sm:justify-end sm:px-6 [&>*]:w-full sm:[&>*]:w-auto">
              {footer}
            </div>
          )}
        </>
      )}
    </dialog>
  );
}
