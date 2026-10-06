"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { User } from "firebase/auth";

export type UserRole = "student" | "admin";

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

interface AuthContextType {
  user: User | null;
  userProfile: AuthUserProfile | null;
  loading: boolean;
  signIn: (email: string, pass: string) => Promise<{ role: UserRole }>;
  signUp: (email: string, pass: string, displayName: string, phone?: string) => Promise<void>;
  signOut: () => Promise<void>;
  loginAsDemo: (role: UserRole) => Promise<{ role: UserRole }>;
  updateTargetScore: (score: number) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  userProfile: null,
  loading: true,
  signIn: async () => ({ role: "student" }),
  signUp: async () => {},
  signOut: async () => {},
  loginAsDemo: async () => ({ role: "student" }),
  updateTargetScore: async () => {},
});

const DEMO_USERS: Record<UserRole, { email: string; pass: string; displayName: string }> = {
  student: {
    email: "student@ort.kg",
    pass: "student123",
    displayName: "Айбек Жумабеков",
  },
  admin: {
    email: "admin@ort.kg",
    pass: "admin123",
    displayName: "Нурлан Админ",
  },
};

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

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [userProfile, setUserProfile] = useState<AuthUserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  // Sync auth state on mount
  useEffect(() => {
    async function loadStoredAuth() {
      if (typeof window === "undefined") {
        setLoading(false);
        return;
      }

      const storedToken = localStorage.getItem("ort_token");
      const storedDevUser = localStorage.getItem("ort_dev_auth_user");

      if (storedToken) {
        try {
          // Fetch current profile from backend using stored token
          const res = await fetch("/api/v1/auth/me", {
            headers: { Authorization: `Bearer ${storedToken}` },
          });
          if (res.ok) {
            const data = await res.json();
            const role: UserRole = data.role === "admin" ? "admin" : "student";
            const profile: AuthUserProfile = {
              uid: data.id,
              email: data.email,
              displayName: data.displayName || data.email.split("@")[0],
              role,
              phone: data.phone,
              target_score: data.target_score || 200,
              currentEstimatedScore: data.currentEstimatedScore ?? 0,
              exams_taken: data.exams_taken ?? 0,
              starting_score: data.starting_score ?? 0,
            };

            setAuthCookies(storedToken, role);
            setUserProfile(profile);
            setUser({
              uid: profile.uid,
              email: profile.email,
              displayName: profile.displayName,
              getIdToken: async () => storedToken,
            } as unknown as User);
            setLoading(false);
            return;
          }
        } catch (e) {
          console.warn("Could not verify session with backend, falling back to local cache:", e);
        }
      }

      // Fallback to cached dev user
      if (storedDevUser) {
        try {
          const parsed = JSON.parse(storedDevUser) as AuthUserProfile;
          const role: UserRole = parsed.role === "admin" ? "admin" : "student";
          setAuthCookies(storedToken || (role === "admin" ? "mock_admin_token" : "mock_student_token"), role);
          setUserProfile(parsed);
          setUser({
            uid: parsed.uid,
            email: parsed.email,
            displayName: parsed.displayName,
            getIdToken: async () => (role === "admin" ? "mock_admin_token" : "mock_student_token"),
          } as unknown as User);
        } catch {
          localStorage.removeItem("ort_dev_auth_user");
        }
      }

      setLoading(false);
    }

    loadStoredAuth();
  }, []);

  const signIn = async (email: string, pass: string): Promise<{ role: UserRole }> => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password: pass }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Authentication failed");
      }

      const data = await res.json();
      const role: UserRole = data.role === "admin" ? "admin" : "student";
      const token = data.access_token;

      setAuthCookies(token, role);
      localStorage.setItem("ort_token", token);
      localStorage.setItem("ort_role", role);

      const profile: AuthUserProfile = {
        uid: data.user.id,
        email: data.user.email,
        displayName: data.user.displayName || email.split("@")[0],
        role,
        target_score: data.user.target_score || 200,
      };

      localStorage.setItem("ort_dev_auth_user", JSON.stringify(profile));
      setUserProfile(profile);
      setUser({
        uid: profile.uid,
        email: profile.email,
        displayName: profile.displayName,
        getIdToken: async () => token,
      } as unknown as User);

      return { role };
    } finally {
      setLoading(false);
    }
  };

  const signUp = async (email: string, pass: string, displayName: string, phone?: string): Promise<void> => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          password: pass,
          displayName: displayName.trim(),
          phone: phone?.trim() || undefined,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Registration failed");
      }

      const data = await res.json();
      const token = data.access_token;
      const role: UserRole = "student";

      setAuthCookies(token, role);
      localStorage.setItem("ort_token", token);
      localStorage.setItem("ort_role", role);

      const profile: AuthUserProfile = {
        uid: data.user.id,
        email: data.user.email,
        displayName: data.user.displayName || displayName || email.split("@")[0],
        phone: data.user.phone || phone,
        role,
        target_score: 200,
      };

      localStorage.setItem("ort_dev_auth_user", JSON.stringify(profile));
      setUserProfile(profile);
      setUser({
        uid: profile.uid,
        email: profile.email,
        displayName: profile.displayName,
        getIdToken: async () => token,
      } as unknown as User);
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    clearAuthCookies();
    if (typeof window !== "undefined") {
      localStorage.removeItem("ort_token");
      localStorage.removeItem("ort_role");
      localStorage.removeItem("ort_dev_auth_user");
    }
    setUser(null);
    setUserProfile(null);
  };

  const loginAsDemo = async (role: UserRole): Promise<{ role: UserRole }> => {
    const demo = DEMO_USERS[role];
    return await signIn(demo.email, demo.pass);
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
        localStorage.setItem("ort_dev_auth_user", JSON.stringify(updated));
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
        signOut,
        loginAsDemo,
        updateTargetScore,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
