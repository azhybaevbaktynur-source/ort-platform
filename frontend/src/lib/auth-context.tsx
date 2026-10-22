"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";

export type UserRole = "student" | "admin";

/** Minimal signed-in user (the app authenticates with its own backend JWT, not Firebase). */
export interface AuthUser {
  uid: string;
  email: string;
  displayName: string;
  getIdToken: () => Promise<string>;
}

export interface AuthUserProfile {
  uid: string;
  email: string;
  displayName: string;
  role: UserRole;
  phone?: string;
  target_score?: number;
  currentEstimatedScore?: number;
  exams_taken?: number;
  starting_score?: number;
  streak?: {
    current: number;
    longest: number;
    lastActiveDate: string;
  };
}

export interface RegisterResult {
  email: string;
  resendAfterSeconds: number;
  codeTtlMinutes: number;
}

/**
 * Error from the auth API. `code` is machine-readable (e.g. "email_not_verified", "invalid_code")
 * so pages can show a translated message; `details` carries extras like attemptsLeft.
 */
export class AuthError extends Error {
  code?: string;
  status: number;
  details: Record<string, unknown>;

  constructor(status: number, message: string, code?: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface AuthContextType {
  user: AuthUser | null;
  userProfile: AuthUserProfile | null;
  loading: boolean;
  signIn: (email: string, pass: string) => Promise<{ role: UserRole }>;
  signUp: (email: string, pass: string, displayName: string, phone?: string) => Promise<RegisterResult>;
  verifyEmail: (email: string, pass: string, code: string) => Promise<{ role: UserRole }>;
  resendCode: (email: string) => Promise<{ resendAfterSeconds: number }>;
  signOut: () => Promise<void>;
  updateTargetScore: (score: number) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  userProfile: null,
  loading: true,
  signIn: async () => ({ role: "student" }),
  signUp: async () => ({ email: "", resendAfterSeconds: 60, codeTtlMinutes: 10 }),
  verifyEmail: async () => ({ role: "student" }),
  resendCode: async () => ({ resendAfterSeconds: 60 }),
  signOut: async () => {},
  updateTargetScore: async () => {},
});

const PROFILE_KEY = "ort_dev_auth_user";

function setAuthCookies(token: string, role: string) {
  if (typeof document !== "undefined") {
    document.cookie = `ort_token=${encodeURIComponent(token)}; path=/; max-age=604800; SameSite=Lax`;
    document.cookie = `ort_role=${encodeURIComponent(role)}; path=/; max-age=604800; SameSite=Lax`;
  }
}

function clearAuthCookies() {
  if (typeof document !== "undefined") {
    document.cookie = "ort_token=; path=/; max-age=0; SameSite=Lax";
    document.cookie = "ort_role=; path=/; max-age=0; SameSite=Lax";
  }
}

function toAuthUser(profile: AuthUserProfile, token: string): AuthUser {
  return {
    uid: profile.uid,
    email: profile.email,
    displayName: profile.displayName,
    getIdToken: async () => token,
  };
}

async function postJson(path: string, body: unknown): Promise<any> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const { code, message, ...rest } = detail as Record<string, unknown>;
      throw new AuthError(res.status, String(message || `HTTP ${res.status}`), code as string | undefined, rest);
    }
    throw new AuthError(res.status, typeof detail === "string" ? detail : `HTTP ${res.status}`);
  }
  return data;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { lang } = useTranslation();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [userProfile, setUserProfile] = useState<AuthUserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = () => {
    clearAuthCookies();
    if (typeof window !== "undefined") {
      localStorage.removeItem("ort_token");
      localStorage.removeItem("ort_role");
      localStorage.removeItem(PROFILE_KEY);
      try {
        // pending autosave queues belong to the signed-out user
        for (const k of Object.keys(localStorage)) {
          if (k.startsWith("lms_attempt_q_")) localStorage.removeItem(k);
        }
      } catch { /* storage unavailable */ }
    }
    setUser(null);
    setUserProfile(null);
  };

  const startSession = (token: string, profile: AuthUserProfile) => {
    setAuthCookies(token, profile.role);
    localStorage.setItem("ort_token", token);
    localStorage.setItem("ort_role", profile.role);
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    setUserProfile(profile);
    setUser(toAuthUser(profile, token));
  };

  // Restore the session instantly from the cached profile, then confirm it with the backend in the
  // background. Pages no longer wait for /auth/me (slow while the server wakes up) before rendering.
  useEffect(() => {
    const storedToken = localStorage.getItem("ort_token");
    if (!storedToken) {
      setLoading(false);
      return;
    }

    let cached: AuthUserProfile | null = null;
    try {
      const raw = localStorage.getItem(PROFILE_KEY);
      cached = raw ? (JSON.parse(raw) as AuthUserProfile) : null;
    } catch {
      localStorage.removeItem(PROFILE_KEY);
    }
    if (cached) {
      setAuthCookies(storedToken, cached.role === "admin" ? "admin" : "student");
      setUserProfile(cached);
      setUser(toAuthUser(cached, storedToken));
      setLoading(false);
    }

    (async () => {
      try {
        const res = await fetch("/api/v1/auth/me", {
          headers: { Authorization: `Bearer ${storedToken}` },
        });
        if (res.status === 401 || res.status === 403) {
          clearSession();
          return;
        }
        if (res.ok) {
          const data = await res.json();
          const profile: AuthUserProfile = {
            uid: data.id,
            email: data.email,
            displayName: data.displayName || data.email.split("@")[0],
            role: data.role === "admin" ? "admin" : "student",
            phone: data.phone,
            target_score: data.target_score || 200,
            currentEstimatedScore: data.currentEstimatedScore ?? 0,
            exams_taken: data.exams_taken ?? 0,
            starting_score: data.starting_score ?? 0,
          };
          startSession(storedToken, profile);
        }
      } catch (e) {
        // Network problem: keep the cached session; the backend still checks the token on every call.
        console.warn("Could not verify session with backend:", e);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const finishLogin = (data: any): { role: UserRole } => {
    const role: UserRole = data.role === "admin" ? "admin" : "student";
    startSession(data.access_token, {
      uid: data.user.id,
      email: data.user.email,
      displayName: data.user.displayName || data.user.email.split("@")[0],
      phone: data.user.phone || undefined,
      role,
      target_score: data.user.target_score || 200,
    });
    return { role };
  };

  const signIn = async (email: string, pass: string): Promise<{ role: UserRole }> => {
    const data = await postJson("/api/v1/auth/login", { email: email.trim(), password: pass, lang });
    return finishLogin(data);
  };

  const signUp = async (email: string, pass: string, displayName: string, phone?: string): Promise<RegisterResult> => {
    return postJson("/api/v1/auth/register", {
      email: email.trim(),
      password: pass,
      displayName: displayName.trim(),
      phone: phone?.trim() || undefined,
      lang,
    });
  };

  const verifyEmail = async (email: string, pass: string, code: string): Promise<{ role: UserRole }> => {
    const data = await postJson("/api/v1/auth/verify-email", { email: email.trim(), password: pass, code: code.trim() });
    return finishLogin(data);
  };

  const resendCode = async (email: string): Promise<{ resendAfterSeconds: number }> => {
    return postJson("/api/v1/auth/resend-code", { email: email.trim(), lang });
  };

  const signOut = async () => {
    clearSession();
  };

  const updateTargetScore = async (score: number) => {
    try {
      const { getAuthHeader } = await import("./api");
      const authHeader = await getAuthHeader();
      await fetch("/api/v1/users/me/target-score", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeader,
        },
        body: JSON.stringify({ target_score: score }),
      });
    } catch (err) {
      console.error("Failed to update target score via API:", err);
    }

    setUserProfile((prev) => {
      if (!prev) return null;
      const updated = { ...prev, target_score: score };
      try {
        localStorage.setItem(PROFILE_KEY, JSON.stringify(updated));
      } catch {}
      return updated;
    });
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        userProfile,
        loading,
        signIn,
        signUp,
        verifyEmail,
        resendCode,
        signOut,
        updateTargetScore,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
