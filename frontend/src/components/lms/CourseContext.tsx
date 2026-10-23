"use client";

import { createContext, useContext } from "react";
import type { CourseOut } from "@/lib/lms/types";

export interface CourseCtx {
  course: CourseOut;
  reload: () => Promise<void>;
  setCourse: (c: CourseOut) => void;
}

export const CourseContext = createContext<CourseCtx | null>(null);

export function useCourse(): CourseCtx {
  const c = useContext(CourseContext);
  if (!c) throw new Error("useCourse must be used within the course layout");
  return c;
}
