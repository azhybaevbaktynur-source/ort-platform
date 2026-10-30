"use client";

// Phase 8a S4b: renders the server's `body_html` (Markdown rendered and sanitized by nh3 on the server, design 5.1)
// and typesets $...$ / $$...$$ with KaTeX auto-render. The client never renders raw user Markdown.
// Phase 8c UX m5: auto-render is loaded once per page (`preloadKatexAutoRender`, called when an editor with a preview
// mounts). Once loaded, typesetting runs before paint; while it loads, a body with "$" stays invisible, so phones
// never flash raw LaTeX.
import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import "katex/dist/katex.min.css";
import { cn } from "@/components/ui";

type AutoRender = (el: HTMLElement, opts: Record<string, unknown>) => void;
let autoRender: AutoRender | null = null;
let loading: Promise<AutoRender> | null = null;

/** Starts loading KaTeX auto-render (idempotent). */
export function preloadKatexAutoRender(): Promise<AutoRender> {
  if (!loading) {
    loading = import("katex/contrib/auto-render").then((mod) => {
      autoRender = mod.default as unknown as AutoRender;
      return autoRender;
    });
    loading.catch(() => { loading = null; });
  }
  return loading;
}

const OPTIONS = {
  delimiters: [
    { left: "$$", right: "$$", display: true },
    { left: "$", right: "$", display: false },
  ],
  throwOnError: false,
  trust: false,
  maxSize: 20,
  maxExpand: 200,
};

export function SafeHtml({ html, className }: { html: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const hasMath = html.includes("$");
  const [pending, setPending] = useState(hasMath && !autoRender);
  // the same object while `html` is unchanged: React re-sets innerHTML when the object changes, which would drop
  // the typeset formulas on the `pending` re-render
  const inner = useMemo(() => ({ __html: html }), [html]);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !html.includes("$")) { setPending(false); return; }
    if (autoRender) {
      autoRender(el, OPTIONS);
      setPending(false);
      return;
    }
    let cancelled = false;
    setPending(true);
    preloadKatexAutoRender()
      .then((render) => { if (!cancelled && ref.current) render(ref.current, OPTIONS); })
      .catch(() => { /* the raw text stays readable */ })
      .finally(() => { if (!cancelled) setPending(false); });
    return () => { cancelled = true; };
  }, [html]);
  return (
    <div
      ref={ref}
      className={cn("page-body max-w-none", pending && "invisible", className)}
      dangerouslySetInnerHTML={inner}
    />
  );
}
