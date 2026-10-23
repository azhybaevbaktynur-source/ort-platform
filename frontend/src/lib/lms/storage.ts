import { lmsFetch } from "./client";

/** R2 free-tier guard (Phase 5): GET /platform/storage, POST /platform/storage/smoke (platform admin). */
export type StorageLevel = "ok" | "warn" | "full";

export interface StorageMonthOut {
  month: string;
  class_a: number;
  class_b_backend: number;
  class_b_estimated: number;
  bytes_written: number;
  objects_written: number;
}

export interface StorageSummaryOut {
  driver: string;
  public_base_is_r2dev: boolean;
  stored_bytes: number;
  object_count: number;
  warn_bytes: number;
  hard_bytes: number;
  level: StorageLevel;
  month: StorageMonthOut;
}

export interface StorageSmokeOut {
  put_ok: boolean;
  head_ok: boolean;
  public_read_ok: boolean;
  public_url: string | null;
  status_code: number | null;
  deleted: boolean;
  latency_ms: number;
  error: string | null;
}

/** Cloudflare R2 free tier per month (owner requirement 8). */
export const R2_FREE_CLASS_A = 1_000_000;
export const R2_FREE_CLASS_B = 10_000_000;

export const getStorageSummary = () => lmsFetch<StorageSummaryOut>("/platform/storage");
export const runStorageSmoke = () => lmsFetch<StorageSmokeOut>("/platform/storage/smoke", { method: "POST", body: {} });

/** `units`: translated [B, KB, MB, GB] (keys `storage.units.*`). */
export function formatBytes(n: number, locale: string, units: [string, string, string, string]): string {
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: i === 0 ? 0 : 2 }).format(v)} ${units[i]}`;
}
