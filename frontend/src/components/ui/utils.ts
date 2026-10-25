import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge class names; later Tailwind classes win over earlier ones. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** The one visible focus ring used by every interactive element (keyboard focus only). */
export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2";

/** Shared look of text fields (Input, Textarea, Select). 16 px text on phones avoids iOS zoom. */
export const fieldBase =
  "block w-full rounded-xl border bg-white px-3 text-base leading-6 text-slate-900 placeholder:text-slate-500 " +
  "focus:outline-none focus:ring-2 focus:ring-brand-600/30 focus:border-brand-600 " +
  "disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-600 sm:text-sm sm:leading-6";

export function fieldBorder(invalid: boolean): string {
  return invalid ? "border-danger-600" : "border-slate-300";
}
