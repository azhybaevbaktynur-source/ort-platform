import { lmsFetch } from "./client";
import type { MyTeacherRequestOut, TeacherRequestIn } from "./types";

export const submitTeacherRequest = (body: TeacherRequestIn) =>
  lmsFetch<MyTeacherRequestOut>("/me/teacher-requests", { method: "POST", body });
export const listMyTeacherRequests = () => lmsFetch<MyTeacherRequestOut[]>("/me/teacher-requests");
