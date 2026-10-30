// Phase 8c S1 (PHASE_8C_DESIGN §3.5, §7): the teacher Course page "To do" panel (S2 builds `TodoPanel` on it).
import { lmsFetch } from "./client";
import type { TodoOut } from "./types";

/** Teachers and assistants: assignments waiting for grading (oldest first, at most 10), drafts (at most 10), the
 * unpublished module count, active students and (teachers only) the join code. */
export const getTodo = (courseId: string, opts: { signal?: AbortSignal } = {}) =>
  lmsFetch<TodoOut>(`/courses/${encodeURIComponent(courseId)}/todo`, { signal: opts.signal });
