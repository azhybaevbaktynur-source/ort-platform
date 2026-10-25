import React from "react";
import { LoaderCircle } from "lucide-react";
import { cn } from "./utils";

/** Decorative spinner; pair it with visible text or `aria-busy` on the owner. */
export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle aria-hidden="true" className={cn("h-4 w-4 shrink-0 animate-spin", className)} />;
}
