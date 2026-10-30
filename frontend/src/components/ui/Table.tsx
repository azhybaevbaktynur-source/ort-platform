"use client";

import React, { useId } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Pagination, type PaginationProps } from "./Pagination";
import { Skeleton } from "./Skeleton";
import { cn, fieldBase, focusRing } from "./utils";

export type SortDirection = "asc" | "desc";

export interface TableSort {
  key: string;
  direction: SortDirection;
}

export interface TableColumn<T> {
  /** Stable id of the column; also the sort key sent to `onSortChange`. */
  key: string;
  /** Header content. */
  header: React.ReactNode;
  /** Plain-text label for stacked cards and the phone sort menu, when `header` is not a string. */
  label?: string;
  /** Cell content for one row. */
  cell: (row: T, index: number) => React.ReactNode;
  sortable?: boolean;
  align?: "left" | "right" | "center";
  /** The row's name: rendered as the row header (`<th scope="row">`) and as the card title on phones. One per table. */
  primary?: boolean;
  /** Order in the stacked cards (lower first, key columns first). Default: column order. */
  mobilePriority?: number;
  /** Leave this column out of the stacked cards (keep only 2-3 key values on phones). */
  hideOnMobile?: boolean;
  /** Leave this row's value out of its stacked card (an empty value: no "Label —" line on phones). */
  hideInCard?: (row: T) => boolean;
  /** Row actions (buttons/links): no label in the cards, shown at the bottom of each card. */
  actions?: boolean;
  /** Keep the cell on one line on desktop (dates, numbers). */
  nowrap?: boolean;
  className?: string;
  headerClassName?: string;
}

export interface TableProps<T> {
  /** Accessible name of the table (visually hidden unless `showCaption`). */
  caption: string;
  showCaption?: boolean;
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Current sort (controlled). The server sorts; the table only shows and changes the state. */
  sort?: TableSort | null;
  onSortChange?: (sort: TableSort) => void;
  /** Total number of items for the count line ("124 results"). */
  count?: number;
  /** Own count text ("124 questions"); overrides `count`. */
  countText?: string;
  /** Slot above the table for a search field or a `FilterBar`. */
  search?: React.ReactNode;
  /** Slot next to the count line (bulk actions, "Export"). */
  toolbar?: React.ReactNode;
  /** First page is loading: skeleton rows in the table's shape. */
  loading?: boolean;
  /** Shown instead of the rows when the list failed (usually an `ErrorState`). */
  error?: React.ReactNode;
  /** Shown when there are no rows (usually an `EmptyState` with `variant="plain"`). */
  empty?: React.ReactNode;
  /** Cursor pagination under the table. */
  pagination?: PaginationProps;
  /** Under 640 px: `cards` (default) turns each row into a card; `scroll` keeps the table and scrolls it inside its box. */
  mobile?: "cards" | "scroll";
  rowClassName?: (row: T) => string | undefined;
  className?: string;
}

const ALIGN = { left: "text-left", right: "text-right", center: "text-center" } as const;

function plainLabel<T>(c: TableColumn<T>): string {
  return c.label ?? (typeof c.header === "string" ? c.header : c.key);
}

/**
 * Data table with a count line, search slot, sortable headers, cursor pagination and a
 * stacked-card layout on phones (each row becomes a card with label/value pairs, key columns first).
 */
export function Table<T>({
  caption, showCaption = false, columns, rows, rowKey, sort, onSortChange, count, countText, search, toolbar,
  loading = false, error, empty, pagination, mobile = "cards", rowClassName, className,
}: TableProps<T>) {
  const { t } = useTranslation();
  const sortId = useId();
  const countLine = countText ?? (count !== undefined ? t("ui.table.count", { count }) : null);
  const sortable = columns.filter((c) => c.sortable);
  const cards = mobile === "cards";

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    const direction: SortDirection = sort?.key === key && sort.direction === "asc" ? "desc" : "asc";
    onSortChange({ key, direction });
  };

  const header = (search || toolbar || countLine) && (
    <div className="mb-3 space-y-3">
      {search}
      {(countLine || toolbar) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {countLine ? <p className="text-sm font-medium text-slate-700" aria-live="polite">{countLine}</p> : <span />}
          {toolbar && <div className="flex flex-wrap items-center gap-2">{toolbar}</div>}
        </div>
      )}
    </div>
  );

  let body: React.ReactNode;
  if (error) {
    body = error;
  } else if (loading && rows.length === 0) {
    body = (
      <div role="status" className="rounded-2xl border border-slate-200 bg-white p-4">
        <span className="sr-only">{t("ui.loading")}</span>
        <div aria-hidden="true" className="space-y-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="flex gap-4">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-5 flex-1" />
              <Skeleton className="hidden h-5 w-1/5 sm:block" />
            </div>
          ))}
        </div>
      </div>
    );
  } else if (rows.length === 0) {
    body = empty ?? <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">{t("ui.table.empty")}</p>;
  } else {
    const primary = columns.find((c) => c.primary);
    const cardColumns = columns
      .map((c, i) => ({ c, i }))
      .filter(({ c }) => !c.primary && !c.actions && !c.hideOnMobile)
      .sort((a, b) => (a.c.mobilePriority ?? a.i) - (b.c.mobilePriority ?? b.i))
      .map(({ c }) => c);
    const actionColumns = columns.filter((c) => c.actions);

    body = (
      <>
        {cards && sortable.length > 0 && onSortChange && (
          <div className="mb-3 sm:hidden">
            <label htmlFor={sortId} className="block text-sm font-medium leading-6 text-slate-800">{t("ui.table.sortBy")}</label>
            <div className="relative mt-1">
              <select
                id={sortId}
                value={sort ? `${sort.key}:${sort.direction}` : ""}
                onChange={(e) => {
                  const [key, direction] = e.target.value.split(":");
                  if (key) onSortChange({ key, direction: direction as SortDirection });
                }}
                className={cn(fieldBase, "min-h-11 appearance-none border-slate-300 py-2 pr-10")}
              >
                {!sort && <option value="">{t("ui.table.notSorted")}</option>}
                {sortable.flatMap((c) => [
                  <option key={`${c.key}:asc`} value={`${c.key}:asc`}>{t("ui.table.sortOptionAsc", { column: plainLabel(c) })}</option>,
                  <option key={`${c.key}:desc`} value={`${c.key}:desc`}>{t("ui.table.sortOptionDesc", { column: plainLabel(c) })}</option>,
                ])}
              </select>
              <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
            </div>
          </div>
        )}

        {cards && (
          <ul aria-label={caption} className="space-y-3 sm:hidden">
            {rows.map((row, ri) => {
              // Phase 9 UX: no empty action row on a card whose action cells are all empty (a revoked invitation)
              const actionCells = actionColumns.map((c) => ({ c, node: c.cell(row, ri) }))
                .filter(({ node }) => node !== null && node !== undefined && node !== false);
              return (
              <li key={rowKey(row)} className={cn("rounded-2xl border border-slate-200 bg-white p-4 shadow-sm", rowClassName?.(row))}>
                {primary && <div className="break-words text-base font-semibold leading-6 text-slate-900">{primary.cell(row, ri)}</div>}
                {cardColumns.some((c) => !c.hideInCard?.(row)) && (
                  <dl className={cn("space-y-1.5", primary && "mt-2")}>
                    {cardColumns.filter((c) => !c.hideInCard?.(row)).map((c) => (
                      <div key={c.key} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                        <dt className="text-sm leading-6 text-slate-600">{plainLabel(c)}</dt>
                        <dd className="min-w-0 break-words text-right text-sm leading-6 text-slate-900">{c.cell(row, ri)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {actionCells.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                    {actionCells.map(({ c, node }) => <React.Fragment key={c.key}>{node}</React.Fragment>)}
                  </div>
                )}
              </li>
              );
            })}
          </ul>
        )}

        <div className={cn("overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm", cards && "hidden sm:block")}>
          <table className="w-full border-collapse text-left text-sm">
            <caption className={showCaption ? "px-4 py-3 text-left text-base font-semibold text-slate-900" : "sr-only"}>{caption}</caption>
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                {columns.map((c) => {
                  const active = sort?.key === c.key;
                  const ariaSort = active ? (sort!.direction === "asc" ? "ascending" : "descending") : undefined;
                  const Icon = active ? (sort!.direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
                  return (
                    <th key={c.key} scope="col" aria-sort={ariaSort}
                      className={cn("px-4 py-3 font-semibold leading-5 text-slate-700", ALIGN[c.align ?? "left"], c.headerClassName)}>
                      {c.actions && !c.header ? <span className="sr-only">{t("ui.table.actions")}</span>
                        : c.sortable && onSortChange ? (
                          <button type="button" onClick={() => toggleSort(c.key)}
                            className={cn("-mx-2 inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2 font-semibold hover:bg-slate-200/60 hover:text-slate-900", active && "text-slate-900", focusRing)}>
                            {c.header}
                            <Icon aria-hidden="true" className={cn("h-4 w-4 shrink-0", active ? "text-brand-700" : "text-slate-500")} />
                          </button>
                        ) : c.header}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((row, ri) => (
                <tr key={rowKey(row)} className={cn("hover:bg-slate-50/60", rowClassName?.(row))}>
                  {columns.map((c) => {
                    const cls = cn("px-4 py-3 align-middle leading-6 text-slate-800", ALIGN[c.align ?? "left"], c.nowrap && "whitespace-nowrap", c.actions && "whitespace-nowrap", c.className);
                    return c.primary
                      ? <th key={c.key} scope="row" className={cn(cls, "font-medium text-slate-900")}>{c.cell(row, ri)}</th>
                      : <td key={c.key} className={cls}>{c.cell(row, ri)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  return (
    <div className={className}>
      {header}
      {body}
      {pagination && !error && <Pagination {...pagination} />}
    </div>
  );
}
