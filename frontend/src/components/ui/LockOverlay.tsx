import React from "react";
import { Lock } from "lucide-react";
import { cn } from "./utils";

/*
 * Student UI U1 (STUDENT_UI_DESIGN §1, §6): a blurred "unlock" cover over a card's content (locked analytics or
 * lessons). While `locked`, the content underneath is inert and hidden from screen readers; the overlay says what is
 * locked and offers the way to open it (usually a GoldPill). Unlocked, it renders the children unchanged, so moving a
 * card behind the pass later is a one-line change.
 */

export interface LockOverlayProps {
  locked: boolean;
  /** Optional (U9: a test card shows the blur and the icon only; its "Платный" chip says it). */
  title?: React.ReactNode;
  body?: React.ReactNode;
  /** The way to unlock (a GoldPill to /unlock). */
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function LockOverlay({ locked, title, body, action, children, className }: LockOverlayProps) {
  if (!locked) return <>{children}</>;
  return (
    <div className={cn("relative isolate min-h-[12rem] overflow-hidden rounded-card", className)}>
      {/* `inert` keeps keyboard focus out of the covered content */}
      <div aria-hidden="true" inert className="pointer-events-none select-none">{children}</div>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-white/[0.72] p-4 text-center backdrop-blur-[6px]">
        <span aria-hidden="true" className="flex h-11 w-11 items-center justify-center rounded-full bg-navy-800 text-white">
          <Lock className="h-5 w-5" />
        </span>
        {title && <p className="max-w-xs text-base font-semibold leading-6 text-slate-900">{title}</p>}
        {body && <p className="max-w-xs text-sm leading-5 text-slate-700">{body}</p>}
        {action && <div className="mt-1">{action}</div>}
      </div>
    </div>
  );
}
