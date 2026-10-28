"use client";

import React from "react";
import { useParams } from "next/navigation";
import { AnnouncementEditor } from "@/components/lms/announcements/AnnouncementEditor";
import { StaffGate } from "@/components/lms/content/StaffGate";

export default function EditAnnouncementRoute() {
  const { announcementId } = useParams<{ announcementId: string }>();
  return <StaffGate><AnnouncementEditor announcementId={announcementId} /></StaffGate>;
}
