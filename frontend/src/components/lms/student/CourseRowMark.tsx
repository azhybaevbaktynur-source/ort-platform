"use client";

/**
 * Step 3a S9 (STUDENT_IA_DESIGN §0.4, V12): a sidebar or «Ещё» row's mark. A course with a cover shows it as a
 * 24 × 24 thumbnail (the same URL as the card's cover, so the browser cache serves it; no new size on the server);
 * otherwise, or when the image fails to load, the subject / family mark of `courseMark`.
 */
import React, { useState } from "react";
import { CourseMark } from "@/lib/lms/courseIcon";
import type { CourseMarkInput } from "@/lib/lms/courseMarkKey";

export function CourseRowMark({ course }: { course: CourseMarkInput & { cover_url?: string | null } }) {
  const [broken, setBroken] = useState<string | null>(null);
  const url = course.cover_url || null;
  if (url && broken !== url) {
    return (
      // 24 px drawn in the icon's 20 px slot (-m-0.5), so every row's title starts at the same x
      // eslint-disable-next-line @next/next/no-img-element
      <img src={url} alt="" loading="lazy" decoding="async" draggable={false} data-icon="cover"
        onError={() => setBroken(url)} className="-m-0.5 h-6 w-6 max-w-none shrink-0 rounded-md object-cover" />
    );
  }
  return <CourseMark course={course} />;
}
