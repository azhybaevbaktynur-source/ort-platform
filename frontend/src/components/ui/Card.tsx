import React from "react";
import { cn } from "./utils";

export interface CardProps extends Omit<React.HTMLAttributes<HTMLElement>, "title"> {
  /** Section title (rendered as h2 unless `headingLevel` says otherwise). */
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** Buttons or links at the top right (they wrap under the title on phones). */
  actions?: React.ReactNode;
  headingLevel?: 2 | 3 | 4;
  /** `none` for cards whose content brings its own padding (for example a table). */
  padding?: "none" | "md";
  as?: "div" | "section" | "article" | "li";
}

/** White surface with the standard border, radius and padding (16 px phone, 24 px desktop). */
export function Card({ title, description, actions, headingLevel = 2, padding = "md", as: Tag = "section", className, children, ...rest }: CardProps) {
  const H = `h${headingLevel}` as "h2" | "h3" | "h4";
  const hasHeader = title || description || actions;
  return (
    <Tag className={cn("rounded-2xl border border-slate-200 bg-white shadow-sm", padding === "md" && "p-4 sm:p-6", className)} {...rest}>
      {hasHeader && (
        <div className={cn("flex flex-wrap items-start justify-between gap-x-4 gap-y-2", padding === "none" && "px-4 pt-4 sm:px-6 sm:pt-6", children ? "mb-4" : "")}>
          <div className="min-w-0 flex-1 basis-56">
            {title && <H className="text-lg font-semibold leading-7 text-slate-900">{title}</H>}
            {description && <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </Tag>
  );
}
