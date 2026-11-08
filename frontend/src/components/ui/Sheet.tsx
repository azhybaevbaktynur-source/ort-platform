"use client";

import React, { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §2.3): a bottom sheet (the phone "More" menu, the exam switcher, the account) on the
 * native modal <dialog>, like `Dialog`: the page behind is inert, Tab stays inside, Esc and a tap outside close it,
 * focus returns to the button that opened it. From 640 px it is a centred card. `tone="navy"` gives the navy header.
 */

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  /** Pinned below the scrolling body (sign out, primary action): always visible, padded by the safe-area inset. */
  footer?: React.ReactNode;
  /** id of the <dialog> (for `aria-controls` on the button that opens it). */
  id?: string;
  tone?: "navy" | "light";
  className?: string;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.getClientRects().length > 0);
}

export function Sheet({ open, onClose, title, children, footer, id, tone = "light", className }: SheetProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      returnTo.current = document.activeElement as HTMLElement | null;
      el.showModal();
      document.documentElement.style.overflow = "hidden";
      const first = bodyRef.current ? focusables(bodyRef.current)[0] : undefined;
      (first ?? el).focus();
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    return () => {
      document.documentElement.style.overflow = "";
      const back = returnTo.current;
      returnTo.current = null;
      if (back && document.contains(back)) setTimeout(() => back.focus(), 0);
    };
  }, [open]);

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
      id={id}
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
      onCancel={(e) => { e.preventDefault(); onCloseRef.current(); }}
      onKeyDown={onKeyDown}
      onClick={(e) => { if (e.target === ref.current) onCloseRef.current(); }}
      className={cn(
        "max-h-[calc(100vh-3rem)] max-h-[calc(100dvh-3rem)] w-full max-w-full overflow-hidden bg-white p-0 text-slate-900 shadow-lg",
        "mb-0 mt-auto rounded-t-2xl sm:m-auto sm:max-h-[calc(100vh-4rem)] sm:max-h-[calc(100dvh-4rem)] sm:w-[calc(100%-2rem)] sm:max-w-md sm:rounded-2xl",
        "backdrop:bg-slate-900/50 focus:outline-none open:flex open:flex-col",
        className,
      )}
    >
      {open && (
        <>
          <div className={cn("flex items-center gap-3 px-4 py-3", tone === "navy" ? "bg-navy-800 text-white" : "border-b border-slate-100")}>
            <h2 id={titleId} className="min-w-0 flex-1 break-words text-base font-semibold leading-6">{title}</h2>
            <button type="button" aria-label={t("ui.close")} onClick={() => onCloseRef.current()}
              className={cn("inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-control focus-visible:outline-none focus-visible:ring-2",
                tone === "navy" ? "text-white hover:bg-white/10 focus-visible:ring-white" : "text-slate-600 hover:bg-slate-100 focus-visible:ring-brand-600")}>
              <X aria-hidden="true" className="h-5 w-5" />
            </button>
          </div>
          <div ref={bodyRef} className={cn("min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pt-3", footer ? "pb-3" : "pb-[calc(1rem+env(safe-area-inset-bottom))]")}>
            {children}
          </div>
          {footer && <div className="shrink-0 border-t border-slate-100 bg-white px-3 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2">{footer}</div>}
        </>
      )}
    </dialog>
  );
}
