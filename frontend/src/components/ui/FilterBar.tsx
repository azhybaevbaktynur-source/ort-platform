"use client";

import React from "react";
import { Search, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button } from "./Button";
import { Input } from "./Input";
import { cn, focusRing } from "./utils";

export interface SearchInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "size"> {
  value: string;
  onChange: (value: string) => void;
  /** Visible label; defaults to "Search". */
  label?: string;
  hint?: string;
  containerClassName?: string;
}

/** Search field with a visible label, a search icon and a clear button. */
export function SearchInput({ value, onChange, label, hint, containerClassName, ...rest }: SearchInputProps) {
  const { t } = useTranslation();
  return (
    <Input
      type="search"
      label={label ?? t("ui.search")}
      hint={hint}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      leading={<Search className="h-4 w-4" />}
      trailing={value ? (
        <button type="button" onClick={() => onChange("")} aria-label={t("ui.clearSearch")} title={t("ui.clearSearch")}
          className={cn("inline-flex h-11 w-11 items-center justify-center rounded-xl text-slate-600 hover:text-slate-900", focusRing)}>
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      ) : undefined}
      containerClassName={containerClassName}
      className="[&::-webkit-search-cancel-button]:appearance-none"
      autoComplete="off"
      {...rest}
    />
  );
}

export interface FilterBarProps {
  /** Search field (rendered first, grows to fill the row on desktop). */
  search?: SearchInputProps;
  /** Filter controls (`Select`, `Checkbox`, `Switch`...). */
  children?: React.ReactNode;
  /** Shows "Reset filters" when given and `canReset` is true. */
  onReset?: () => void;
  canReset?: boolean;
  className?: string;
}

/** Search + filters above a list. Stacks on phones, one wrapping row on desktop. */
export function FilterBar({ search, children, onReset, canReset = false, className }: FilterBarProps) {
  const { t } = useTranslation();
  return (
    <div role="search" className={cn("flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end", className)}>
      {search && <SearchInput containerClassName="sm:min-w-[16rem] sm:flex-1" {...search} />}
      {children && <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:[&>*]:min-w-[12rem]">{children}</div>}
      {onReset && canReset && (
        <Button variant="link" onClick={onReset} className="self-start sm:self-end sm:min-h-11">{t("ui.resetFilters")}</Button>
      )}
    </div>
  );
}
