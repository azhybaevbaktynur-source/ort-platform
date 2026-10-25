/** Small formatting helpers shared by the assessment UI. */
import { parseApiDate } from "@/lib/format";

export function secToMin(s: number | null | undefined): string {
  return s === null || s === undefined ? "" : String(Math.round(s / 60));
}

/** Empty or invalid input means "no limit" (null). */
export function minToSec(v: string): number | null {
  const n = Number(v);
  if (!v.trim() || !Number.isFinite(n) || n <= 0) return null;
  return Math.round(n * 60);
}

/** ISO timestamp -> value for <input type="datetime-local"> in local time. */
export function toLocalInput(iso: string | null | undefined): string {
  const d = parseApiDate(iso);
  if (!d) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fromLocalInput(v: string): string | null {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function fmtDateTime(iso: string | null | undefined): string {
  const d = parseApiDate(iso);
  return d ? d.toLocaleString() : "";
}

export function fmtPoints(p: number | string | null | undefined): string {
  if (p === null || p === undefined || p === "") return "";
  const n = Number(p);
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : String(p);
}

/** New order after moving the element at `from` to index `to`. */
export function moveIndex<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = list.slice();
  const [x] = next.splice(from, 1);
  next.splice(to, 0, x);
  return next;
}
