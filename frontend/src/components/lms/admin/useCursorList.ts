"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PageOut } from "@/lib/lms/types";

/**
 * A cursor-paginated list ("Load more"): first page on mount and whenever `fetchPage` changes
 * (wrap it in useCallback with its filters), `loadMore()` appends the next page. Stale responses
 * (filters changed meanwhile) are dropped.
 */
export function useCursorList<T>(fetchPage: (cursor: string | null) => Promise<PageOut<T>>) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const gen = useRef(0);

  const run = useCallback(async (next: string | null) => {
    const my = ++gen.current;
    setLoading(true);
    setError(null);
    try {
      const page = await fetchPage(next);
      if (my !== gen.current) return;
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      if (my === gen.current) setError(e);
    } finally {
      if (my === gen.current) setLoading(false);
    }
  }, [fetchPage]);

  useEffect(() => { void run(null); }, [run]);

  const reload = useCallback(() => run(null), [run]);
  const loadMore = useCallback(() => { if (cursor) void run(cursor); }, [run, cursor]);
  return { items, setItems, cursor, loading, error, reload, loadMore };
}

/** Debounced search text (350 ms). */
export function useDebounced(value: string, ms = 350): string {
  const [v, setV] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setV(value.trim()), ms);
    return () => clearTimeout(h);
  }, [value, ms]);
  return v;
}
