"use client";

import React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { cn, focusRing } from "./utils";

export interface Breadcrumb {
  label: React.ReactNode;
  /** Omit for the current page (the last crumb). */
  href?: string;
}

export interface PageHeaderProps {
  /** Page title (the one `<h1>`). */
  title: React.ReactNode;
  /** One line under the title (what this page is for). */
  description?: React.ReactNode;
  /** Status badge(s) next to the title, e.g. `<Badge tone="success">Published</Badge>`. */
  badge?: React.ReactNode;
  /** Where you are (area → section → page). The last crumb is the current page. */
  breadcrumbs?: Breadcrumb[];
  /** The ONE primary action of the page (a `Button` or `LinkButton` with variant="primary"). */
  primaryAction?: React.ReactNode;
  /** Secondary actions (secondary buttons / links). They come before the primary on desktop and after it on phones. */
  secondaryActions?: React.ReactNode;
  /** Extra content under the header row (meta line, tabs). */
  children?: React.ReactNode;
  className?: string;
}

/** Page title block: breadcrumbs, title + badge, description and actions; wraps on phones. */
export function PageHeader({ title, description, badge, breadcrumbs, primaryAction, secondaryActions, children, className }: PageHeaderProps) {
  const { t } = useTranslation();
  const hasActions = primaryAction || secondaryActions;
  return (
    <header className={cn("mb-6", className)}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label={t("ui.breadcrumbs")} className="mb-2">
          <ol className="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-sm leading-6 text-slate-600">
            {breadcrumbs.map((b, i) => {
              const last = i === breadcrumbs.length - 1;
              return (
                <li key={i} className="inline-flex min-w-0 items-center gap-1">
                  {b.href && !last ? (
                    <Link href={b.href} className={cn("inline-flex min-h-11 items-center break-words rounded font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>{b.label}</Link>
                  ) : (
                    <span aria-current={last ? "page" : undefined} className="break-words">{b.label}</span>
                  )}
                  {!last && <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" />}
                </li>
              );
            })}
          </ol>
        </nav>
      )}
      <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 sm:min-w-[16rem]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="min-w-0 break-words text-2xl font-bold leading-8 text-slate-900">{title}</h1>
            {badge}
          </div>
          {description && <p className="mt-1 max-w-3xl text-base leading-6 text-slate-600 sm:text-sm sm:leading-6">{description}</p>}
        </div>
        {hasActions && (
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end [&>*]:w-full sm:[&>*]:w-auto">
            {secondaryActions && <div className="flex flex-wrap gap-2 [&>*]:flex-1 sm:[&>*]:flex-none">{secondaryActions}</div>}
            {primaryAction}
          </div>
        )}
      </div>
      {children}
    </header>
  );
}
