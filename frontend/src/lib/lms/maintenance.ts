import { lmsFetch } from "./client";

/** Daily database maintenance (DB_STORAGE_REVIEW 5, slice D2): GET /platform/maintenance, POST /platform/maintenance/run
 *  (platform admin; a dry run unless `apply`). The daily GitHub run uses the token route, not these. */
export interface MaintenanceCounts {
  /** Dry run: rows due. Applied: rows this run handled (at most one bounded batch per task). */
  examined: number;
  changed: number;
}

export interface MaintenanceRun {
  ran_at: string;
  dry_run: boolean;
  trigger: "token" | "admin" | "fallback" | string;
  counts: Record<string, MaintenanceCounts>;
  errors: string[];
}

export interface MaintenanceState {
  tasks: string[];
  last_run: MaintenanceRun | null;
}

export const getMaintenance = () => lmsFetch<MaintenanceState>("/platform/maintenance");
export const runMaintenance = (apply: boolean) =>
  lmsFetch<MaintenanceRun>("/platform/maintenance/run", { method: "POST", body: { apply } });
