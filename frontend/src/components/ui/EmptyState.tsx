import React from "react";
import { Inbox } from "lucide-react";
import { cn } from "./utils";

export interface EmptyStateProps {
  /** What this place is for ("No courses yet."). */
  title: React.ReactNode;
  /** The next step ("Join a course with a code from your teacher."). */
  description?: React.ReactNode;
  /** One button or link that takes the next step. */
  action?: React.ReactNode;
  icon?: React.ReactNode;
  /** `plain` drops the dashed border (inside a Card or Table). */
  variant?: "bordered" | "plain";
  className?: string;
}

export function EmptyState({ title, description, action, icon, variant = "bordered", className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center px-4 py-10 text-center", variant === "bordered" && "rounded-2xl border border-dashed border-slate-300 bg-white", className)}>
      <span aria-hidden="true" className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600 [&>svg]:h-6 [&>svg]:w-6">
        {icon ?? <Inbox />}
      </span>
      <p className="max-w-md text-base font-semibold leading-6 text-slate-900">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm leading-6 text-slate-600">{description}</p>}
      {action && <div className="mt-4 flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">{action}</div>}
    </div>
  );
}
