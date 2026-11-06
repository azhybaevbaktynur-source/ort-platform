"use client";

import React from "react";
import dictionary from "../ky.json?lazy";
import { registerDictionary } from "../context";

/** S5 performance: the ky dictionary as a chunk of its own; context.tsx renders it through next/dynamic. */
export default function Dictionary({ children }: { children: React.ReactNode }) {
  registerDictionary("ky", dictionary);
  return <>{children}</>;
}
