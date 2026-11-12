"use client";

// Step 3a S2 (STUDENT_IA_DESIGN §2.5): the write hooks of `lastPlace.ts`. Only a student of the course (Student view's
// test student included: its own user id) is remembered; staff and read-only viewers never are. S3 adds the reader.
import { useContext, useEffect, useState } from "react";
import { CourseContext } from "@/components/lms/CourseContext";
import { useLmsMe } from "./useLmsMe";
import { deviceStorage, lobbyPlace, placeOfPath, readLastPlace, readRecentCourses, writePlace, type LastPlace } from "./lastPlace";
import { inCourseSpace } from "./templates";

/** Step 3a S3: fired after every write, so the frame's readers (sidebar rows, «Продолжить») follow at once. */
const PLACE_EVENT = "ort-last-place";

function written(): void {
  try { window.dispatchEvent(new Event(PLACE_EVENT)); } catch { /* no window */ }
}

/** The course layout: every student navigation inside a course (tabs and object pages). */
export function useRememberPlace(pathname: string, enabled: boolean): void {
  const { me } = useLmsMe();
  const userId = me?.id ?? null;
  useEffect(() => {
    if (!enabled || !userId) return;
    writePlace(deviceStorage(), userId, placeOfPath(pathname));
    written();
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
    written();
  }, [enabled, userId, lang, courseId, assessmentId]);
}

export interface PlaceRead {
  place: LastPlace | null;
  recent: string[];
}

const NOTHING: PlaceRead = { place: null, recent: [] };

/**
 * Step 3a S3: this user's last place and recent courses (sidebar order, the rows' tab, «Продолжить»), read on mount
 * and after every write. Nothing on the server render; private mode gives nothing (the server fallback then decides).
 */
export function useLastPlaceRead(): PlaceRead {
  const { me } = useLmsMe();
  const userId = me?.id ?? null;
  const [read, setRead] = useState<PlaceRead>(NOTHING);
  useEffect(() => {
    if (!userId) { setRead(NOTHING); return; }
    const load = () => {
      const s = deviceStorage();
      setRead({ place: readLastPlace(s, userId), recent: readRecentCourses(s, userId) });
    };
    load();
    window.addEventListener(PLACE_EVENT, load);
    window.addEventListener("storage", load);
    return () => {
      window.removeEventListener(PLACE_EVENT, load);
      window.removeEventListener("storage", load);
    };
  }, [userId]);
  return read;
}
