"use client";

import React, { useEffect, useId } from "react";

/** Plain accessible modal used by the builder dialogs. Escape closes unless busy. */
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
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby={id}
        className={`my-8 w-full ${wide ? "max-w-3xl" : "max-w-lg"} rounded-2xl bg-white p-6 shadow-xl`}>
        <h2 id={id} className="mb-3 text-lg font-bold text-slate-900">{title}</h2>
        {children}
      </div>
    </div>
  );
}
