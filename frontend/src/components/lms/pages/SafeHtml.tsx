"use client";

// Phase 8a S4b: renders the server's `body_html` (Markdown rendered and sanitized by nh3 on the server, design 5.1)
// and typesets $...$ / $$...$$ with KaTeX auto-render. The client never renders raw user Markdown.
// Phase 8c UX m5: auto-render is loaded once per page (`preloadKatexAutoRender`, called when an editor with a preview
// mounts). Once loaded, typesetting runs before paint; while it loads, a body with "$" stays invisible, so phones
// never flash raw LaTeX.
// Lesson course requests R6 / C6: the body uses Noto Sans (`noto.variable`, read by `.page-body` in globals.css).
// «Проверь себя» answers are native <details> (no JS needed to open them); the server writes the closed summary text
// («Показать ответ» / «Жоопту көрсөт»), and this component swaps it for `pages.view.hideAnswer` while the answer is
// open and back when it closes. Printing opens every <details> (CSS `::details-content`, plus `beforeprint` where
// that selector is not supported).
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import "katex/dist/katex.min.css";
import { cn } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { noto } from "@/lib/fonts";

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
  const { t } = useTranslation();
  const hideText = t("pages.view.hideAnswer");
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // `toggle` does not bubble: listen in the capture phase on the body
    const onToggle = (e: Event) => {
      const d = e.target;
      if (!(d instanceof HTMLDetailsElement) || d.classList.contains("why") || !d.closest(".callout--check")) return;
      const summary = d.querySelector(":scope > summary") as HTMLElement | null;
      if (!summary) return;
      if (summary.dataset.closedText === undefined) summary.dataset.closedText = summary.textContent ?? "";
      summary.textContent = d.open ? hideText : summary.dataset.closedText;
    };
    // print: open closed answers for the printout, close them again afterwards (browsers without ::details-content)
    const printOpened: HTMLDetailsElement[] = [];
    const supportsDetailsContent = typeof CSS !== "undefined" && CSS.supports?.("selector(::details-content)");
    const beforePrint = () => {
      if (supportsDetailsContent) return;
      el.querySelectorAll("details:not([open])").forEach((d) => { (d as HTMLDetailsElement).open = true; printOpened.push(d as HTMLDetailsElement); });
    };
    const afterPrint = () => { printOpened.splice(0).forEach((d) => { d.open = false; }); };
    el.addEventListener("toggle", onToggle, true);
    window.addEventListener("beforeprint", beforePrint);
    window.addEventListener("afterprint", afterPrint);
    return () => {
      el.removeEventListener("toggle", onToggle, true);
      window.removeEventListener("beforeprint", beforePrint);
      window.removeEventListener("afterprint", afterPrint);
    };
  }, [hideText]);
  return (
    <div
      ref={ref}
      className={cn("page-body", noto.variable, pending && "invisible", className)}
      dangerouslySetInnerHTML={inner}
    />
  );
}
