"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button, type ButtonSize, type ButtonVariant } from "./Button";
import { cn, focusRing } from "./utils";

export interface MenuItem {
  id: string;
  label: React.ReactNode;
  /** One line under the label (what the item does). */
  description?: React.ReactNode;
  disabled?: boolean;
}

export interface MenuButtonProps {
  /** Visible label of the button (also the accessible name of the menu). */
  label: React.ReactNode;
  items: MenuItem[];
  onSelect: (id: string) => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  leftIcon?: React.ReactNode;
  disabled?: boolean;
  /** Menu edge on desktop: `end` opens towards the left (button at the right of a header). */
  align?: "start" | "end";
  className?: string;
}

/**
 * A button that opens a list of choices (`role="menu"`). Arrow keys / Home / End move between items, Enter
 * or Space picks one, Esc and a click outside close the menu and return focus to the button.
 * Phase 6b S11b ("New question" with a question type).
 */
export function MenuButton({ label, items, onSelect, variant = "primary", size = "md", leftIcon, disabled, align = "end", className }: MenuButtonProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const uid = useId().replace(/:/g, "");
  const buttonId = `mb${uid}`;
  const menuId = `mb${uid}-menu`;
  const enabled = items.map((it, i) => (it.disabled ? -1 : i)).filter((i) => i >= 0);

  const focusItem = (i: number | undefined) => { if (i !== undefined) itemRefs.current[i]?.focus(); };
  const close = (returnFocus = true) => {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    focusItem(enabled[0]);
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onMenuKey = (e: React.KeyboardEvent) => {
    const current = itemRefs.current.findIndex((el) => el === document.activeElement);
    const pos = enabled.indexOf(current);
    if (e.key === "ArrowDown") { e.preventDefault(); focusItem(enabled[(pos + 1) % enabled.length]); }
    else if (e.key === "ArrowUp") { e.preventDefault(); focusItem(enabled[(pos - 1 + enabled.length) % enabled.length]); }
    else if (e.key === "Home") { e.preventDefault(); focusItem(enabled[0]); }
    else if (e.key === "End") { e.preventDefault(); focusItem(enabled[enabled.length - 1]); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Tab") setOpen(false);
  };

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <Button ref={buttonRef} id={buttonId} variant={variant} size={size} disabled={disabled} leftIcon={leftIcon} fullWidth
        aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (e.key === "ArrowDown" && !open) { e.preventDefault(); setOpen(true); } }}
        rightIcon={<ChevronDown aria-hidden="true" className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />}>
        {label}
      </Button>
      {open && (
        <div id={menuId} role="menu" aria-labelledby={buttonId} onKeyDown={onMenuKey}
          className={cn(
            "absolute z-30 mt-2 max-h-[70vh] w-full min-w-[16rem] overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg sm:w-72",
            align === "end" ? "right-0" : "left-0",
          )}>
          {items.map((it, i) => (
            <button key={it.id} ref={(el) => { itemRefs.current[i] = el; }} type="button" role="menuitem" tabIndex={-1}
              disabled={it.disabled}
              onClick={() => { close(false); onSelect(it.id); }}
              className={cn(
                "flex min-h-11 w-full flex-col items-start justify-center rounded-lg px-3 py-2 text-left text-base leading-6 text-slate-800 hover:bg-slate-100 focus:bg-slate-100 sm:text-sm",
                "disabled:cursor-not-allowed disabled:opacity-50", focusRing, "focus-visible:ring-offset-0",
              )}>
              <span className="font-medium">{it.label}</span>
              {it.description && <span className="text-sm leading-5 text-slate-600">{it.description}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
