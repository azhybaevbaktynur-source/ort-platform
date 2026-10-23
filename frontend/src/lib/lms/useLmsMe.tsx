"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getMe } from "./courses";
import type { LmsApiError } from "./client";
import type { MeOut } from "./types";

interface LmsMeState {
  me: MeOut | null;
  loading: boolean;
  error: LmsApiError | null;
  reload: () => Promise<void>;
}

const LmsMeContext = createContext<LmsMeState | null>(null);

export function useLmsMeLoader(enabled: boolean): LmsMeState {
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<LmsApiError | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setMe(await getMe());
      setError(null);
    } catch (e) {
      setError(e as LmsApiError);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) void reload();
  }, [enabled, reload]);

  return { me, loading, error, reload };
}

export const LmsMeProvider = LmsMeContext.Provider;

/** Current user's LMS profile (MeOut). Requires LmsShell (or another LmsMeProvider) above. */
export function useLmsMe(): LmsMeState {
  const ctx = useContext(LmsMeContext);
  if (!ctx) throw new Error("useLmsMe must be used within LmsShell");
  return ctx;
}
