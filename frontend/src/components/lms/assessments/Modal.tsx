"use client";

import React from "react";
import { Dialog } from "@/components/ui";

/**
 * Modal used by the builder and gradebook dialogs. Phase 6b S5c: one consistent dialog: this is now the
 * design-system `Dialog` (native <dialog>, focus trap, Esc, focus return, scrolls inside, no overlay gap: UX T18).
 * The API is unchanged; callers keep their own buttons in `children`.
 */
export function Modal({
  open, title, onClose, busy = false, wide = false, children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  busy?: boolean;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Dialog open={open} title={title} onClose={onClose} busy={busy} size={wide ? "lg" : "md"} closeOnBackdrop={false}>
      {children}
    </Dialog>
  );
}
