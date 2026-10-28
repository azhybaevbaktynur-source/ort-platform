import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";

/** Error from LMS endpoints. `code` maps to the i18n key `lms.errors.<code>`. */
export class LmsApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "LmsApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface LmsFetchOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  params?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  /** Phase 7c UX: let the request outlive the page (a last autosave on `pagehide`); bodies must stay under 64 KB. */
  keepalive?: boolean;
}

export async function lmsFetch<T>(path: string, opts: LmsFetchOptions = {}): Promise<T> {
  const { method = "GET", body, params, signal, keepalive } = opts;
  let url = `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
  if (params) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") sp.append(k, String(v));
    }
    const qs = sp.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = { ...(await getAuthHeader()) };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      cache: "no-store",
      signal,
      ...(keepalive ? { keepalive: true } : {}),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new LmsApiError(0, "network", "Network error");
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
  }

  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    if (err && typeof err === "object" && typeof err.code === "string") {
      throw new LmsApiError(res.status, err.code, err.message || err.code, err.details || {});
    }
    // Old-style or unparseable error: map the status to a coarse code.
    const code = res.status === 401 ? "unknown" : res.status === 403 ? "forbidden" : res.status === 404 ? "not_found" : "unknown";
    throw new LmsApiError(res.status, code, `HTTP ${res.status}`);
  }

  return data as T;
}

export function isLmsApiError(e: unknown): e is LmsApiError {
  return e instanceof LmsApiError;
}
