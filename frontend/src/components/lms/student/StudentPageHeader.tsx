import React from "react";
import { cn } from "@/components/ui/utils";

/*
 * Student UI coherence (STUDENT_UI_DESIGN §5.1 d): the one header of every student page (Тесты, Аналитика,
 * Видеоуроки, Практика, Открыть доступ; the home's greeting band follows the same layout): the title, a small
 * subtitle (the course, or one line about the page) and at most one action on the right. The page's primary button is
 * never here unless it is the page's only one (§5.1 e).
 */
export interface StudentPageHeaderProps {
  title: React.ReactNode;
  /** Small line under the title: the course name, or one line about the page. */
  subtitle?: React.ReactNode;
  /** At most one control on the right (for example the analytics period). */
  action?: React.ReactNode;
  /** id of the `<h1>` (for `aria-labelledby`). */
  id?: string;
  className?: string;
}

export const STUDENT_TITLE = "break-words text-2xl font-bold leading-8 text-slate-900 lg:text-[28px] lg:leading-9";
export const STUDENT_SUBTITLE = "mt-1 break-words text-sm leading-5 text-slate-600";

export function StudentPageHeader({ title, subtitle, action, id, className }: StudentPageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4", className)}>
      <div className="min-w-0">
        <h1 id={id} className={STUDENT_TITLE}>{title}</h1>
        {subtitle ? <p className={STUDENT_SUBTITLE}>{subtitle}</p> : null}
      </div>
      {action ? <div className="min-w-0 shrink-0">{action}</div> : null}
    </header>
  );
}
