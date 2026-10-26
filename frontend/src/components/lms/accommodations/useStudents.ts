"use client";

import { useCallback, useEffect, useState } from "react";
import { listAccommodations, type AccommodationRowOut } from "@/lib/lms/accommodations";

const MAX_PAGES = 10;

/** Active students of a course with their accommodation (teacher only), up to 500, for pickers. */
export function useStudents(courseId: string, enabled: boolean) {
  const [rows, setRows] = useState<AccommodationRowOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      const all: AccommodationRowOut[] = [];
      let cursor: string | null = null;
      for (let i = 0; i < MAX_PAGES; i++) {
        const page: { items: AccommodationRowOut[]; next_cursor: string | null } = await listAccommodations(courseId, { cursor, limit: 50 });
        all.push(...page.items);
        cursor = page.next_cursor;
        if (!cursor) break;
      }
      setRows(all);
    } catch (e) {
      setError(e);
    }
  }, [courseId]);
  useEffect(() => { if (enabled) void load(); }, [enabled, load]);
  return { rows, error, reload: load };
}
