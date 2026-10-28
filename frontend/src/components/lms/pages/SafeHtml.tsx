"use client";

// Phase 8a S4b: renders the server's `body_html` (Markdown rendered and sanitized by nh3 on the server, design 5.1)
// and typesets $...$ / $$...$$ with KaTeX auto-render. The client never renders raw user Markdown.
import React, { useEffect, useRef } from "react";
import "katex/dist/katex.min.css";
import { cn } from "@/components/ui";

export function SafeHtml({ html, className }: { html: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    void import("katex/contrib/auto-render").then((mod) => {
      const el = ref.current;
      if (cancelled || !el) return;
      mod.default(el, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
        trust: false,
        maxSize: 20,
        maxExpand: 200,
      });
    });
    return () => { cancelled = true; };
  }, [html]);
  return (
    <div
      ref={ref}
      className={cn("prose max-w-none break-words text-slate-800 leading-relaxed [&_img]:h-auto [&_img]:max-w-full [&_table]:block [&_table]:overflow-x-auto", className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
