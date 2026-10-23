"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";

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
  phone?: string;
  is_platform_admin: boolean;
  teacher_status: string;
  locale?: string;
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
  signIn: (email: string, pass: string) => Promise<void>;
  signUp: (email: string, pass: string, displayName: string, phone?: string) => Promise<RegisterResult>;
  verifyEmail: (email: string, pass: string, code: string) => Promise<void>;
  resendCode: (email: string) => Promise<{ resendAfterSeconds: number }>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  userProfile: null,
  loading: true,
  signIn: async () => {},
  signUp: async () => ({ email: "", resendAfterSeconds: 60, codeTtlMinutes: 10 }),
  verifyEmail: async () => {},
  resendCode: async () => ({ resendAfterSeconds: 60 }),
  signOut: async () => {},
});

const PROFILE_KEY = "ort_dev_auth_user";

function toProfile(u: any): AuthUserProfile {
  return {
    uid: u.id,
    email: u.email,
    displayName: u.displayName || String(u.email).split("@")[0],
    phone: u.phone || undefined,
    is_platform_admin: Boolean(u.is_platform_admin),
    teacher_status: u.teacher_status || "none",
    locale: u.locale || undefined,
  };
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
    if (typeof window !== "undefined") {
      localStorage.removeItem("ort_token");
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
    localStorage.setItem("ort_token", token);
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
          const profile = toProfile(data);
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

  const finishLogin = (data: any): void => {
    startSession(data.access_token, toProfile(data.user));
  };

  const signIn = async (email: string, pass: string): Promise<void> => {
    const data = await postJson("/api/v1/auth/login", { email: email.trim(), password: pass, lang });
    finishLogin(data);
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

  const verifyEmail = async (email: string, pass: string, code: string): Promise<void> => {
    const data = await postJson("/api/v1/auth/verify-email", { email: email.trim(), password: pass, code: code.trim() });
    finishLogin(data);
  };

  const resendCode = async (email: string): Promise<{ resendAfterSeconds: number }> => {
    return postJson("/api/v1/auth/resend-code", { email: email.trim(), lang });
  };

  const signOut = async () => {
    clearSession();
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
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
