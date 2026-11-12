import { lmsFetch } from "./client";

/** Infrastructure panel (INFRA_PANEL_DESIGN): GET /platform/infra, POST /platform/infra/refresh (platform admin). */
/** `notice` only for the database (50 %; DB_STORAGE_REVIEW 7.2); other metrics are ok / warning (80 %) / critical (95 %). */
export type InfraLevel = "ok" | "notice" | "warning" | "critical";
export type InfraCardStatus = "ok" | "warning" | "error" | "not_connected" | "unavailable" | "refreshing";
export type InfraUnit = "bytes" | "cu_hours" | "count" | "requests" | "emails" | "seconds";

export interface InfraMetric {
  key: string;
  value: number | null;
  limit: number | null;
  unit: InfraUnit;
  percent: number | null;
  level: InfraLevel;
  source: "cloudflare" | "counter" | null;
}

export interface InfraFlag {
  key: string;
  level: InfraLevel;
}

export interface InfraCard {
  provider: string; // neon | render | vercel | r2 | email
  status: InfraCardStatus;
  plan: string | null;
  fetched_at: string | null;
  duration_ms: number | null;
  error_code: string | null;
  error_status: number | null;
  dashboard_url: string | null;
  metrics: InfraMetric[];
  flags: InfraFlag[];
  details: Record<string, number | boolean | string | null>;
}

export interface InfraCapacity {
  fits: number;
  students: number;
  exam_bytes: number;
  used_bytes: number;
  limit_bytes: number;
  used_source: "neon" | "database" | "database_estimate";
  /** Used of the limit, 0-100 (one decimal). */
  percent: number | null;
  /** Database levels: notice 50 %, warning 70 %, critical 85 %; no full exam left raises it (server-side). */
  level: InfraLevel;
  measured_at: string | null;
  estimated: boolean;
  history_seconds: number | null;
  branches: number | null;
  branches_limit: number | null;
  /** Neon Launch storage price (backend `costs.py`), for the upgrade hint. */
  upgrade_storage_usd_per_gb_month: number | null;
  per_row_bytes: Record<string, number>;
}

export interface InfraCostRow {
  key: string;
  service: string;
  plan: string;
  usd_per_month: number | null;
  next_plan: string | null;
  next_usd_per_month: number | null;
  next_unit: string | null;
  verified: boolean;
}

export interface InfraCosts {
  total_usd: number;
  complete: boolean;
  rows: InfraCostRow[];
  source: string;
  as_of: string;
}

export interface InfraOut {
  generated_at: string;
  ttl_seconds: number;
  cards: InfraCard[];
  capacity: InfraCapacity;
  costs: InfraCosts;
}

export const getInfra = () => lmsFetch<InfraOut>("/platform/infra");
export const refreshInfra = () => lmsFetch<InfraOut>("/platform/infra/refresh", { method: "POST", body: {} });

/** Env var names the owner sets on the backend, by provider (names only, INFRA_PANEL_DESIGN 2). */
export const INFRA_ENV: Record<string, string[]> = {
  neon: ["NEON_API_KEY", "NEON_PROJECT_ID"],
  render: ["RENDER_API_KEY", "RENDER_SERVICE_ID"],
  vercel: ["VERCEL_TOKEN", "VERCEL_PROJECT_ID", "VERCEL_TEAM_ID"],
  r2: ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
};
export const INFRA_EMAIL_ENV: Record<string, string[]> = { brevo: ["BREVO_API_KEY"], resend: ["RESEND_API_KEY"] };

/** The card's tone: the server's status, raised by the worst metric or flag level. */
export function cardTone(c: InfraCard): "ok" | "notice" | "warning" | "critical" | "error" | "muted" {
  if (c.status === "error") return "error";
  if (c.status === "not_connected" || c.status === "unavailable") return "muted";
  const levels = [...c.metrics.map((m) => m.level), ...c.flags.map((f) => f.level)];
  if (levels.includes("critical")) return "critical";
  if (c.status === "warning" || levels.includes("warning")) return "warning";
  if (levels.includes("notice")) return "notice";
  return "ok";
}
