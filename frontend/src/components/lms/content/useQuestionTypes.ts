"use client";

// Phase 10: the question types a course offers. ORT keeps the seven types; every other course, and pages outside a
// course (shared banks), also offer matching, fill-in-the-blank and ordering. The server refuses them on ORT too.
import { useContext } from "react";
import { CourseContext } from "@/components/lms/CourseContext";
import { ALL_QUESTION_TYPES, QUESTION_TYPES, type QuestionType } from "@/lib/lms/contentTypes";

export function useQuestionTypes(): QuestionType[] {
  return useContext(CourseContext)?.course.template?.key === "ort" ? QUESTION_TYPES : ALL_QUESTION_TYPES;
}
