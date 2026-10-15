"use client";

import React from "react";
import { renderRichText } from "@/components/math/MathRenderer";

interface NumberedPassageProps {
  text: string;
  className?: string;
}

// Official ORT passages mark every 5th printed line as "[5] ", "[10] ", ... (questions cite these numbers)
const LINE_MARKER = /^\[(\d+)\]\s?/;

/**
 * Renders an official ORT reading passage with line numbers every 5 lines (5, 10, 15...).
 * Splits the passage by newlines (\n) and provides a dedicated left gutter with monospace numbers.
 * If the passage carries its own "[N] " markers, those numbers are shown instead of counting lines.
 */
export const NumberedPassage: React.FC<NumberedPassageProps> = ({ text, className = "" }) => {
  if (!text) return null;

  const lines = text.split("\n");
  const hasMarkers = lines.some((line) => LINE_MARKER.test(line));

  return (
    <div className={`font-serif text-gray-900 leading-relaxed text-base select-text space-y-1 ${className}`}>
      {lines.map((line, idx) => {
        const marker = hasMarkers ? line.match(LINE_MARKER) : null;
        const lineNumber = marker ? Number(marker[1]) : idx + 1;
        const showNumber = hasMarkers ? Boolean(marker) : lineNumber % 5 === 0;
        const lineText = marker ? line.slice(marker[0].length) : line;

        return (
          <div key={idx} className="relative pl-10 min-h-[1.5rem]">
            {showNumber && (
              <span
                className="absolute left-2 top-0 text-xs text-gray-400 font-mono text-right w-6 select-none pointer-events-none"
                aria-hidden="true"
              >
                {lineNumber}
              </span>
            )}
            {lineText ? (
              <span className="leading-relaxed" dangerouslySetInnerHTML={{ __html: renderRichText(lineText) }} />
            ) : (
              <span className="leading-relaxed">{" "}</span>
            )}
          </div>
        );
      })}
    </div>
  );
};
