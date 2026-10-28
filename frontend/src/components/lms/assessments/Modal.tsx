"use client";

import React from "react";
import { Dialog } from "@/components/ui";

const PHONE_FULL = "max-sm:m-0 max-sm:h-[100dvh] max-sm:max-h-[100dvh] max-sm:w-full max-sm:max-w-full max-sm:rounded-none";

/**
 * Modal used by the builder and gradebook dialogs. Phase 6b S5c: one consistent dialog: this is now the
 * design-system `Dialog` (native <dialog>, focus trap, Esc, focus return, scrolls inside, no overlay gap: UX T18).
 * The API is unchanged; callers keep their own buttons in `children`.
 */
export function Modal({
  open, title, onClose, busy = false, wide = false, fullScreenOnPhone = false, children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  busy?: boolean;
  wide?: boolean;
  /** Phase 7c S5 (opt-in): below `sm` the dialog fills the screen (the quiz editor's "Find questions"). */
  fullScreenOnPhone?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Dialog open={open} title={title} onClose={onClose} busy={busy} size={wide ? "lg" : "md"} closeOnBackdrop={false}
      className={fullScreenOnPhone ? PHONE_FULL : undefined}>
      {children}
    </Dialog>
  );
}
