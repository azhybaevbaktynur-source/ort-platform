"use client";

import React from "react";
import { renderRichText } from "@/components/math/MathRenderer";
import { useTemplateUi } from "@/lib/lms/templates";
import { NumberedPassage } from "./NumberedPassage";

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

/** Numbered or plain passage, chosen by the course template (`passage_display`). */
export function TemplatePassage({ text, className }: { text: string; className?: string }) {
  const ui = useTemplateUi();
  return ui.passageDisplay === "numbered" ? <NumberedPassage text={text} className={className} /> : <PlainPassage text={text} className={className} />;
}
