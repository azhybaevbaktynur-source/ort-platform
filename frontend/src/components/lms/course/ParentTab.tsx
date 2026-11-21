"use client";

// Lesson course requests C3: an object page whose parent tab the path cannot tell declares it to the student course
// frame (the lobby and the result of a lesson quiz live under /assessments and /attempts, yet belong to Уроки). The
// declaration holds only for the path it was made on, so a stale one never marks another page.
import { createContext, useContext, useEffect } from "react";
import { usePathname } from "next/navigation";
import type { CourseTabKey } from "@/lib/lms/courseTabs";

export interface ParentTabDecl {
  path: string;
  tab: CourseTabKey;
}

export const ParentTabContext = createContext<((decl: ParentTabDecl | null) => void) | null>(null);

/** Declare this page's parent tab (null: the tab of its path). No-op outside the student course frame. */
export function useDeclareParentTab(tab: CourseTabKey | null): void {
  const declare = useContext(ParentTabContext);
  const pathname = usePathname() || "";
  useEffect(() => {
    if (!declare) return;
    declare(tab ? { path: pathname, tab } : null);
    return () => declare(null);
  }, [declare, pathname, tab]);
}
