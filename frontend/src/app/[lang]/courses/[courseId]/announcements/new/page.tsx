"use client";

import React from "react";
import { AnnouncementEditor } from "@/components/lms/announcements/AnnouncementEditor";
import { StaffGate } from "@/components/lms/content/StaffGate";

export default function NewAnnouncementRoute() {
  return <StaffGate><AnnouncementEditor /></StaffGate>;
}
