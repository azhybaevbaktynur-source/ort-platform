"use client";

import React, { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

interface MathRendererProps {
  content: string;
  className?: string;
}

/**
 * High-performance KaTeX renderer that parses mixed text containing
 * inline $math$ and block $$math$$ formulas, fully supporting Cyrillic characters.
 */
export const MathRenderer: React.FC<MathRendererProps> = ({ content, className = "" }) => {
  const renderedContent = useMemo(() => {
    if (!content) return "";

    // Replace block math $$...$$
    let formatted = content.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
      try {
        return katex.renderToString(math.trim(), {
          displayMode: true,
          throwOnError: false,
        });
      } catch {
        return `$$${math}$$`;
      }
    });

    // Replace inline math $...$
    formatted = formatted.replace(/\$([^$]+?)\$/g, (_, math) => {
      try {
        return katex.renderToString(math.trim(), {
          displayMode: false,
          throwOnError: false,
        });
      } catch {
        return `$${math}$`;
      }
    });

    return formatted;
  }, [content]);

  return (
    <div
      className={`prose max-w-none text-slate-800 leading-relaxed ${className}`}
      dangerouslySetInnerHTML={{ __html: renderedContent }}
    />
  );
};

