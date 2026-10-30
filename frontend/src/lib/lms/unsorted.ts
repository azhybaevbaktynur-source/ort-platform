// Phase 8c S1 (PHASE_8C_DESIGN §3.4, §7): Course page reads for the "Unsorted" group and the module duplicate write.
// S2 builds `UnsortedGroup` and the module "⋯ → Duplicate" entry on these.
import { lmsFetch } from "./client";
import type { ModuleStaffOut } from "./modulesTypes";
import type { UnsortedKind, UnsortedOut } from "./types";

const e = encodeURIComponent;

/** Staff and org admins: one page per kind (20 rows by default, at most 50); with `kind`, only that kind's page
 * (`cursor` continues it). */
export const getUnsorted = (
  courseId: string,
  opts: { kind?: UnsortedKind; cursor?: string | null; limit?: number; signal?: AbortSignal } = {},
) =>
  lmsFetch<UnsortedOut>(`/courses/${e(courseId)}/modules/unsorted`, {
    params: { kind: opts.kind, cursor: opts.cursor ?? undefined, limit: opts.limit },
    signal: opts.signal,
  });

/** A draft copy right after the module (items and requirements copied, prerequisites not). 422 `limit_reached` at the
 * module cap. */
export const duplicateModule = (courseId: string, moduleId: string) =>
  lmsFetch<ModuleStaffOut>(`/courses/${e(courseId)}/modules/${e(moduleId)}/duplicate`, { method: "POST" });
