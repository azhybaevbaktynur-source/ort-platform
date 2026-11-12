"use client";

import React, { Suspense } from "react";
import { CatalogView } from "@/components/lms/home/CatalogView";

/** Phase 6b S6b: course catalog (moved here from the /courses#catalog block). Step 3a S4: `?exam=` picks the chip. */
export default function CatalogPage() {
  return (
    <Suspense fallback={null}>
      <CatalogView />
    </Suspense>
  );
}
