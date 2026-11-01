// Phase 11 S3: API client of the privacy screens (PHASE_11_DESIGN 3.3, 4).
import { getAuthHeader, studentViewUnauthorized } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { LmsApiError, lmsFetch } from "@/lib/lms/client";
import type { PageOut } from "@/lib/lms/types";

export type AgeBand = "under_14" | "14_17" | "18_plus";
export type PolicyKind = "privacy" | "terms" | "guardian_consent";
export const AGE_BANDS: AgeBand[] = ["under_14", "14_17", "18_plus"];
export const POLICY_KINDS: PolicyKind[] = ["privacy", "terms", "guardian_consent"];

export interface PolicyOut {
  id: string;
  kind: PolicyKind;
  version: number;
  status: string;
  body: string;
}

export interface DataRequestOut {
  id: string;
  kind: "export" | "delete";
  status: "pending" | "completed" | "rejected" | "cancelled";
  requested_at: string;
  due_at: string;
  completed_at: string | null;
  reject_code: string | null;
}

export interface PrivacyState {
  age_band: AgeBand | null;
  consent_state: "legacy" | "ok" | "pending_guardian" | "exempt";
  consent_due_at: string | null;
  needs: { kind: PolicyKind; policy_version_id: string }[];
  requests: DataRequestOut[];
}

export interface GuardianRow {
  id: string;
  guardian_name: string;
  created_at: string;
  holds_consent: boolean;
}

export interface PairingCode {
  code: string;
  expires_at: string;
}

export interface AdminRequestOut extends DataRequestOut {
  user_id: string;
  user_email: string | null;
  overdue: boolean;
}

export const getPolicies = (locale: string) => lmsFetch<PolicyOut[]>("/privacy/policies/current", { params: { locale } });
/** The ids a person of 14 or more accepts. */
export const ownPolicyIds = (rows: PolicyOut[]) => rows.filter((p) => p.kind === "privacy" || p.kind === "terms").map((p) => p.id);

export const getMyPrivacy = () => lmsFetch<PrivacyState>("/me/privacy");
export const setMyAgeBand = (age_band: AgeBand, policy_version_ids: string[]) =>
  lmsFetch<PrivacyState>("/me/privacy/age-band", { method: "POST", body: { age_band, policy_version_ids } });
export const giveConsents = (policy_version_ids: string[]) =>
  lmsFetch<PrivacyState>("/me/privacy/consents", { method: "POST", body: { policy_version_ids } });
export const createDataRequest = (kind: "export" | "delete", password?: string) =>
  lmsFetch<DataRequestOut>("/me/privacy/requests", { method: "POST", body: { kind, password } });
export const cancelDataRequest = (id: string) => lmsFetch<void>(`/me/privacy/requests/${encodeURIComponent(id)}`, { method: "DELETE" });

/** The export is streamed with the bearer token and saved as a file; the download completes the request. */
export async function downloadDataExport(id: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/me/privacy/requests/${encodeURIComponent(id)}/download`, {
      headers: { ...(await getAuthHeader()) }, cache: "no-store",
    });
  } catch {
    throw new LmsApiError(0, "network", "Network error");
  }
  if (!res.ok) {
    studentViewUnauthorized(res.status);
    const err = (await res.json().catch(() => null))?.error;
    throw new LmsApiError(res.status, err?.code || "unknown", err?.message || `HTTP ${res.status}`, err?.details || {});
  }
  const objectUrl = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = objectUrl;
  a.rel = "noopener";
  a.download = "my-data.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

export const listMyGuardians = () => lmsFetch<GuardianRow[]>("/me/guardians");
export const createPairingCode = () => lmsFetch<PairingCode>("/me/guardians/pairing-code", { method: "POST" });
export const removeMyGuardian = (id: string) => lmsFetch<void>(`/me/guardians/${encodeURIComponent(id)}`, { method: "DELETE" });

export const listAdminRequests = (status: string | null, cursor: string | null) =>
  lmsFetch<PageOut<AdminRequestOut>>("/admin/privacy/requests", { params: { status, cursor } });
export const executeAdminRequest = (id: string) =>
  lmsFetch<AdminRequestOut>(`/admin/privacy/requests/${encodeURIComponent(id)}/execute`, { method: "POST" });
export const rejectAdminRequest = (id: string, reject_code: string) =>
  lmsFetch<AdminRequestOut>(`/admin/privacy/requests/${encodeURIComponent(id)}/reject`, { method: "POST", body: { reject_code } });
