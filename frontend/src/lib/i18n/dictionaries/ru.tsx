"use client";

import React from "react";
import dictionary from "../generated/ru.core.json?lazy";
import { registerDictionary } from "../context";

/** S5 performance: the ru dictionary as a chunk of its own; context.tsx renders it through next/dynamic. */
export default function Dictionary({ children }: { children: React.ReactNode }) {
  registerDictionary("ru", dictionary);
  return <>{children}</>;
}
