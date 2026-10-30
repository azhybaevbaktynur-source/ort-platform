"use client";

// Phase 8c S2 (PHASE_8C_DESIGN §3.3, §3.6, §10): the Course page menus: the per-row "⋯" menu (icon-only trigger with a
// text name) and the grouped "+ Add" menu. A popover from `sm`; on phones a bottom sheet with group headings over a
// backdrop. Same keyboard model as `MenuButton`: arrows / Home / End move, Enter or Space picks, Esc and a click
// outside close and return focus to the trigger.
import React, { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Ellipsis } from "lucide-react";
import { Button, type ButtonVariant, type MenuItem, cn, focusRing } from "@/components/ui";

export interface MenuGroup {
  id: string;
  /** Group heading (shown above its items); omit for an ungrouped list. */
  heading?: string;
  items: (MenuItem & { icon?: React.ReactNode })[];
}

export interface OutlineMenuProps {
  /** Accessible name of the trigger (and of the menu). */
  label: string;
  groups: MenuGroup[];
  onSelect: (id: string) => void;
  /** `icon`: a 44 px "⋯" button; `button`: a labelled button with a chevron. */
  trigger?: "icon" | "button";
  /** Visible text of a `button` trigger (default: `label`). */
  text?: React.ReactNode;
  leftIcon?: React.ReactNode;
  variant?: ButtonVariant;
  fullWidth?: boolean;
  disabled?: boolean;
  /** Heading of the phone sheet (default: `label`). */
  sheetTitle?: string;
  className?: string;
}

export function OutlineMenu({
  label, groups, onSelect, trigger = "icon", text, leftIcon, variant = "secondary", fullWidth, disabled, sheetTitle, className,
}: OutlineMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const uid = useId().replace(/:/g, "");
  const buttonId = `om${uid}`;
  const menuId = `om${uid}-menu`;
  const flat = groups.flatMap((g) => g.items);
  const enabled = flat.map((it, i) => (it.disabled ? -1 : i)).filter((i) => i >= 0);

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

  const triggerProps = {
    id: buttonId,
    "aria-haspopup": "menu" as const,
    "aria-expanded": open,
    "aria-controls": open ? menuId : undefined,
    disabled,
    onClick: () => setOpen((o) => !o),
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "ArrowDown" && !open) { e.preventDefault(); setOpen(true); } },
  };

  let index = -1;
  return (
    <div ref={rootRef} className={cn("relative", fullWidth && "w-full", className)}>
      {trigger === "icon" ? (
        <button ref={buttonRef} type="button" aria-label={label} title={label} {...triggerProps}
          className={cn(
            "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-700 transition-colors hover:bg-slate-100 hover:text-slate-900",
            "disabled:cursor-not-allowed disabled:opacity-60", focusRing,
          )}>
          <Ellipsis aria-hidden="true" className="h-5 w-5" />
        </button>
      ) : (
        <Button ref={buttonRef} variant={variant} size="sm" leftIcon={leftIcon} fullWidth={fullWidth} {...triggerProps}
          rightIcon={<ChevronDown aria-hidden="true" className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />}>
          {text ?? label}
        </Button>
      )}
      {open && (
        <>
          {/* phones: the menu is a bottom sheet over a backdrop (a click on it closes the menu) */}
          <div aria-hidden="true" className="fixed inset-0 z-40 bg-slate-900/40 sm:hidden" onClick={() => setOpen(false)} />
          <div id={menuId} role="menu" aria-labelledby={buttonId} onKeyDown={onMenuKey}
            className={cn(
              "fixed inset-x-0 bottom-0 z-50 max-h-[80vh] overflow-y-auto rounded-t-2xl border border-slate-200 bg-white p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-lg",
              "sm:absolute sm:inset-x-auto sm:bottom-auto sm:z-30 sm:mt-2 sm:w-72 sm:max-h-[70vh] sm:rounded-xl sm:p-1",
              "sm:right-0",
            )}>
            <p aria-hidden="true" className="px-3 pb-1 pt-2 text-base font-semibold text-slate-900 sm:hidden">{sheetTitle ?? label}</p>
            {groups.map((g) => {
              const headingId = `${menuId}-${g.id}`;
              const body = g.items.map((it) => {
                index += 1;
                const i = index;
                return (
                  <button key={it.id} ref={(el) => { itemRefs.current[i] = el; }} type="button" role="menuitem" tabIndex={-1}
                    disabled={it.disabled}
                    onClick={() => { close(false); onSelect(it.id); }}
                    className={cn(
                      "flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-base leading-6 text-slate-800 hover:bg-slate-100 focus:bg-slate-100 sm:text-sm",
                      "disabled:cursor-not-allowed disabled:opacity-50", focusRing, "focus-visible:ring-offset-0",
                    )}>
                    {it.icon && <span aria-hidden="true" className="inline-flex shrink-0 text-slate-500 [&>svg]:h-5 [&>svg]:w-5">{it.icon}</span>}
                    <span className="min-w-0">
                      <span className="block font-medium">{it.label}</span>
                      {it.description && <span className="block text-sm leading-5 text-slate-600">{it.description}</span>}
                    </span>
                  </button>
                );
              });
              return g.heading ? (
                <div key={g.id} role="group" aria-labelledby={headingId} className="py-1 [&+&]:border-t [&+&]:border-slate-100">
                  <p id={headingId} className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-slate-600">{g.heading}</p>
                  {body}
                </div>
              ) : <React.Fragment key={g.id}>{body}</React.Fragment>;
            })}
          </div>
        </>
      )}
    </div>
  );
}
