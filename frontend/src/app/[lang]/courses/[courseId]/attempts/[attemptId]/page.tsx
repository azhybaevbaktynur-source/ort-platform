"use client";

import React from "react";
import { useParams } from "next/navigation";
import { PlayerShell } from "@/components/lms/player/PlayerShell";

export default function AttemptPlayerPage() {
  const params = useParams<{ courseId: string; attemptId: string }>();
  return <PlayerShell courseId={params.courseId} attemptId={params.attemptId} />;
}
