import { lmsFetch } from "./client";
import type { MyTeacherRequestOut } from "./types";

export const submitTeacherRequest = (message?: string) =>
  lmsFetch<MyTeacherRequestOut>("/me/teacher-requests", { method: "POST", body: message ? { message } : {} });
export const listMyTeacherRequests = () => lmsFetch<MyTeacherRequestOut[]>("/me/teacher-requests");
