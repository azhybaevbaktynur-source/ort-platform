"use client";

/**
 * Step 3a S9 (STUDENT_IA_DESIGN §0.4, V11–V12): a course's mark, one place for the whole student UI. `courseMark`
 * picks the lucide icon from `exam_family` / `subject` (the key logic is `courseMarkKey.ts`, checked by
 * `courseIcon.check.ts`); `CourseMark` draws it with a `data-icon` attribute (size and colour from the caller: this
 * folder is not in Tailwind's `content`, so no class names live here). The sidebar / «Ещё» row's thumbnail-or-mark is
 * `components/lms/student/CourseRowMark.tsx`.
 */
import React from "react";
import {
  Atom, Award, BookOpen, BookText, ClipboardCheck, Dna, FlaskConical, Globe, Landmark, Languages, Sigma,
  type LucideIcon,
} from "lucide-react";
import { courseMarkKey, type CourseMarkInput, type CourseMarkKey } from "./courseMarkKey";

const ICONS: Record<CourseMarkKey, LucideIcon> = {
  sigma: Sigma,
  atom: Atom,
  "flask-conical": FlaskConical,
  dna: Dna,
  landmark: Landmark,
  globe: Globe,
  languages: Languages,
  "book-text": BookText,
  award: Award,
  "clipboard-check": ClipboardCheck,
  "book-open": BookOpen,
};

/** The course's mark: its key (for `data-icon`) and its lucide icon. */
export function courseMark(c: CourseMarkInput | null | undefined): { key: CourseMarkKey; Icon: LucideIcon } {
  const key = courseMarkKey(c);
  return { key, Icon: ICONS[key] };
}

/** The mark as an element; size and colour come from the caller (`className`, `strokeWidth`). */
export function CourseMark({ course, className, strokeWidth }: {
  course: CourseMarkInput | null | undefined;
  className?: string;
  strokeWidth?: number;
}) {
  const { key, Icon } = courseMark(course);
  return <Icon aria-hidden="true" data-icon={key} className={className} strokeWidth={strokeWidth} />;
}
