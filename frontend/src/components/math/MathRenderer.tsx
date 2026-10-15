"use client";

import React, { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

interface MathRendererProps {
  content: string;
  className?: string;
}

// Inline $math$ and block $$math$$ (block first, so $$ is never read as two inline delimiters)
const MATH_PATTERN = /\$\$([\s\S]*?)\$\$|\$([^$]+?)\$/g;
// After escaping, only <u> and <b> (underline/bold, e.g. grammar questions) are turned back into tags
const ALLOWED_TAG_PATTERN = /&lt;(\/?)(u|b)&gt;/gi;

function escapeText(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(ALLOWED_TAG_PATTERN, (_, slash: string, tag: string) => `<${slash}${tag.toLowerCase()}>`)
    .replace(/\n/g, "<br />");
}

function renderMath(math: string, displayMode: boolean, original: string): string {
  try {
    return katex.renderToString(math.trim(), { displayMode, throwOnError: false });
  } catch {
    return escapeText(original);
  }
}

/**
 * Converts question text to safe HTML: LaTeX between $...$ / $$...$$ via KaTeX, <u> and <b> kept,
 * every other HTML tag escaped, and line breaks preserved.
 */
export function renderRichText(content: string): string {
  if (!content) return "";
  let html = "";
  let last = 0;
  for (const match of content.matchAll(MATH_PATTERN)) {
    const index = match.index ?? 0;
    html += escapeText(content.slice(last, index));
    html += match[1] !== undefined ? renderMath(match[1], true, match[0]) : renderMath(match[2], false, match[0]);
    last = index + match[0].length;
  }
  return html + escapeText(content.slice(last));
}

/**
 * High-performance KaTeX renderer that parses mixed text containing
 * inline $math$ and block $$math$$ formulas, fully supporting Cyrillic characters.
 */
export const MathRenderer: React.FC<MathRendererProps> = ({ content, className = "" }) => {
  const renderedContent = useMemo(() => renderRichText(content), [content]);

  return (
    <div
      className={`prose max-w-none text-slate-800 leading-relaxed ${className}`}
      dangerouslySetInnerHTML={{ __html: renderedContent }}
    />
  );
};
