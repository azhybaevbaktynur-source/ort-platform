"use client";

import { useEffect, useState } from "react";
import { getCourseGrading } from "@/lib/lms/grading";
import { isStaffCourseGrading, type CategoryOut } from "@/lib/lms/gradingTypes";

/** Grade categories of a course (staff); empty while loading or when the course has none. */
export function useCategories(courseId: string, enabled = true): CategoryOut[] {
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  useEffect(() => {
    if (!enabled) return;
    let off = false;
    getCourseGrading(courseId)
      .then((g) => { if (!off && isStaffCourseGrading(g)) setCategories(g.categories); })
      .catch(() => { if (!off) setCategories([]); });
    return () => { off = true; };
  }, [courseId, enabled]);
  return categories;
}
