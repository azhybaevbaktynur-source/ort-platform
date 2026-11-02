"use client";

import React from "react";
import { useStaticText } from "@/components/mascot/staticText";

/** Last resort when the root layout itself fails: no providers, no design system, plain neutral markup. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { lang, m } = useStaticText();
  return (
    <html lang={lang}>
      <body style={{ fontFamily: "system-ui, sans-serif", textAlign: "center", padding: "4rem 1rem" }}>
        <h1 style={{ fontSize: "1.25rem" }}>{m.error.title}</h1>
        <p>{m.error.body}</p>
        <p>
          <button type="button" onClick={() => reset()} style={{ padding: "0.6rem 1rem", marginRight: "0.5rem" }}>{m.error.retry}</button>
          <a href={`/${lang}`}>{m.error.home}</a>
        </p>
      </body>
    </html>
  );
}
