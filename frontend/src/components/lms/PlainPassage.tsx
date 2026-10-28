"use client";

import React from "react";
import { renderRichText } from "@/components/math/MathRenderer";
import { useTemplateUi } from "@/lib/lms/templates";
import { NumberedPassage } from "./NumberedPassage";
import type { PassageDisplay } from "@/lib/lms/blocks";

/** A passage without line numbers (general courses, design §5.3): same typography, line breaks kept. */
export function PlainPassage({ text, className = "" }: { text: string; className?: string }) {
  if (!text) return null;
  const lines = text.split("\n");
  return (
    <div className={`font-serif text-gray-900 leading-relaxed text-base select-text space-y-1 ${className}`}>
      {lines.map((line, idx) => (
        <div key={idx} className="min-h-[1.5rem]">
          {line ? (
            <span className="leading-relaxed" dangerouslySetInnerHTML={{ __html: renderRichText(line) }} />
          ) : (
            <span className="leading-relaxed">{" "}</span>
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * Numbered or plain passage. Phase 8b S3 (PHASE_8B_DESIGN 8.2): the player and result pages pass `display` from the
 * attempt state / result payload (the server resolves NULL to the course template's value, so ORT stays "numbered");
 * without it (builder screens, or a payload without the field) the course template decides as before.
 */
export function TemplatePassage({ text, className, display }: { text: string; className?: string; display?: PassageDisplay | null }) {
  const ui = useTemplateUi();
  return (display ?? ui.passageDisplay) === "numbered" ? <NumberedPassage text={text} className={className} /> : <PlainPassage text={text} className={className} />;
}
