"use client";

import { createContext, useContext } from "react";
import type { StudentShellData } from "./useStudentShellData";

/*
 * Student UI U3 (STUDENT_UI_DESIGN §3.1): the student shell's data (exam-prep courses, the current one) for the pages
 * inside it, so the home follows the exam switcher. Null outside the student frame.
 */
export const StudentShellDataContext = createContext<StudentShellData | null>(null);

export function useStudentShellDataContext(): StudentShellData | null {
  return useContext(StudentShellDataContext);
}
