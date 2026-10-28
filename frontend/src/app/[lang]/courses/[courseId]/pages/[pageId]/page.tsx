"use client";

import React from "react";
import { useParams } from "next/navigation";
import { PageView } from "@/components/lms/pages/PageView";

export default function PageViewRoute() {
  const { pageId } = useParams<{ pageId: string }>();
  return <PageView pageId={pageId} />;
}
