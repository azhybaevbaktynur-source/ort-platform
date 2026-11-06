"use client";

import React from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";

/** SF-1: the "back" link above the lobby and the result page (chevron, 44 px touch target on phones). */
export function BackLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="inline-flex min-h-11 items-center gap-1 text-sm font-medium text-brand-700 hover:underline sm:min-h-0">
      <ChevronLeft className="h-4 w-4" aria-hidden="true" />{children}
    </Link>
  );
}
