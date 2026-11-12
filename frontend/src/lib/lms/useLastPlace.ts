"use client";

// Step 3a S2 (STUDENT_IA_DESIGN §2.5): the write hooks of `lastPlace.ts`. Only a student of the course (Student view's
// test student included: its own user id) is remembered; staff and read-only viewers never are. S3 adds the readers.
import { useContext, useEffect } from "react";
import { CourseContext } from "@/components/lms/CourseContext";
import { useLmsMe } from "./useLmsMe";
import { deviceStorage, lobbyPlace, placeOfPath, writePlace } from "./lastPlace";
import { inCourseSpace } from "./templates";


/** The course layout: every student navigation inside a course (tabs and object pages). */
export function useRememberPlace(pathname: string, enabled: boolean): void {
  const { me } = useLmsMe();
  const userId = me?.id ?? null;
  useEffect(() => {
    if (!enabled || !userId) return;
    writePlace(deviceStorage(), userId, placeOfPath(pathname));
  }, [enabled, userId, pathname]);
}

/** The player and the result page: the attempt's lobby (an attempt URL is never stored). */
export function useRememberLobby(lang: string, courseId: string, assessmentId: string | null | undefined): void {
  const { me } = useLmsMe();
  const ctx = useContext(CourseContext);
  const userId = me?.id ?? null;
  const enabled = inCourseSpace(ctx?.course) && ctx?.course.id === courseId;
  useEffect(() => {
    if (!enabled || !userId || !assessmentId) return;
    writePlace(deviceStorage(), userId, lobbyPlace(lang, courseId, assessmentId));
  }, [enabled, userId, lang, courseId, assessmentId]);
}
