// S1 admin security: the platform admin's own two-step login, platform admins, sessions, health.
import { lmsFetch } from "./client";
import type { AdminUserOut } from "./types";

const enc = encodeURIComponent;
const post = <T,>(path: string, body?: unknown) => lmsFetch<T>(path, { method: "POST", body: body ?? {} });

export interface MfaStatus {
  enabled: boolean;
  enabled_at: string | null;
  /** Platform admins must set it up before using the admin area. */
  required: boolean;
  recovery_codes_left: number;
}
export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
}
export interface MfaEnabled {
  recovery_codes: string[];
  /** Turning it on ends every session; the page continues with this one. */
  access_token: string;
}

export const getMfaStatus = () => lmsFetch<MfaStatus>("/platform/security/mfa");
/** Both need the account's current password (a stolen session alone cannot turn two-step login on). */
export const startMfaSetup = (password: string) => post<MfaSetup>("/platform/security/mfa/setup", { password });
export const confirmMfa = (code: string, password: string) =>
  post<MfaEnabled>("/platform/security/mfa/confirm", { code, password });
export const regenerateRecoveryCodes = (code: string) =>
  post<{ recovery_codes: string[] }>("/platform/security/mfa/recovery-codes", { code });
/** Every session of the signed-in account, this one included. */
export const logoutEverywhere = () => post<{ success: boolean }>("/auth/logout-all");

export const setPlatformAdmin = (userId: string, platformAdmin: boolean, reason: string, code: string) =>
  post<AdminUserOut>(`/platform/users/${enc(userId)}/platform-admin`, { platform_admin: platformAdmin, reason, code });
export const endUserSessions = (userId: string, reason: string) =>
  post<AdminUserOut>(`/platform/users/${enc(userId)}/end-sessions`, { reason });

export interface PlatformHealth {
  ok: boolean;
  database: { ok: boolean; latency_ms: number | null; dialect: string };
  migrations: { ok: boolean; current: string[]; expected: string[] };
  email: { ok: boolean; provider: string; configured: boolean };
  storage: { ok: boolean; driver: string; r2_configured: boolean };
  commit: string | null;
}
export const getPlatformHealth = () => lmsFetch<PlatformHealth>("/platform/health");
