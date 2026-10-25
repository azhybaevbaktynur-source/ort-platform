// Phase 6b S6b: student home data (`GET /me/home`, PHASE_6_DESIGN 8.4). One server-limited call, no N+1.
import { lmsFetch } from "./client";
import type { HomeOut } from "./homeTypes";

export const getHome = (signal?: AbortSignal) => lmsFetch<HomeOut>("/me/home", { signal });
